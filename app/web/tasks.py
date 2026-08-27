"""进程内任务管理。

submit() 起后台线程跑 prepress.run，State.on_update 回调触发 WS 广播。
任务状态存内存 dict，重启丢失（基础阶段，后续升级 SQLite）。

产物入库：run() 成功后，由本模块（web 层，非脚本）把产物 ingest 进文件库，
更新 state.outputs 指向库内路径，并清理暂存目录。
"""
from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Optional

from app.config.impose import Preset
from app.storage import store
from app.tasks.scripts._state import State, TaskStatus
from app.tasks.scripts.impose import SlotInput, run as impose_run
from app.tasks.scripts.prepress import run
from app.web import ws as _ws

_tasks: dict[str, State] = {}
_lock = threading.Lock()


def _make_on_update(task_id: str):
    """构造 State.on_update 回调：把 state 推到 WS。"""
    def _cb(state: State) -> None:
        _ws.broadcast_threadsafe(task_id, state.to_dict())
    return _cb


def _ingest_outputs(
    state: State,
    output_root: str,
    *,
    type_id: Optional[str],
    size_id: Optional[str],
    task_id: str,
) -> None:
    """把 run() 产出的文件 ingest 进文件库，更新 state.outputs。"""
    updated: list[dict] = []
    for o in state.outputs:
        src = Path(o["path"])
        if not src.exists():
            updated.append(o)
            continue
        # PSD 产物复用 run 已生成的缩略图，避免重复合成大图
        thumb_src = None
        if o["format"] == "psd" and state.thumb_path and Path(state.thumb_path).exists():
            thumb_src = state.thumb_path
        rec = store.ingest_file(
            src,
            original_name=src.name,
            source="prepress",
            fmt=o["format"],
            ref_type=type_id,
            ref_size=size_id,
            task_id=task_id,
            thumb_src=thumb_src,
            move=True,
        )
        o = {**o, "library_id": rec.id, "path": str(store.original_path(rec.id, rec.stored_name))}
        updated.append(o)
    state.outputs = updated
    # 任务缩略图重指到库内（PSD 产物的缩略图已 move 进库）
    old_thumb = state.thumb_path
    lib_id = next((o.get("library_id") for o in updated if o.get("library_id")), None)
    if lib_id:
        state.thumb_path = str(store.thumb_path(lib_id))
    _cleanup_staging(old_thumb)


def _cleanup_staging(old_thumb: Optional[str]) -> None:
    """清理残留暂存缩略图与空壳暂存目录。"""
    if old_thumb:
        p = Path(old_thumb)
        p.unlink(missing_ok=True)
        # 暂存 uuid 子目录（outputs 已 move 走，剩空壳则删）
        parent = p.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()


def submit(
    image_path: str,
    config_path: str,
    output_root: str,
    save_name: Optional[str] = None,
    vars: Optional[dict] = None,
    type_id: Optional[str] = None,
    size_id: Optional[str] = None,
) -> str:
    """
    起后台线程跑 prepress.run，返回 task_id。

    Args:
        image_path: 输入图片路径
        config_path: 尺码配置 json 路径
        output_root: 输出根目录（在其下建 uuid 子目录，产物入库后清理）
        save_name: 可选，覆盖配置的 save_name
        vars: 占位符变量字典
        type_id / size_id: 关联类型与尺码，写入产物库记录

    Returns:
        task_id
    """
    task_id = uuid.uuid4().hex
    state = State(on_update=_make_on_update(task_id))
    with _lock:
        _tasks[task_id] = state

    def worker() -> None:
        try:
            run(image_path, config_path, output_root, state, save_name, vars)
            if state.status == TaskStatus.SUCCEEDED:
                _ingest_outputs(
                    state, output_root, type_id=type_id, size_id=size_id, task_id=task_id
                )
                state._notify()
        except Exception as e:
            # run 内部已 try/except 设 fail，这里是兜底
            if state.status != TaskStatus.FAILED:
                state.fail(f"worker 异常: {e}")

    t = threading.Thread(target=worker, daemon=True, name=f"task-{task_id[:8]}")
    t.start()
    return task_id


def get(task_id: str) -> Optional[State]:
    """取任务 State。"""
    with _lock:
        return _tasks.get(task_id)


def all_tasks() -> list[dict]:
    """所有任务摘要（用于 WS 重连后下发全量）。"""
    with _lock:
        return [{"task_id": tid, **s.to_dict()} for tid, s in _tasks.items()]


# ---- 排版任务 ----

def _ingest_impose_output(state: State, ref_type: str | None, task_id: str) -> None:
    """把 impose.run 产出的单 TIF ingest 进文件库，更新 state.outputs 指向库内路径。

    缩略图复用引擎已生成的（state.thumb_path），避免重复合成大画布。
    """
    if not state.outputs:
        return
    o = state.outputs[0]
    src = Path(o["path"])
    if not src.exists():
        return
    thumb_src = state.thumb_path if state.thumb_path and Path(state.thumb_path).exists() else None
    rec = store.ingest_file(
        src,
        original_name=src.name,
        source="impose",
        fmt=o["format"],
        ref_type=ref_type,
        task_id=task_id,
        thumb_src=thumb_src,
        move=True,
    )
    state.outputs[0] = {**o, "library_id": rec.id,
                        "path": str(store.original_path(rec.id, rec.stored_name))}
    if rec.id:
        state.thumb_path = str(store.thumb_path(rec.id))
    # 清理暂存空壳目录
    _cleanup_staging(thumb_src if thumb_src else None)


def submit_impose(
    preset: Preset,
    slots: list[dict | None],
    output_root: str,
    save_name: str | None = None,
) -> str:
    """
    起后台线程跑排版拼版，返回 task_id。

    Args:
        preset: 排版预设对象（由调用方从内联配置构造）
        slots: 槽位列表（行优先），每项 {image_id, rotation, fit_mode?} 或 None（空槽）
        output_root: 输出根目录（产物入库后清理）
        save_name: 可选，覆盖默认保存名

    Returns:
        task_id
    """
    task_id = uuid.uuid4().hex
    state = State(on_update=_make_on_update(task_id))
    with _lock:
        _tasks[task_id] = state

    def worker() -> None:
        try:
            # image_id → 文件路径，构造 SlotInput
            slot_inputs: list[SlotInput] = []
            for s in slots:
                if s is None:
                    slot_inputs.append(SlotInput(path=None))
                    continue
                rec = store.get(s["image_id"])
                if rec is None:
                    raise ValueError(f"图件不存在: {s['image_id']}")
                path = str(store.original_path(rec.id, rec.stored_name))
                slot_inputs.append(SlotInput(
                    path=path,
                    rotation=int(s.get("rotation", 0)),
                    fit_mode=s.get("fit_mode"),
                ))
            impose_run(slot_inputs, preset, output_root, state, save_name)
            if state.status == TaskStatus.SUCCEEDED:
                _ingest_impose_output(state, preset.id, task_id)
                state._notify()
        except Exception as e:
            if state.status != TaskStatus.FAILED:
                state.fail(f"worker 异常: {e}")

    t = threading.Thread(target=worker, daemon=True, name=f"task-{task_id[:8]}")
    t.start()
    return task_id
