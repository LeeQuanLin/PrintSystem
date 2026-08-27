"""排版图件载入 / 适配 / 旋转 / 写出 / 缩略图（pyvips）。

排版输出普通 TIF（不分层，带 alpha）。写 TIF 前必须 colourspace("srgb").cast("uchar")
并加 bitdepth=8，否则 pyvips 可能存成 32 位浮点 scRGB，Photoshop 报"不受支持的位深度"
（见 CLAUDE.md §3、spike 06）。

PSD 输入图：pyvips 无 PSD 加载器，走 psd-tools 合成 → PIL → numpy → pyvips。
其它格式走 new_from_file(access="sequential") 流式载入。
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from app._vendor import load_vips

load_vips()

import numpy as np
import pyvips
from PIL import Image
from psd_tools import PSDImage

# 家纺印前图普遍超 PIL 默认 89M 像素上限，放开
Image.MAX_IMAGE_PIXELS = None

_FIT_MODE = Literal["stretch", "contain", "cover"]


def _to_rgba_uchar(img: pyvips.Image) -> pyvips.Image:
    """确保 4 band RGBA uchar：缺 alpha 补 255，统一 uchar。"""
    if img.bands < 3:
        # 灰度 → RGB（保留 interpretation 让 colourspace 正确）
        img = img.colourspace("srgb")
    if img.bands == 3:
        w, h = img.width, img.height
        # black+常量会丢 interpretation → float，故 cast 回 uchar
        alpha = (pyvips.Image.black(w, h, bands=1) + 255).cast("uchar")
        img = img.bandjoin(alpha)
    img = img.cast("uchar")
    return img


def load_image(path: str | Path, fmt: str) -> pyvips.Image:
    """
    载入一个图件为 4 band RGBA uchar pyvips.Image。

    Args:
        path: 图件路径
        fmt: 格式（psd / png / tif / jpg ...）
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"图件不存在: {p}")

    if fmt == "psd":
        # pyvips 无 PSD 加载器：psd-tools 合成平面 → PIL RGBA → numpy → pyvips
        psd = PSDImage.open(p)
        composited = psd.composite()
        if composited.mode != "RGBA":
            composited = composited.convert("RGBA")
        arr = np.ascontiguousarray(np.array(composited))
        img = pyvips.Image.new_from_array(arr)
        return _to_rgba_uchar(img)

    # 普通图：random 访问（合成/标记需多次随机读取源；libvips 必要时落临时盘）
    img = pyvips.Image.new_from_file(str(p), access="random")
    return _to_rgba_uchar(img)


def fit_to_slot(
    img: pyvips.Image,
    slot_w: int,
    slot_h: int,
    fit_mode: str,
) -> pyvips.Image:
    """
    把图件适配到槽位尺寸（像素）。

    - stretch：拉伸铺满（忽略宽高比）
    - contain：等比缩放进槽位，留白区透明（alpha=0）
    - cover：等比覆盖后居中裁切到槽位
    """
    if img.width == slot_w and img.height == slot_h:
        return img

    if fit_mode == "stretch":
        # 非等比拉伸：resize 用独立 x/y 缩放
        return img.resize(slot_w / img.width, vscale=slot_h / img.height)

    iw, ih = img.width, img.height
    if fit_mode == "contain":
        scale = min(slot_w / iw, slot_h / ih)
        scaled = img.resize(scale) if scale != 1 else img
        sw, sh = scaled.width, scaled.height
        dx = (slot_w - sw) // 2
        dy = (slot_h - sh) // 2
        # embed 到槽位尺寸，背景透明
        return scaled.embed(dx, dy, slot_w, slot_h,
                            extend="background", background=[0, 0, 0, 0])

    if fit_mode == "cover":
        scale = max(slot_w / iw, slot_h / ih)
        scaled = img.resize(scale) if scale != 1 else img
        sw, sh = scaled.width, scaled.height
        left = (sw - slot_w) // 2
        top = (sh - slot_h) // 2
        return scaled.crop(left, top, slot_w, slot_h)

    raise ValueError(f"未知 fit_mode: {fit_mode}")


def rotate_cw(img: pyvips.Image, rotation: int) -> pyvips.Image:
    """
    顺时针旋转 90° 倍数。

    pyvips Image.rot("d90") 即顺时针 90°（实测：旋转后新顶行=原图左列）。
    rotation ∈ {0, 90, 180, 270}。
    """
    if rotation == 0:
        return img
    if rotation not in (90, 180, 270):
        raise ValueError(f"rotation 须为 0/90/180/270，得到 {rotation}")
    return img.rot({90: "d90", 180: "d180", 270: "d270"}[rotation])


def write_alpha_tif(
    img: pyvips.Image,
    path: str | Path,
    dpi: int,
    compression: str = "none",
) -> None:
    """
    写普通 TIF（不分层，带 alpha），PS 可打开。

    用无压缩 striped（compression="none"）——deflate 在纯色大图上压缩比极端，
    PS 解码异常打不开；striped 无压缩已验证 PS 可正常打开（见 spike 06 验证）。
    强制 8 位 sRGB + alpha：colourspace("srgb").cast("uchar") + bitdepth=8。
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    out = img.colourspace("srgb").cast("uchar")
    res = dpi / 25.4  # pixels/mm（resunit=inch 时 pyvips 按 xres 像素/单位写）
    out.tiffsave(
        str(p),
        xres=res, yres=res, resunit="inch",
        compression="none", bitdepth=8,
    )


def make_thumbnail(
    img: pyvips.Image,
    path: str | Path,
    max_px: int = 400,
    quality: int = 80,
) -> None:
    """
    生成 webp 缩略图（白底合成 alpha 后缩略）。

    pyvips 流式 resize，大画布友好。
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # 白底合成：alpha 拍平到白
    if img.bands >= 4:
        rgb = img.extract_band(0, n=3)
        alpha = img.extract_band(3)
        # 白底 = 255；合成 = rgb*alpha/255 + 255*(1-alpha/255) = 255 - (255-rgb)*alpha/255
        bg = pyvips.Image.black(rgb.width, rgb.height, bands=3) + 255
        bg = bg.cast("uchar")
        flat = bg.subtract(bg.subtract(rgb).multiply(alpha).divide(255))
        flat = flat.cast("uchar")
    else:
        flat = img.colourspace("srgb").cast("uchar")

    scale = max_px / max(flat.width, flat.height)
    if scale < 1:
        flat = flat.resize(scale)
    flat.webpsave(str(p), Q=quality)
