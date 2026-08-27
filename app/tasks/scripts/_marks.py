"""标记层绘制：裁切线、拉链标记线、文字标记。

每类标记生成一个独立 RGBA 层（画布像素尺寸，透明背景），未启用的返回 None。
图层名限 ASCII（psd-tools 限制）。

字段定义见 docs/04-预检与生成参数.md §3.4。
"""
from __future__ import annotations

from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from ._canvas import CanvasPx, mm_to_px


def _color_tuple(name: str) -> tuple[int, int, int, int]:
    """颜色名转 RGBA。"""
    if name == "black":
        return (0, 0, 0, 255)
    if name == "white":
        return (255, 255, 255, 255)
    if name == "red":
        return (255, 0, 0, 255)
    # 兜底：黑色
    return (0, 0, 0, 255)


def _draw_line(
    draw: ImageDraw.ImageDraw,
    p1: tuple[int, int],
    p2: tuple[int, int],
    fill: tuple,
    width: int,
    dashed: bool = False,
    dash_px: int = 0,
    gap_px: int = 0,
) -> None:
    """
    画直线，支持虚线。

    虚线沿 p1→p2 方向分段绘制：dash_px 实线 + gap_px 间隙交替。
    实线模式直接 draw.line。

    Args:
        draw: ImageDraw 对象
        p1 / p2: 线段端点
        fill: 颜色
        width: 线宽（像素）
        dashed: 是否虚线
        dash_px / gap_px: 虚线段长与间隙（像素）
    """
    if not dashed or dash_px <= 0 or gap_px <= 0:
        draw.line([p1, p2], fill=fill, width=width)
        return

    x1, y1 = p1
    x2, y2 = p2
    dx = x2 - x1
    dy = y2 - y1
    total = (dx * dx + dy * dy) ** 0.5
    if total <= 0:
        return
    ux, uy = dx / total, dy / total
    pos = 0.0
    while pos < total:
        seg_end = min(pos + dash_px, total)
        draw.line(
            [(x1 + ux * pos, y1 + uy * pos),
             (x1 + ux * seg_end, y1 + uy * seg_end)],
            fill=fill, width=width,
        )
        pos = seg_end + gap_px


