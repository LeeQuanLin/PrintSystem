"""FastAPI 路由：页面、配置查询、上传、生成、下载、文件库、WebSocket。

印前生成主流程：选类型尺码 → 上传图 → 触发生成 → WS 进度 → 下载产物。
文件库：上传图与生成产物统一入库，缩略图浏览/下载/删除。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.config import (
    create_size_config,
    delete_size_config,
    get_impose,
    get_params,
    get_size_config_path,
    get_size_raw,
    get_sizes,
    get_storage,
    list_impose_presets,
    list_types,
    rename_size_config,
    save_size_config,
)
from app.storage import store
from app.storage import store
from app.tasks.scripts._state import TaskStatus
from app.web import tasks as _tasks
from app.web import ws as _ws

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")

# 命名占位符 %(name)s 提取正则
_PLACEHOLDER_RE = re.compile(r"%\(([^)]+)\)")


def _extract_placeholders(template: str) -> list[str]:
    """从 %(name)s 模板中提取变量名列表（去重保序）。"""
    seen: list[str] = []
    for m in _PLACEHOLDER_RE.finditer(template):
        name = m.group(1)
        if name not in seen:
            seen.append(name)
    return seen


def _collect_placeholders(params) -> list[str]:
    """收集 save_name 与所有 text_marks.items[].text 的占位符变量名。"""
    names: list[str] = []
    # save_name
    if params.output.save_name:
        for n in _extract_placeholders(params.output.save_name):
            if n not in names:
                names.append(n)
    # text_marks
    if params.marks.text_marks.enabled:
        for item in params.marks.text_marks.items:
            for n in _extract_placeholders(item.text):
                if n not in names:
                    names.append(n)
    return names

# 项目根
ROOT = Path(__file__).resolve().parents[2]
TMP_DIR = ROOT / "data" / "tmp"          # 上传暂存（落库前）
OUTPUT_DIR = ROOT / "data" / "outputs"    # 生成暂存（入库后清理）


def _resolve_config_path(type_id: str, size_id: str) -> Path:
    """查 type+size 对应的配置文件路径。"""
    try:
        return get_size_config_path(type_id, size_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---- 健康检查 ----

@router.get("/health")
async def health():
    """容器 HEALTHCHECK 与运维探活用。"""
    return {"status": "ok"}


# ---- 页面 ----

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """印前生成页。"""
    return templates.TemplateResponse(request, "index.html")


@router.get("/library", response_class=HTMLResponse)
async def library_page(request: Request):
    """文件库页。"""
    return templates.TemplateResponse(request, "library.html")


@router.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    """配置管理入口，重定向到印前配置。"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/config/prepress", status_code=302)


@router.get("/config/prepress", response_class=HTMLResponse)
async def config_prepress_page(request: Request):
    """印前配置页。"""
    return templates.TemplateResponse(request, "config_prepress.html")


@router.get("/config/impose", response_class=HTMLResponse)
async def config_impose_page(request: Request):
    """排版配置页（只读）。"""
    return templates.TemplateResponse(request, "config_impose.html")


@router.get("/config/storage", response_class=HTMLResponse)
async def config_storage_page(request: Request):
    """存储配置页（只读）。"""
    return templates.TemplateResponse(request, "config_storage.html")


# ---- 配置查询 ----

@router.get("/api/types")
async def api_types():
    """类型列表。"""
    return list_types()


