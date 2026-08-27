"""PSD 分层组装与缩略图生成。

组装顺序：背景层（PSDImage.new 自带）→ zones 列表顺序逐层 → 标记层。
图层名限 ASCII（psd-tools mac_roman 编码限制）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image
from psd_tools import PSDImage
import psd_tools.psd.image_resources as ir

from ._canvas import CanvasPx


def _set_dpi(psd: PSDImage, dpi: int) -> None:
    """
    写入 PSD 的 DPI 元数据（ResolutionInfo，resource id 1005）。

    psd-tools 默认不写 DPI，Photoshop 读到 72。此处显式设为指定值。
    PSD 规范中 h_res/v_res 为 16.16 定点数，需 dpi << 16。
    unit=1 表示 pixels/inch。

    Args:
        psd: PSDImage 对象
        dpi: 分辨率（如 150）
    """
    fixed = dpi << 16
    res = ir.ResoulutionInfo(fixed, 1, 0, fixed, 1, 0)
    psd.image_resources[1005] = ir.ImageResource(b"8BIM", 1005, "", res.tobytes())


def build_psd(
    canvas: CanvasPx,
    background,
    solid_layers: list[tuple[str, Image.Image]],
    zone_layers: list[tuple[str, Image.Image]],
    mark_layers: list[tuple[str, Image.Image]],
    dpi: int = 150,
) -> PSDImage:
    """
    组装分层 PSD。

    层序：背景层（PSDImage.new 自带）→ 独立纯色层 → zones 列表顺序逐层 → 标记层。
    所有传入的 layer 必须已是画布像素尺寸（调用方负责把 zone 层按其 x/y 坐标
    放置到画布尺寸的透明层上）。

    Args:
        canvas: 画布像素几何
        background: config.prepress.Background 对象（可能为 None）
        solid_layers: [(name, RGBA Image 画布尺寸)]，独立纯色层，位于 background 与 zones 之间
        zone_layers: [(name, RGBA Image 画布尺寸)]，按配置顺序
        mark_layers: [(name, RGBA Image 画布尺寸)]
        dpi: 写入 PSD 的分辨率

    Returns:
        PSDImage
    """
    w, h = canvas.width_px, canvas.height_px

    # 背景层
    if background is not None and background.enabled:
        bg_color = tuple(background.fill_color) + (255,)
        psd = PSDImage.new(mode="RGBA", size=(w, h), color=bg_color)
    else:
        psd = PSDImage.new(mode="RGBA", size=(w, h), color=(0, 0, 0, 0))

    _set_dpi(psd, dpi)

    for name, layer in solid_layers + zone_layers + mark_layers:
        if layer.mode != "RGBA":
            layer = layer.convert("RGBA")
        if layer.size != (w, h):
            raise ValueError(
                f"层 {name} 尺寸 {layer.size} 与画布 {(w, h)} 不符，调用方需先放置"
            )
        psd.append(psd.create_pixel_layer(layer, name=name))

    return psd


def save_psd(psd: PSDImage, path: str | Path) -> None:
    """保存分层 PSD 到文件。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    psd.save(path)


def save_flat(psd: PSDImage, path: str | Path, fmt: str, dpi: int) -> None:
    """
    把 PSD 平面合成后保存为 TIF 或 PNG（不分层）。

    Args:
        psd: PSDImage 对象
        path: 输出路径
        fmt: "tif" 或 "png"
        dpi: 分辨率，写入文件元数据
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    composited = psd.composite()
    if composited.mode != "RGBA":
        composited = composited.convert("RGBA")
    # 白底合成（alpha 拍平），TIF/PNG 不保留透明
    bg = Image.new("RGBA", composited.size, (255, 255, 255, 255))
    bg.alpha_composite(composited)
    rgb = bg.convert("RGB")

    if fmt == "tif":
        # dpi 转 pixels/cm（PIL TIF 用 cm）或直接用 dpi tuple
        rgb.save(path, format="TIFF", dpi=(dpi, dpi), compression="deflate")
    elif fmt == "png":
        rgb.save(path, format="PNG", dpi=(dpi, dpi))
    else:
        raise ValueError(f"不支持的平面格式: {fmt}")


def generate_thumbnail(
    psd_path: str | Path,
    thumb_path: str | Path,
    max_size_px: int = 400,
    quality: int = 80,
) -> None:
    """
    从 PSD 文件合成平面生成 webp 缩略图。

    Args:
        psd_path: PSD 文件路径
        thumb_path: 缩略图输出路径
        max_size_px: 最长边像素
        quality: webp 质量
    """
    psd = PSDImage.open(psd_path)
    generate_thumbnail_from_psd(psd, thumb_path, max_size_px, quality)


def generate_thumbnail_from_psd(
    psd: PSDImage,
    thumb_path: str | Path,
    max_size_px: int = 400,
    quality: int = 80,
) -> None:
    """
    从 PSDImage 对象合成平面生成 webp 缩略图。

    Args:
        psd: PSDImage 对象
        thumb_path: 缩略图输出路径
        max_size_px: 最长边像素
        quality: webp 质量
    """
    composited = psd.composite()
    if composited.mode != "RGBA":
        composited = composited.convert("RGBA")
    # 白底合成（alpha 拍平）
    bg = Image.new("RGBA", composited.size, (255, 255, 255, 255))
    bg.alpha_composite(composited)
    rgb = bg.convert("RGB")
    rgb.thumbnail((max_size_px, max_size_px), Image.LANCZOS)

    thumb_path = Path(thumb_path)
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    rgb.save(thumb_path, format="WEBP", quality=quality)