def make_crop_marks_layer(
    canvas: CanvasPx, width_mm: float, height_mm: float, crop_marks, dpi: int
) -> Optional[Image.Image]:
    """
    生成裁切线层：成品四角各画 L 形线。

    Args:
        canvas: 画布像素几何
        width_mm / height_mm: 成品尺寸（不含出血）
        crop_marks: config.prepress.CropMarks 对象
        dpi: 分辨率

    Returns:
        RGBA Image（画布尺寸），未启用返回 None
    """
    if not crop_marks.enabled:
        return None

    layer = Image.new("RGBA", (canvas.width_px, canvas.height_px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    color = _color_tuple(crop_marks.color)
    line_w = max(1, mm_to_px(crop_marks.width_mm, dpi))
    length = mm_to_px(crop_marks.length_mm, dpi)
    offset = mm_to_px(crop_marks.offset_mm, dpi)
    dashed = crop_marks.dashed
    dash_px = mm_to_px(crop_marks.dash_length_mm, dpi)
    gap_px = mm_to_px(crop_marks.gap_length_mm, dpi)

    # 画布坐标系：成品矩形 = 画布减去四周出血
    bx = canvas.bleed_px
    by = canvas.bleed_px
    bw = canvas.width_px - 2 * canvas.bleed_px
    bh = canvas.height_px - 2 * canvas.bleed_px

    # 四角 L 形线，朝外（出血方向）
    # 左上
    _draw_line(draw, (bx - offset, by), (bx - offset - length, by), color, line_w, dashed, dash_px, gap_px)
    _draw_line(draw, (bx, by - offset), (bx, by - offset - length), color, line_w, dashed, dash_px, gap_px)
    # 右上
    rx = bx + bw
    _draw_line(draw, (rx + offset, by), (rx + offset + length, by), color, line_w, dashed, dash_px, gap_px)
    _draw_line(draw, (rx, by - offset), (rx, by - offset - length), color, line_w, dashed, dash_px, gap_px)
    # 左下
    by2 = by + bh
    _draw_line(draw, (bx - offset, by2), (bx - offset - length, by2), color, line_w, dashed, dash_px, gap_px)
    _draw_line(draw, (bx, by2 + offset), (bx, by2 + offset + length), color, line_w, dashed, dash_px, gap_px)
    # 右下
    _draw_line(draw, (rx + offset, by2), (rx + offset + length, by2), color, line_w, dashed, dash_px, gap_px)
    _draw_line(draw, (rx, by2 + offset), (rx, by2 + offset + length), color, line_w, dashed, dash_px, gap_px)

    return layer


def make_zipper_marks_layer(
    canvas: CanvasPx, width_mm: float, height_mm: float, zipper, dpi: int
) -> Optional[Image.Image]:
    """
    生成拉链标记线层：在某侧均匀排布短标记线。

    Args:
        canvas: 画布像素几何
        width_mm / height_mm: 成品尺寸
        zipper: config.prepress.ZipperMarks 对象
        dpi: 分辨率

    Returns:
        RGBA Image（画布尺寸），未启用返回 None
    """
    if not zipper.enabled:
        return None

    layer = Image.new("RGBA", (canvas.width_px, canvas.height_px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    color = _color_tuple(zipper.color)
    line_w = max(1, mm_to_px(zipper.line_width_mm, dpi))
    length = mm_to_px(zipper.length_mm, dpi)
    offset = mm_to_px(zipper.offset_mm, dpi)

    span = mm_to_px(zipper.span_mm, dpi)
    pitch = mm_to_px(zipper.pitch_mm, dpi)
    count = round(span / pitch) + 1 if pitch > 0 else 1

    # 画布坐标系：矩形 = 整个画布
    bx = 0
    by = 0
    bw = canvas.width_px
    bh = canvas.height_px

    # 沿边方向的总跨度（像素）
    total_span_px = (count - 1) * pitch

    # 计算沿边方向的起点
    if zipper.side in ("left", "right"):
        edge_len = bh  # 沿垂直方向排布
    else:
        edge_len = bw  # 沿水平方向排布

    if zipper.alignment == "start":
        start = 0
    elif zipper.alignment == "end":
        start = edge_len - total_span_px
    elif zipper.alignment == "distribute":
        # 均匀铺满整边
        if count > 1:
            pitch_actual = edge_len / (count - 1)
        else:
            pitch_actual = 0
        start = 0
    else:  # center
        start = (edge_len - total_span_px) // 2

    for i in range(count):
        if zipper.alignment == "distribute" and count > 1:
            pos_along = round(start + i * pitch_actual)
        else:
            pos_along = start + i * pitch

        # 画布坐标系：offset=距画布边的偏移（0=贴边），标记线在画布内侧
        if zipper.side == "left":
            x = bx + offset
            y1 = by + pos_along
            y2 = by + pos_along
            _draw_line(draw, (x, y1), (x + length, y2), color, line_w)
        elif zipper.side == "right":
            # 贴右边缘内侧：x = bw - 1 - offset，向内延伸 length
            x = bx + bw - 1 - offset
            y1 = by + pos_along
            y2 = by + pos_along
            _draw_line(draw, (x, y1), (x - length, y2), color, line_w)
        elif zipper.side == "top":
            y = by + offset
            x1 = bx + pos_along
            x2 = bx + pos_along
            _draw_line(draw, (x1, y), (x2, y + length), color, line_w)
        elif zipper.side == "bottom":
            y = by + bh - 1 - offset
            x1 = bx + pos_along
            x2 = bx + pos_along
            _draw_line(draw, (x1, y), (x2, y - length), color, line_w)

    return layer


def _load_font(font_size_pt: float, dpi: int) -> ImageFont.ImageFont:
    """加载字体。优先 CJK 字体（中文需要），其次西文，找不到用默认。"""
    size_px = max(8, round(font_size_pt * dpi / 72))
    # CJK 优先：微软雅黑（Windows）/ 思源（Linux）；其次西文 arial / dejavu
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size_px)
        except Exception:
            continue
    return ImageFont.load_default()


def make_text_marks_layer(
    canvas: CanvasPx, text_marks, dpi: int
) -> Optional[Image.Image]:
    """
    生成文字标记层。

    Args:
        canvas: 画布像素几何
        text_marks: config.prepress.TextMarks 对象
        dpi: 分辨率

    Returns:
        RGBA Image（画布尺寸），未启用返回 None
    """
    if not text_marks.enabled:
        return None

    layer = Image.new("RGBA", (canvas.width_px, canvas.height_px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    color = _color_tuple(text_marks.color)
    font = _load_font(text_marks.font_size_pt, dpi)

    for item in text_marks.items:
        # 画布坐标系：x/y 相对画布左上角（0,0 = 画布左上角 = 图片左上角）
        x = mm_to_px(item.x_mm, dpi)
        y = mm_to_px(item.y_mm, dpi)
        if item.rotation != 0:
            # 旋转：先画到临时层再 rotate paste
            tmp = Image.new("RGBA", (canvas.width_px, canvas.height_px), (0, 0, 0, 0))
            tmp_draw = ImageDraw.Draw(tmp)
            tmp_draw.text((x, y), item.text, fill=color, font=font)
            tmp = tmp.rotate(item.rotation, expand=False, fillcolor=(0, 0, 0, 0))
            layer.alpha_composite(tmp)
        else:
            draw.text((x, y), item.text, fill=color, font=font)

    return layer


def make_border_marks_layer(
    canvas: CanvasPx, border_marks, dpi: int
) -> Optional[Image.Image]:
    """
    生成虚线边框层（矩形虚线框，可作裁剪线）。

    位置/尺寸由 border_marks 的 x/y/width/height 决定，相对画布左上角（含出血偏移）。

    Args:
        canvas: 画布像素几何
        border_marks: config.prepress.BorderMarks 对象
        dpi: 分辨率

    Returns:
        RGBA Image（画布尺寸），未启用返回 None
    """
    if not border_marks.enabled:
        return None

    layer = Image.new("RGBA", (canvas.width_px, canvas.height_px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    color = _color_tuple(border_marks.color)
    line_w = max(1, mm_to_px(border_marks.width_mm_line, dpi))
    dash_px = mm_to_px(border_marks.dash_length_mm, dpi)
    gap_px = mm_to_px(border_marks.gap_length_mm, dpi)

    # 画布坐标系：x/y 相对画布左上角（0,0 = 画布左上角 = 图片左上角）
    # 内描边：线完全在矩形内部，向内偏移 line_w//2
    inset = line_w // 2
    x1 = mm_to_px(border_marks.x_mm, dpi) + inset
    y1 = mm_to_px(border_marks.y_mm, dpi) + inset
    x2 = x1 + mm_to_px(border_marks.width_mm, dpi) - 1 - 2 * inset
    y2 = y1 + mm_to_px(border_marks.height_mm, dpi) - 1 - 2 * inset

    # 四条边虚线（内描边，不超出配置的 width/height 范围）
    _draw_line(draw, (x1, y1), (x2, y1), color, line_w, True, dash_px, gap_px)  # 上
    _draw_line(draw, (x1, y2), (x2, y2), color, line_w, True, dash_px, gap_px)  # 下
    _draw_line(draw, (x1, y1), (x1, y2), color, line_w, True, dash_px, gap_px)  # 左
    _draw_line(draw, (x2, y1), (x2, y2), color, line_w, True, dash_px, gap_px)  # 右

    return layer
