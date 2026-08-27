"""图片区与纯色区处理。

图片区：载入上传图 → fit_mode 适配 → 四角裁剪 → 微调（scale/rotation/offset）。
纯色区：手动色直接填充，或从来源图片区提取主色（dominant/average）填充。

字段定义见 docs/04-预检与生成参数.md §3.4。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageStat

from ._canvas import mm_to_px, zone_to_px


# ---------------------------------------------------------------------------
# 图片区
# ---------------------------------------------------------------------------


def load_source_image(image_path: str | Path) -> Image.Image:
    """载入上传图，转 RGBA。"""
    img = Image.open(image_path)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img


def fit_to_zone(
    src: Image.Image, w_px: int, h_px: int, fit_mode: str
) -> Image.Image:
    """
    按 fit_mode 把源图适配到 zone 像素尺寸。

    Args:
        src: 源图（RGBA）
        w_px / h_px: zone 像素宽高
        fit_mode: stretch / contain / cover

    Returns:
        RGBA Image，尺寸 w_px × h_px
    """
    if fit_mode == "stretch":
        return src.resize((w_px, h_px), Image.LANCZOS)

    if fit_mode == "contain":
        # 等比缩放到 zone 内，居中放到透明画布
        ratio = min(w_px / src.width, h_px / src.height)
        new_w = max(1, round(src.width * ratio))
        new_h = max(1, round(src.height * ratio))
        scaled = src.resize((new_w, new_h), Image.LANCZOS)
        canvas = Image.new("RGBA", (w_px, h_px), (0, 0, 0, 0))
        offset = ((w_px - new_w) // 2, (h_px - new_h) // 2)
        canvas.paste(scaled, offset, scaled)
        return canvas

    if fit_mode == "cover":
        # 等比缩放覆盖 zone，center 裁切
        ratio = max(w_px / src.width, h_px / src.height)
        new_w = max(1, round(src.width * ratio))
        new_h = max(1, round(src.height * ratio))
        scaled = src.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - w_px) // 2
        top = (new_h - h_px) // 2
        return scaled.crop((left, top, left + w_px, top + h_px))

    raise ValueError(f"未知 fit_mode: {fit_mode}")


def make_corner_mask(
    w_px: int, h_px: int, corner_crop, dpi: int
) -> Image.Image:
    """
    生成四角裁剪 alpha mask（L 模式，255=保留 / 0=裁掉）。

    Args:
        w_px / h_px: zone 像素尺寸
        corner_crop: config.prepress.CornerCrop 对象（可能为 None）
        dpi: 分辨率（mm 转 px 用）

    Returns:
        L 模式 Image，尺寸 w_px × h_px
    """
    mask = Image.new("L", (w_px, h_px), 255)

    if corner_crop is None:
        return mask

    draw = ImageDraw.Draw(mask)

    if corner_crop.style == "square":
        # 矩形缺角：四角各切一个正方形透明区（边长 chamfer_mm），形如纸盒展开图缺角
        c = mm_to_px(corner_crop.chamfer_mm, dpi)
        if c <= 0:
            return mask
        c = min(c, w_px // 2, h_px // 2)
        boxes = [
            (0, 0, c, c),                       # 左上
            (w_px - c, 0, w_px, c),             # 右上
            (0, h_px - c, c, h_px),             # 左下
            (w_px - c, h_px - c, w_px, h_px),   # 右下
        ]
        for box in boxes:
            draw.rectangle(box, fill=0)
        return mask

    if corner_crop.style == "rounded":
        radius = mm_to_px(corner_crop.radius_mm, dpi)
        radius = min(radius, w_px // 2, h_px // 2)
        if radius <= 0:
            return mask
        # 画白色圆角矩形到全黑 mask，再反转
        black = Image.new("L", (w_px, h_px), 0)
        d_black = ImageDraw.Draw(black)
        d_black.rounded_rectangle([0, 0, w_px - 1, h_px - 1], radius=radius, fill=255)
        return black

    if corner_crop.style == "chamfer":
        c = mm_to_px(corner_crop.chamfer_mm, dpi)
        if c <= 0:
            return mask
        c = min(c, w_px // 2, h_px // 2)
        # 四角各画一个三角形透明区
        triangles = [
            [(0, 0), (c, 0), (0, c)],               # 左上
            [(w_px, 0), (w_px - c, 0), (w_px, c)],   # 右上
            [(0, h_px), (c, h_px), (0, h_px - c)],   # 左下
            [(w_px, h_px), (w_px - c, h_px), (w_px, h_px - c)],  # 右下
        ]
        for tri in triangles:
            draw.polygon(tri, fill=0)
        return mask

    return mask


def apply_alpha_mask(img: Image.Image, mask: Image.Image) -> Image.Image:
    """把 L mask 应用到 RGBA 图的 alpha 通道。"""
    if img.size != mask.size:
        mask = mask.resize(img.size, Image.LANCZOS)
    r, g, b, _ = img.split()
    return Image.merge("RGBA", (r, g, b, mask))


def apply_transforms(
    fitted: Image.Image, zone, dpi: int
) -> Image.Image:
    """
    应用微调：scale → rotation → offset，输出 zone 像素尺寸 RGBA。

    Args:
        fitted: fit_mode 适配后的图（zone 像素尺寸）
        zone: config.prepress.Zone 对象
        dpi: 分辨率

    Returns:
        RGBA Image，zone 像素尺寸
    """
    w_px = mm_to_px(zone.width_mm, dpi)
    h_px = mm_to_px(zone.height_mm, dpi)

    # scale
    scaled = fitted
    if zone.scale != 1.0:
        new_w = max(1, round(fitted.width * zone.scale))
        new_h = max(1, round(fitted.height * zone.scale))
        scaled = fitted.resize((new_w, new_h), Image.LANCZOS)

    # rotation（中心轴，expand=False 保持尺寸）
    rotated = scaled
    if zone.rotation != 0:
        rotated = scaled.rotate(
            zone.rotation, resample=Image.BICUBIC, expand=False, fillcolor=(0, 0, 0, 0)
        )

    # offset：创建 zone 尺寸透明画布，居中 paste
    canvas = Image.new("RGBA", (w_px, h_px), (0, 0, 0, 0))
    offset_x = mm_to_px(zone.offset_x_mm, dpi)
    offset_y = mm_to_px(zone.offset_y_mm, dpi)
    pos_x = (w_px - rotated.width) // 2 + offset_x
    pos_y = (h_px - rotated.height) // 2 + offset_y
    canvas.paste(rotated, (pos_x, pos_y), rotated)
    return canvas


def process_image_zone(zone, image_path: str | Path, dpi: int) -> Image.Image:
    """
    处理图片区：载入 → fit → 四角裁剪 → 微调，输出 zone 像素尺寸 RGBA。

    Args:
        zone: config.prepress.Zone 对象（type=image）
        image_path: 上传图路径
        dpi: 分辨率

    Returns:
        RGBA Image，zone 像素尺寸
    """
    zp = zone_to_px(zone, dpi)
    src = load_source_image(image_path)
    fitted = fit_to_zone(src, zp.width_px, zp.height_px, zone.fit_mode or "stretch")
    mask = make_corner_mask(zp.width_px, zp.height_px, zone.corner_crop, dpi)
    masked = apply_alpha_mask(fitted, mask)
    return apply_transforms(masked, zone, dpi)


# ---------------------------------------------------------------------------
# 纯色区
# ---------------------------------------------------------------------------


def extract_average_color(img: Image.Image) -> tuple[int, int, int]:
    """提取平均色（RGB 三通道均值）。"""
    stat = ImageStat.Stat(img.convert("RGB"))
    r, g, b = (int(v) for v in stat.mean[:3])
    return (r, g, b)


def extract_dominant_color(img: Image.Image, n_colors: int = 8) -> tuple[int, int, int]:
    """
    提取主色：量化到 n_colors 色后取出现最多的色。

    Args:
        img: 源图
        n_colors: 量化色数

    Returns:
        (r, g, b)
    """
    rgb = img.convert("RGB")
    quant = rgb.quantize(colors=n_colors, method=Image.MEDIANCUT)
    palette = quant.getpalette()[: n_colors * 3]
    # 统计每个调色板 index 的像素数
    hist = quant.histogram()[:n_colors]
    max_idx = hist.index(max(hist))
    r = palette[max_idx * 3]
    g = palette[max_idx * 3 + 1]
    b = palette[max_idx * 3 + 2]
    return (r, g, b)


def extract_color(img: Image.Image, method: str) -> tuple[int, int, int]:
    """按 method 提取颜色。"""
    if method == "average":
        return extract_average_color(img)
    if method == "dominant":
        return extract_dominant_color(img)
    raise ValueError(f"未知主色提取方法: {method}")


def make_color_layer(
    zone, dpi: int, color: tuple[int, int, int]
) -> Image.Image:
    """
    生成纯色区图层：zone 像素尺寸 RGBA，填充指定色。

    Args:
        zone: config.prepress.Zone 对象（type=color）
        dpi: 分辨率
        color: (r, g, b)

    Returns:
        RGBA Image，zone 像素尺寸
    """
    zp = zone_to_px(zone, dpi)
    r, g, b = color
    layer = Image.new("RGBA", (zp.width_px, zp.height_px), (r, g, b, 255))
    # 纯色区也应用四角裁剪（与图片区一致）
    if zone.corner_crop is not None:
        mask = make_corner_mask(zp.width_px, zp.height_px, zone.corner_crop, dpi)
        layer = apply_alpha_mask(layer, mask)
    return layer
