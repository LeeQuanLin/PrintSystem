"""排版标记层（pyvips draw_line）。

裁切线：每个槽位四角画 L 形两条短线，朝槽位外侧偏移。
套准标记：画布四角各一个十字标，位于 margin 内。
标记本身 alpha=255（实色黑色）。

相邻槽位共享边的裁切线本期不去重（05b §13.4 开放项，重叠重绘无害）。
字段定义见 docs/05b-排版规范.md §7。
"""
from __future__ import annotations

from app._vendor import load_vips

load_vips()

import pyvips

from ._canvas import mm_to_px

# 黑色实色 RGBA
_INK = [0, 0, 0, 255]


def _line(img: pyvips.Image, x1: int, y1: int, x2: int, y2: int) -> pyvips.Image:
    """在 img 上画一条 1px 黑色实线（返回新图）。"""
    return img.draw_line(_INK, x1, y1, x2, y2)


def draw_crop_marks(canvas, slots, marks_cfg, dpi: int) -> pyvips.Image:
    """
    在画布上绘制所有槽位的裁切线（L 形角标）。

    每槽位四角各两条短线（水平+垂直），朝外侧偏移 crop_mark_offset_mm，
    线长 crop_mark_length_mm。

    Args:
        canvas: pyvips.Image（画布，4 band RGBA）
        slots: list[SlotRect]
        marks_cfg: config.impose.ImposeMarks
        dpi: 分辨率
    """
    if not marks_cfg.crop_marks:
        return canvas

    offset = mm_to_px(marks_cfg.crop_mark_offset_mm, dpi)
    length = mm_to_px(marks_cfg.crop_mark_length_mm, dpi)
    img = canvas

    for s in slots:
        left, top = s.x_px, s.y_px
        right = s.x_px + s.width_px - 1
        bottom = s.y_px + s.height_px - 1
        # 四角：(cx, cy, sx, sy) —— sx/sy 为外法线方向符号
        corners = [
            (left, top, -1, -1),       # 左上
            (right, top, 1, -1),       # 右上
            (left, bottom, -1, 1),     # 左下
            (right, bottom, 1, 1),     # 右下
        ]
        for cx, cy, sx, sy in corners:
            # 角外参考点
            px = cx + sx * offset
            py = cy + sy * offset
            # 水平线（沿 x 外延）
            img = _line(img, px, py, px + sx * length, py)
            # 垂直线（沿 y 外延）
            img = _line(img, px, py, px, py + sy * length)

    return img


def draw_registration_marks(canvas, marks_cfg, canvas_cfg, gutters, dpi: int) -> pyvips.Image:
    """
    在画布四角绘制套准十字标（位于 margin 内）。

    Args:
        canvas: pyvips.Image
        marks_cfg: config.impose.ImposeMarks
        canvas_cfg: config.impose.Canvas（画布 mm 尺寸）
        gutters: config.impose.Gutters（margin_mm）
        dpi: 分辨率
    """
    if not marks_cfg.registration_marks:
        return canvas

    w_px = canvas.width
    h_px = canvas.height
    # 十字中心位于 margin 条带中央；margin 不足时退到画布角
    half_margin = mm_to_px(gutters.margin_mm / 2, dpi)
    arm = mm_to_px(marks_cfg.crop_mark_length_mm, dpi)
    img = canvas

    centers = [
        (half_margin, half_margin),
        (w_px - 1 - half_margin, half_margin),
        (half_margin, h_px - 1 - half_margin),
        (w_px - 1 - half_margin, h_px - 1 - half_margin),
    ]
    for cx, cy in centers:
        img = _line(img, cx - arm, cy, cx + arm, cy)  # 横
        img = _line(img, cx, cy - arm, cx, cy + arm)  # 竖

    return img
