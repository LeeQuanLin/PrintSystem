"""文件库高层：入库 / 检索 / 清理。

入库 = 落盘原图 + 生成缩略图 + 提取元数据 + 写 DB。
设计见 docs/07-文件存储.md。
"""
from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from PIL import Image
from psd_tools import PSDImage

from ulid import ULID

from app.config import get_storage
from app.storage import db

# 家纺印前图普遍超 PIL 默认 89M 像素上限，放开
Image.MAX_IMAGE_PIXELS = None

_FMT_MAP = {".png": "png", ".jpg": "jpg", ".jpeg": "jpg", ".tif": "tif", ".tiff": "tif", ".psd": "psd"}


@dataclass
class ImageRecord:
    """文件库一条记录（与 DB 行同构）。"""
    id: str
    original_name: str
    stored_name: str
    format: str
    width_px: Optional[int]
    height_px: Optional[int]
    dpi: Optional[int]
    mode: Optional[str]
    size_bytes: Optional[int]
    source: str
    ref_type: Optional[str]
    ref_size: Optional[str]
    task_id: Optional[str]

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ImageRecord":
        return cls(
            id=row["id"],
            original_name=row["original_name"],
            stored_name=row["stored_name"],
            format=row["format"],
            width_px=row.get("width_px"),
            height_px=row.get("height_px"),
            dpi=row.get("dpi"),
            mode=row.get("mode"),
            size_bytes=row.get("size_bytes"),
            source=row["source"],
            ref_type=row.get("ref_type"),
            ref_size=row.get("ref_size"),
            task_id=row.get("task_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---- 路径辅助 ----

def _images_dir() -> Path:
    return get_storage().images_dir


def image_dir(image_id: str) -> Path:
    return _images_dir() / image_id


def original_path(image_id: str, stored_name: str) -> Path:
    return image_dir(image_id) / stored_name


def thumb_path(image_id: str) -> Path:
    return image_dir(image_id) / "thumb.webp"


# ---- 元数据 / 缩略图 ----

def _extract_meta(src: Path, fmt: str) -> dict[str, Any]:
    """提取宽高 / dpi / mode / size_bytes。"""
    size_bytes = src.stat().st_size
    if fmt == "psd":
        psd = PSDImage.open(src)
        return {
            "width_px": psd.size[0],
            "height_px": psd.size[1],
            "dpi": None,  # psd-tools 不直接暴露 dpi
            "mode": _psd_mode(psd),
            "size_bytes": size_bytes,
        }
    img = Image.open(src)
    dpi = img.info.get("dpi")
    return {
        "width_px": img.size[0],
        "height_px": img.size[1],
        "dpi": int(dpi[0]) if dpi else None,
        "mode": img.mode,
        "size_bytes": size_bytes,
    }


def _psd_mode(psd: PSDImage) -> str:
    """PSD 色彩模式转可读字符串。"""
    return {
        "RGB": "RGB",
        "CMYK": "CMYK",
        "GRAYSCALE": "L",
        "GRAYSCALE16": "L",
        "RGB16": "RGB",
        "CMYK16": "CMYK",
    }.get(psd.color_mode.name if hasattr(psd.color_mode, "name") else str(psd.color_mode),
          str(psd.color_mode))


def _make_thumb(src: Path, fmt: str, dst: Path, max_size_px: int, quality: int) -> None:
    """生成缩略图。PSD 用复合平面，普通图用 Pillow。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "psd":
        psd = PSDImage.open(src)
        composited = psd.composite()
        if composited.mode != "RGBA":
            composited = composited.convert("RGBA")
        bg = Image.new("RGBA", composited.size, (255, 255, 255, 255))
        bg.alpha_composite(composited)
        rgb = bg.convert("RGB")
        rgb.thumbnail((max_size_px, max_size_px), Image.LANCZOS)
        rgb.save(dst, format="WEBP", quality=quality)
        return
    img = Image.open(src)
    img.draft(None, (max_size_px, max_size_px))  # 大图降采样提示
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    img.thumbnail((max_size_px, max_size_px), Image.LANCZOS)
    img.save(dst, format="WEBP", quality=quality)


# ---- 入库 ----

def ingest_file(
    src_path: str | Path,
    *,
    original_name: str,
    source: str,
    fmt: Optional[str] = None,
    ref_type: Optional[str] = None,
    ref_size: Optional[str] = None,
    task_id: Optional[str] = None,
    thumb_src: Optional[str | Path] = None,
    move: bool = True,
) -> ImageRecord:
    """
    入库一个文件：落盘原图 + 缩略图 + 元数据 + DB 行。

    Args:
        src_path: 源文件路径
        original_name: 上传时的原始文件名（记入元数据）
        source: 来源 upload / prepress / impose
        fmt: 格式；None 则按扩展名推断
        ref_type / ref_size / task_id: 关联信息
        thumb_src: 已有缩略图路径；给定则 move 进库，否则从 src 生成
        move: True 移动 src，False 复制
    """
    src = Path(src_path)
    ext = src.suffix.lower()
    fmt = fmt or _FMT_MAP.get(ext, ext.lstrip("."))
    image_id = str(ULID())
    stored_name = f"original.{fmt}"
    out_dir = image_dir(image_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    dst = out_dir / stored_name
    if move:
        shutil.move(str(src), str(dst))
    else:
        shutil.copy2(str(src), str(dst))

    # 缩略图
    thumb_cfg = get_storage().thumbnail
    tpath = thumb_path(image_id)
    if thumb_src is not None:
        shutil.move(str(thumb_src), str(tpath))
    else:
        _make_thumb(dst, fmt, tpath, thumb_cfg.max_size_px, thumb_cfg.quality)

    meta = _extract_meta(dst, fmt)
    row = {
        "id": image_id,
        "original_name": original_name,
        "stored_name": stored_name,
        "format": fmt,
        "ref_type": ref_type,
        "ref_size": ref_size,
        "task_id": task_id,
        "source": source,
        **meta,
    }
    db.insert_image(row)
    return ImageRecord.from_row(row)


# ---- 检索 ----

def get(image_id: str) -> Optional[ImageRecord]:
    row = db.get_image(image_id)
    return ImageRecord.from_row(row) if row else None


def list(
    *,
    source: Optional[str] = None,
    ref_type: Optional[str] = None,
    ref_size: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[ImageRecord]:
    rows = db.list_images(
        source=source, ref_type=ref_type, ref_size=ref_size,
        q=q, limit=limit, offset=offset,
    )
    return [ImageRecord.from_row(r) for r in rows]


# ---- 清理 ----

def delete(image_id: str) -> bool:
    """删除文件库一条：删文件夹 + DB 行。返回是否删了记录。"""
    rec = get(image_id)
    if rec is None:
        return False
    db.delete_image(image_id)
    d = image_dir(image_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    return True
