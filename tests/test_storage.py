"""文件库 store / db 测试。"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from app._vendor import load_vips
from app.storage import store
from app.storage import db


@pytest.fixture(autouse=True)
def _vips():
    load_vips()


def _make_png(path: Path, w: int = 800, h: int = 600) -> Path:
    Image.new("RGB", (w, h), (120, 200, 80)).save(path)
    return path


def test_db_insert_get_list_delete(tmp_path):
    """db 层增查删。"""
    row = {
        "id": "testid1",
        "original_name": "a.png",
        "stored_name": "original.png",
        "format": "png",
        "width_px": 10, "height_px": 20, "dpi": 300, "mode": "RGB",
        "size_bytes": 99, "source": "upload",
        "ref_type": None, "ref_size": None, "task_id": None,
    }
    db.insert_image(row)
    got = db.get_image("testid1")
    assert got is not None
    assert got["original_name"] == "a.png"
    assert got["width_px"] == 10

    rows = db.list_images(source="upload")
    assert any(r["id"] == "testid1" for r in rows)

    assert db.delete_image("testid1") is True
    assert db.get_image("testid1") is None
    assert db.delete_image("nope") is False


def test_ingest_upload_image(tmp_path):
    """普通图入库：落盘 + 缩略图 + 元数据。"""
    src = _make_png(tmp_path / "in.png", 1000, 700)
    rec = store.ingest_file(src, original_name="in.png", source="upload", move=True)
    assert rec.format == "png"
    assert rec.width_px == 1000
    assert rec.height_px == 700
    assert rec.mode == "RGB"
    assert rec.source == "upload"
    # 源已 move
    assert not src.exists()
    # 库内文件与缩略图存在
    assert store.original_path(rec.id, rec.stored_name).exists()
    assert store.thumb_path(rec.id).exists()
    # 可查回
    assert store.get(rec.id) is not None
    assert len(store.list(source="upload")) >= 1


def test_ingest_copy_keeps_source(tmp_path):
    """move=False 时保留源文件。"""
    src = _make_png(tmp_path / "keep.png")
    rec = store.ingest_file(src, original_name="keep.png", source="upload", move=False)
    assert src.exists()
    assert store.original_path(rec.id, rec.stored_name).exists()


def test_ingest_psd_with_thumb(tmp_path, sample_image):
    """PSD 入库：复用已有缩略图。"""
    from psd_tools import PSDImage
    from PIL import Image as PI

    # 造一个极简 PSD
    img = PI.new("RGBA", (200, 150), (10, 20, 30, 255))
    psd_path = tmp_path / "x.psd"
    from psd_tools import PSDImage as PSDImg
    psd = PSDImg.frompil(img)
    psd.save(psd_path)

    # 预造缩略图
    thumb = tmp_path / "t.webp"
    PI.new("RGB", (50, 50)).save(thumb, format="WEBP")

    rec = store.ingest_file(
        psd_path, original_name="x.psd", source="prepress",
        fmt="psd", ref_type="test", ref_size="small", task_id="tk1",
        thumb_src=thumb, move=True,
    )
    assert rec.format == "psd"
    assert rec.width_px == 200
    assert rec.ref_type == "test" and rec.ref_size == "small" and rec.task_id == "tk1"
    assert store.thumb_path(rec.id).exists()
    # 预造缩略图已 move 走
    assert not thumb.exists()


def test_delete_removes_files(tmp_path):
    """delete 删文件与 DB 行。"""
    src = _make_png(tmp_path / "d.png")
    rec = store.ingest_file(src, original_name="d.png", source="upload")
    assert store.delete(rec.id) is True
    assert not store.original_path(rec.id, rec.stored_name).exists()
    assert not store.thumb_path(rec.id).exists()
    assert store.get(rec.id) is None


def test_list_filters(tmp_path):
    """list 按 source/ref 过滤。"""
    s1 = _make_png(tmp_path / "u1.png")
    s2 = _make_png(tmp_path / "u2.png")
    r1 = store.ingest_file(s1, original_name="u1.png", source="upload")
    r2 = store.ingest_file(s2, original_name="u2.png", source="prepress", ref_type="t")
    ups = store.list(source="upload")
    assert all(r.source == "upload" for r in ups)
    assert any(r.id == r1.id for r in ups)
    pre = store.list(source="prepress")
    assert any(r.id == r2.id for r in pre)
