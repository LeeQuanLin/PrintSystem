"""排版画布与流式布局几何。

图件按原始像素尺寸（旋转后）行优先流式铺排：从画布左上角 (0,0) 开始，
沿 x 方向依次摆放，当前行剩余宽度放不下下一张时换行。无缩放、无间距、无边距。
"""
from __future__ import annotations

from dataclasses import dataclass

from ._canvas import mm_to_px


@dataclass(frozen=True)
class ImposeCanvas:
    """排版画布像素几何。"""

    width_px: int
    height_px: int
    dpi: int


@dataclass(frozen=True)
class Placement:
    """一个图件在画布上的放置矩形（原始尺寸，不缩放）。"""

    index: int
    x_px: int  # 左上角 x
    y_px: int  # 左上角 y
    width_px: int  # 图件宽（旋转后）
    height_px: int  # 图件高（旋转后）


def compute_impose_canvas(canvas_cfg, dpi: int | None = None) -> ImposeCanvas:
    """
    计算排版画布像素尺寸。

    Args:
        canvas_cfg: config.impose.Canvas（width_mm / height_mm / dpi）
        dpi: 可选，覆盖 canvas_cfg.dpi
    """
    d = dpi or canvas_cfg.dpi
    w = mm_to_px(canvas_cfg.width_mm, d)
    h = mm_to_px(canvas_cfg.height_mm, d)
    return ImposeCanvas(width_px=w, height_px=h, dpi=d)


def compute_flow_layout(
    image_sizes: list[tuple[int, int]],
    canvas_px: ImposeCanvas,
) -> list[Placement]:
    """
    按图件原始尺寸（旋转后）行优先流式铺排。

    从 (0,0) 开始，沿 x 依次摆放；当前行剩余宽度放不下下一张时换行（y 累加当前行最大高度）。
    无缩放、无间距、无边距。

    Args:
        image_sizes: 每个图件旋转后的 (width_px, height_px)
        canvas_px: 画布像素几何

    Returns:
        list[Placement]，与 image_sizes 等长

    Raises:
        ValueError: 任一图件（含放置后）超出画布边界
    """
    placements: list[Placement] = []
    x = 0
    y = 0
    row_h = 0  # 当前行已放置图件的最大高度

    for i, (w, h) in enumerate(image_sizes):
        # 单张图就比画布宽：尝试换行
        if x + w > canvas_px.width_px and x > 0:
            # 换行
            y += row_h
            x = 0
            row_h = 0
        # 放置
        px, py = x, y
        placements.append(Placement(index=i, x_px=px, y_px=py, width_px=w, height_px=h))
        x += w
        row_h = max(row_h, h)

        # 超出校验
        if px + w > canvas_px.width_px:
            raise ValueError(
                f"图件 {i} 宽度 {w}px 超出画布宽 {canvas_px.width_px}px（放置于 x={px}）"
            )
        if py + h > canvas_px.height_px:
            raise ValueError(
                f"图件 {i} 高度 {h}px 超出画布高 {canvas_px.height_px}px（放置于 y={py}）"
            )

    return placements