@router.get("/api/sizes/{type_id}")
async def api_sizes(type_id: str):
    """某类型的尺码列表。"""
    try:
        return get_sizes(type_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/api/params/{type_id}/{size_id}")
async def api_params(type_id: str, size_id: str):
    """某尺码的印前参数 + 占位符变量名列表（前端按变量名渲染输入框）。"""
    try:
        params = get_params(type_id, size_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "params": params.model_dump(),
        "save_name_template": params.output.save_name,
        "placeholders": _collect_placeholders(params),
    }


# ---- 配置管理 ----

@router.get("/api/config/prepress")
async def api_config_prepress_tree():
    """印前配置树：[{id, name, sizes:[{id,name}]}]。"""
    tree = []
    for t in list_types():
        tree.append({"id": t["id"], "name": t["name"], "sizes": get_sizes(t["id"])})
    return tree


@router.get("/api/config/prepress/{type_id}/{size_id}")
async def api_config_prepress_get(type_id: str, size_id: str):
    """某尺码配置 json 全文。"""
    try:
        return get_size_raw(type_id, size_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/api/config/prepress/{type_id}/{size_id}")
async def api_config_prepress_save(type_id: str, size_id: str, body: dict):
    """保存尺码配置（校验后落盘 + 重载）。"""
    try:
        save_size_config(type_id, size_id, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"saved": f"{type_id}/{size_id}"}


@router.post("/api/config/prepress")
async def api_config_prepress_create(body: dict):
    """新增尺码配置。body: {type_id, size_id, name, params}。"""
    type_id = body.get("type_id")
    size_id = body.get("size_id")
    name = body.get("name") or size_id
    params = body.get("params")
    if not (type_id and size_id and params):
        raise HTTPException(status_code=400, detail="缺 type_id/size_id/params")
    try:
        path = create_size_config(type_id, size_id, name, params)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"created": f"{type_id}/{size_id}", "file": path.name}


@router.delete("/api/config/prepress/{type_id}/{size_id}")
async def api_config_prepress_delete(type_id: str, size_id: str):
    """删除尺码配置。"""
    try:
        delete_size_config(type_id, size_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"deleted": f"{type_id}/{size_id}"}


@router.post("/api/config/prepress/rename")
async def api_config_prepress_rename(body: dict):
    """
    重命名尺码的 type/size id 与显示名。

    body: {old_type, old_size, new_type, new_size, new_name}
    """
    old_type = body.get("old_type")
    old_size = body.get("old_size")
    new_type = body.get("new_type")
    new_size = body.get("new_size")
    new_name = body.get("new_name")
    if not (old_type and old_size and new_type and new_size):
        raise HTTPException(status_code=400, detail="缺 old_type/old_size/new_type/new_size")
    try:
        path = rename_size_config(old_type, old_size, new_type, new_size, new_name or new_size)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"renamed": f"{new_type}/{new_size}", "file": path.name}


@router.get("/api/config/impose")
async def api_config_impose():
    """排版配置只读摘要。"""
    cfg = get_impose()
    return {
        "version": cfg.version,
        "presets": [
            {
                "id": p.id,
                "name": p.name,
                "canvas": {"width_mm": p.canvas.width_mm, "height_mm": p.canvas.height_mm,
                           "dpi": p.canvas.dpi, "bitdepth": p.canvas.bitdepth},
                "gutters": {"horizontal_mm": p.gutters.horizontal_mm,
                            "vertical_mm": p.gutters.vertical_mm, "margin_mm": p.gutters.margin_mm},
                "output": {"format": p.output.format, "compression": p.output.compression},
            }
            for p in cfg.presets
        ],
    }


@router.get("/api/config/storage")
async def api_config_storage():
    """存储配置只读。"""
    s = get_storage()
    return {
        "library": {"path": s.library.path, "db_filename": s.library.db_filename},
        "thumbnail": {"format": s.thumbnail.format, "max_size_px": s.thumbnail.max_size_px,
                      "quality": s.thumbnail.quality},
        "tasks": {"max_concurrency": s.tasks.max_concurrency},
    }


# ---- 上传 ----

@router.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    """上传图片并入文件库，返回库内路径（供生成读取）。"""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    original_name = file.filename or "upload.png"
    ext = Path(original_name).suffix or ".png"
    # 落临时文件再入库（store 会 move 走）
    import uuid as _uuid
    content = await file.read()
    tmp = TMP_DIR / f"upload_{_uuid.uuid4().hex}{ext}"
    tmp.write_bytes(content)
    try:
        rec = store.ingest_file(
            tmp, original_name=original_name, source="upload", move=True
        )
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"入库失败: {e}")
    return {
        "image_id": rec.id,
        "path": str(store.original_path(rec.id, rec.stored_name)),
        "original_name": rec.original_name,
        "width": rec.width_px,
        "height": rec.height_px,
        "size_bytes": rec.size_bytes,
    }


# ---- 生成 ----

