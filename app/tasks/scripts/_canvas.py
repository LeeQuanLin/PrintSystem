"""画布像素计算与 mm→px 坐标换算。

所有尺寸换算统一走这里，避免散落各处。DPI 转换：px = mm * dpi / 25.4。
"""
from __future__ import annotations

from dataclasses import dataclass


def mm_to_px(mm: float, dpi: int) -> int:
    """毫米转像素（四舍五入）。"""
    return round(mm * dpi / 25.4)


@dataclass(frozen=True)
class CanvasPx:
    """画布像素尺寸与出血。"""

    width_px: int
    height_px: int
    bleed_px: int


def compute_canvas(width_mm: float, height_mm: float, bleed_mm: float, dpi: int) -> CanvasPx:
    """
    计算画布像素尺寸（含出血四周）。

    Args:
        width_mm: 成品宽（毫米）
        height_mm: 成品高（毫米）
        bleed_mm: 出血量（毫米，四周一致）
        dpi: 分辨率

    Returns:
        CanvasPx
    """
    w = mm_to_px(width_mm + 2 * bleed_mm, dpi)
    h = mm_to_px(height_mm + 2 * bleed_mm, dpi)
    b = mm_to_px(bleed_mm, dpi)
    return CanvasPx(width_px=w, height_px=h, bleed_px=b)


@dataclass(frozen=True)
class ZonePx:
    """区域在画布上的像素几何。"""

    name: str
    x_px: int
    y_px: int
    width_px: int
    height_px: int


def zone_to_px(zone, dpi: int) -> ZonePx:
    """
    把配置中的 zone（mm 坐标）转为像素坐标。

    Args:
        zone: config.prepress.Zone 对象
        dpi: 分辨率

    Returns:
        ZonePx
    """
    return ZonePx(
        name=zone.name,
        x_px=mm_to_px(zone.x_mm, dpi),
        y_px=mm_to_px(zone.y_mm, dpi),
        width_px=mm_to_px(zone.width_mm, dpi),
        height_px=mm_to_px(zone.height_mm, dpi),
    )
