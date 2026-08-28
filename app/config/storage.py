"""存储配置：模型 + 加载。

字段定义见 docs/07-文件存储.md §4.2。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs" / "storage" / "storage.json"


class LibraryCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = "data/library"
    db_filename: str = "library.db"


class ThumbnailCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["webp"] = "webp"
    max_size_px: int = Field(default=400, gt=0)
    quality: int = Field(default=80, ge=1, le=100)


class TasksCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_concurrency: int = Field(default=2, ge=1)


class StorageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    library: LibraryCfg = Field(default_factory=LibraryCfg)
    thumbnail: ThumbnailCfg = Field(default_factory=ThumbnailCfg)
    tasks: TasksCfg = Field(default_factory=TasksCfg)

    @property
    def db_path(self) -> Path:
        """library.db 完整路径（相对项目根）。"""
        return ROOT / self.library.path / self.library.db_filename

    @property
    def images_dir(self) -> Path:
        """图片存放根目录。"""
        return ROOT / self.library.path / "images"


def load(path: Path = CONFIG_PATH) -> StorageConfig:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return StorageConfig.model_validate(data)


def save_tasks_concurrency(max_concurrency: int) -> int:
    """
    修改任务并发上限并落盘。

    仅改 tasks.max_concurrency，其余字段保持不变。校验由 TasksCfg（ge=1）保证。
    调用方需自行 reload_all() 使新值对调度器立即生效。

    Args:
        max_concurrency: 新并发上限（≥1）

    Returns:
        写入后的值
    """
    cfg = load()
    cfg.tasks = TasksCfg(max_concurrency=max_concurrency)
    data = cfg.model_dump()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return cfg.tasks.max_concurrency