@router.post("/api/generate")
async def api_generate(body: dict):
    """
    提交生成任务，起后台线程，返回 task_id。

    body: {type_id, size_id, image_path, save_name?, vars?}
    """
    type_id = body.get("type_id")
    size_id = body.get("size_id")
    image_path = body.get("image_path")
    if not (type_id and size_id and image_path):
        raise HTTPException(status_code=400, detail="缺 type_id/size_id/image_path")

    config_path = _resolve_config_path(type_id, size_id)
    if not Path(image_path).exists():
        raise HTTPException(status_code=400, detail=f"图片不存在: {image_path}")

    save_name = body.get("save_name")
    vars_dict = body.get("vars") or {}

    task_id = _tasks.submit(
        image_path=image_path,
        config_path=str(config_path),
        output_root=str(OUTPUT_DIR),
        save_name=save_name,
        vars=vars_dict,
        type_id=type_id,
        size_id=size_id,
    )
    return {"task_id": task_id}


# ---- 任务状态 ----

@router.get("/api/tasks/{task_id}")
async def api_task(task_id: str):
    """查任务当前 State。"""
    state = _tasks.get(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"task_id": task_id, **state.to_dict()}


@router.get("/api/tasks/{task_id}/download/{fmt}")
async def api_download(task_id: str, fmt: str):
    """下载产物文件（按格式 psd/tif/png）。"""
    state = _tasks.get(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if state.status != TaskStatus.SUCCEEDED:
        raise HTTPException(status_code=400, detail=f"任务未成功: {state.status.value}")
    for o in state.outputs:
        if o["format"] == fmt:
            p = Path(o["path"])
            if not p.exists():
                raise HTTPException(status_code=404, detail="产物文件不存在")
            return FileResponse(p, filename=p.name)
    raise HTTPException(status_code=404, detail=f"无 {fmt} 格式产物")


@router.get("/api/tasks/{task_id}/thumb")
async def api_thumb(task_id: str):
    """下载缩略图。"""
    state = _tasks.get(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not state.thumb_path:
        raise HTTPException(status_code=404, detail="无缩略图")
    p = Path(state.thumb_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="缩略图不存在")
    return FileResponse(p, media_type="image/webp")


# ---- 文件库 ----

@router.get("/api/library")
async def api_library_list(
    source: Optional[str] = None,
    ref_type: Optional[str] = None,
    ref_size: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """文件库列表（按 created_at 倒序，支持筛选与分页）。

    每项附加 path：库内原图绝对路径，供印前生成页"从文件库选择"直接用。
    返回 total：当前筛选条件下的总条数（用于分页），count 为本页条数。
    """
    recs = store.list(
        source=source, ref_type=ref_type, ref_size=ref_size,
        q=q, limit=limit, offset=offset,
    )
    items = []
    for r in recs:
        d = r.to_dict()
        d["path"] = str(store.original_path(r.id, r.stored_name))
        items.append(d)
    total = store.count(source=source, ref_type=ref_type, ref_size=ref_size, q=q)
    return {"items": items, "count": len(recs), "total": total}


@router.get("/api/library/{image_id}")
async def api_library_get(image_id: str):
    """单条记录详情。"""
    rec = store.get(image_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return rec.to_dict()


@router.get("/api/library/{image_id}/thumb")
async def api_library_thumb(image_id: str):
    """缩略图。"""
    rec = store.get(image_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    p = store.thumb_path(image_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail="缩略图不存在")
    return FileResponse(p, media_type="image/webp")


@router.get("/api/library/{image_id}/download")
async def api_library_download(image_id: str):
    """下载原图。"""
    rec = store.get(image_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    p = store.original_path(image_id, rec.stored_name)
    if not p.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(p, filename=rec.original_name)


@router.delete("/api/library/{image_id}")
async def api_library_delete(image_id: str):
    """删除一条（文件 + 元数据）。"""
    if not store.delete(image_id):
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"deleted": image_id}


# ---- WebSocket ----

@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    """WebSocket：连接后下发全量任务，后续实时推送 State 更新。"""
    await _ws.connect(ws)
    # 下发当前全量任务
    for t in _tasks.all_tasks():
        await ws.send_text(json.dumps(t, ensure_ascii=False))
    try:
        while True:
            await ws.receive_text()  # 保持连接（前端可发心跳）
    except WebSocketDisconnect:
        _ws.disconnect(ws)
