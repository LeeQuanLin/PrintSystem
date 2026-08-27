"""pytest 公共 fixtures。"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app._vendor import load_vips
from app.config import storage as sc


@pytest.fixture(scope="session", autouse=True)
def vips_loaded() -> None:
    """会话级自动加载 libvips DLL（开发态）。"""
    load_vips()


@pytest.fixture(autouse=True)
def isolate_library(tmp_path, monkeypatch):
    """每个测试用独立临时文件库，避免污染真实 data/library。

    替换 db/store 模块里的 get_storage 引用为指向 tmp_path 的配置。
    同时清印前配置扫描缓存，防止上个测试的 monkeypatch 残留。
    """
    import app.config as _cfg
    _cfg._scan_prepress.cache_clear()
    cfg = sc.StorageConfig(
        library=sc.LibraryCfg(path=str(tmp_path / "library")),
        thumbnail=sc.ThumbnailCfg(),
        tasks=sc.TasksCfg(),
    )
    import app.storage.db as _db
    import app.storage.store as _store
    monkeypatch.setattr(_db, "get_storage", lambda: cfg)
    monkeypatch.setattr(_store, "get_storage", lambda: cfg)


@pytest.fixture
def sample_image(tmp_path) -> Path:
    """造一张测试图（600×600 条纹），返回路径。"""
    img = Image.new("RGB", (600, 600), (200, 180, 255))
    draw = ImageDraw.Draw(img)
    for i in range(0, 600, 80):
        draw.rectangle([i, 0, i + 40, 600], fill=(255, 120, 100))
    path = tmp_path / "sample.png"
    img.save(path)
    return path


@pytest.fixture
def small_config() -> Path:
    """小尺寸配置路径（100×100mm）。"""
    return Path("configs/prepress/test_small.json")


@pytest.fixture
def real_config() -> Path:
    """真实尺码配置路径（152×202cm）。"""
    return Path("configs/prepress/test_152x202.json")
