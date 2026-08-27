"""配置模块统一入口。

印前配置采用目录扫描：configs/prepress/*.json 每个文件含 {type, size, name, params}。
启动时扫描目录，按 type→size 分组建索引。无 prepress.json 索引文件。
排版与存储配置仍是单文件。

写入 API（save/create/delete）校验后落盘并 reload_all()，立即对新任务生效。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError

from . import impose as _impose
from . import storage as _storage
from .impose import ImposeConfig, Preset
from .prepress import Params, SizeEntry, TypeEntry
from .storage import StorageConfig

ROOT = Path(__file__).resolve().parents[2]
PREPRESS_DIR = ROOT / "configs" / "prepress"


@lru_cache(maxsize=1)
def _scan_prepress() -> dict[str, dict[str, dict]]:
    """
    扫描 configs/prepress/*.json，按 type→size 建索引。

    Returns:
        {type_id: {size_id: {name, file, params_dict}}}
    """
    index: dict[str, dict[str, dict]] = {}
    for f in sorted(PREPRESS_DIR.glob("*.json")):
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        type_id = data.get("type")
        size_id = data.get("size")
        if not type_id or not size_id:
            raise ValueError(f"配置文件 {f} 缺 type 或 size 字段")
        # 校验 params
        Params.model_validate(data["params"])
        index.setdefault(type_id, {})[size_id] = {
            "name": data.get("name", size_id),
            "file": f.name,
            "params_dict": data["params"],
        }
    return index


@lru_cache(maxsize=1)
def get_impose() -> ImposeConfig:
    """加载并返回排版配置（带校验，结果缓存）。"""
    return _impose.load()


@lru_cache(maxsize=1)
def get_storage() -> StorageConfig:
    """加载并返回存储配置（带校验，结果缓存）。"""
    return _storage.load()


# ---- 印前配置查询 API ----

def list_types() -> list[dict]:
    """类型列表：[{id, name}]。"""
    idx = _scan_prepress()
    return [{"id": t, "name": t} for t in idx]


def get_sizes(type_id: str) -> list[dict]:
    """某类型的尺码列表：[{id, name}]。"""
    idx = _scan_prepress()
    if type_id not in idx:
        raise KeyError(f"类型不存在: {type_id}")
    return [{"id": s, "name": d["name"]} for s, d in idx[type_id].items()]


def get_params(type_id: str, size_id: str) -> Params:
    """某尺码的印前参数（从扫描结果读 params_dict，校验后返回 Params）。"""
    idx = _scan_prepress()
    if type_id not in idx or size_id not in idx[type_id]:
        raise KeyError(f"尺码不存在: type={type_id} size={size_id}")
    return Params.model_validate(idx[type_id][size_id]["params_dict"])


def get_size_config_path(type_id: str, size_id: str) -> Path:
    """某尺码配置文件的完整路径。"""
    idx = _scan_prepress()
    if type_id not in idx or size_id not in idx[type_id]:
        raise KeyError(f"尺码不存在: type={type_id} size={size_id}")
    return PREPRESS_DIR / idx[type_id][size_id]["file"]


# ---- 排版配置查询 API ----

def list_impose_presets() -> list[dict]:
    """排版预设列表：[{id, name}]。"""
    return [{"id": p.id, "name": p.name} for p in get_impose().presets]


def get_impose_preset(preset_id: str) -> Preset:
    """某排版预设。"""
    for p in get_impose().presets:
        if p.id == preset_id:
            return p
    raise KeyError(f"排版预设不存在: {preset_id}")


def reload_all() -> None:
    """清除缓存，强制重新加载（配置热更新用，待定）。"""
    _scan_prepress.cache_clear()
    get_impose.cache_clear()
    get_storage.cache_clear()


# ---- 印前配置写入 API（配置管理页用） ----

def _size_file_path(type_id: str, size_id: str) -> Path:
    """定位某尺码配置文件路径（现有文件优先，否则按约定名）。"""
    idx = _scan_prepress()
    if type_id in idx and size_id in idx[type_id]:
        return PREPRESS_DIR / idx[type_id][size_id]["file"]
    # 新建：约定文件名 {type}_{size}.json（id 已校验 ASCII，无路径穿越风险）
    return PREPRESS_DIR / f"{type_id}_{size_id}.json"


def get_size_raw(type_id: str, size_id: str) -> dict:
    """返回某尺码配置 json 全文（含 type/size/name/params）。"""
    idx = _scan_prepress()
    if type_id not in idx or size_id not in idx[type_id]:
        raise KeyError(f"尺码不存在: type={type_id} size={size_id}")
    path = PREPRESS_DIR / idx[type_id][size_id]["file"]
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_size_config(type_id: str, size_id: str, data: dict) -> Path:
    """
    保存某尺码配置（校验后写回文件，立即重载）。

    Args:
        type_id / size_id: 定位目标（data 里的 type/size 须与之一致）
        data: 完整配置 dict {type, size, name, params}

    Returns:
        写入的文件路径

    Raises:
        ValueError: type/size 不一致或校验失败
    """
    if data.get("type") != type_id or data.get("size") != size_id:
        raise ValueError(f"type/size 不一致: 路径 {type_id}/{size_id} vs 数据 {data.get('type')}/{data.get('size')}")
    # SizeEntry 模型字段是 {id, name, params}，文件存 {type, size, name, params}
    # 校验时把 size 映射为 id
    entry = {"id": data["size"], "name": data.get("name", data["size"]), "params": data["params"]}
    try:
        SizeEntry.model_validate(entry)
    except ValidationError as e:
        raise ValueError(str(e)) from e
    path = _size_file_path(type_id, size_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    reload_all()
    return path


def create_size_config(type_id: str, size_id: str, name: str, params: dict) -> Path:
    """
    新建一个尺码配置文件（允许新建类型）。

    Args:
        type_id: 所属类型（已存在则在其下加尺码；不存在则新建类型）
        size_id: 新尺码 id（须在类型内唯一，ASCII）
        name: 显示名
        params: 印前参数 dict

    Returns:
        新建文件路径

    Raises:
        ValueError: type_id/size_id 非 ASCII / size_id 已存在 / 校验失败
    """
    idx = _scan_prepress()
    if type_id in idx and size_id in idx[type_id]:
        raise ValueError(f"尺码已存在: {type_id}/{size_id}")
    data = {"type": type_id, "size": size_id, "name": name, "params": params}
    entry = {"id": size_id, "name": name, "params": params}
    # 用 TypeEntry 整体校验：type_id ASCII + size_id ASCII + params 全量
    try:
        TypeEntry(id=type_id, name=type_id, sizes=[SizeEntry.model_validate(entry)])
    except ValidationError as e:
        raise ValueError(str(e)) from e
    path = PREPRESS_DIR / f"{type_id}_{size_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    reload_all()
    return path


def delete_size_config(type_id: str, size_id: str) -> None:
    """
    删除某尺码配置文件。

    Raises:
        ValueError: 尺码不存在 / 该类型仅剩此一个尺码（不允许删空类型）
    """
    idx = _scan_prepress()
    if type_id not in idx or size_id not in idx[type_id]:
        raise ValueError(f"尺码不存在: {type_id}/{size_id}")
    if len(idx[type_id]) <= 1:
        raise ValueError(f"类型 {type_id} 仅剩此尺码，不允许删除（类型至少需 1 个尺码）")
    path = PREPRESS_DIR / idx[type_id][size_id]["file"]
    path.unlink()
    reload_all()
