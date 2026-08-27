"""spike 03：生成分层 PSD + 平面 TIF（手动验证图层）

目标：产出一份真正的"分层 PSD"和对应的"平面 TIF"，
      供手动用 Photoshop 打开确认图层结构。

分层（2 层）：
  - Pattern 图案层：彩色图案（不透明底）
  - Mark    标记层：四角裁切线 + 顶部标记条（透明背景，可单独开关）

输出：
  data/outputs/spike03_layers.psd   ← 分层，Photoshop 打开应见 2 个图层
  data/outputs/spike03_flat.tif     ← 平面合成，150 DPI

注：psd-tools 图层名限 ASCII，故用英文层名。
"""
from _bootstrap import *  # noqa: F401,F403
import os
import pyvips
from PIL import Image, ImageDraw
from psd_tools import PSDImage


def ensure_vips():
    bin = os.path.abspath("vendor/libvips/bin")
    os.add_dll_directory(bin)
    os.environ["PATH"] = bin + os.pathsep + os.environ["PATH"]


def make_pattern_pil(w, h):
    """图案层：彩色背景 + 竖条纹"""
    img = Image.new("RGBA", (w, h), (200, 180, 255, 255))
    d = ImageDraw.Draw(img)
    for i in range(0, w, 80):
        d.rectangle([i, 0, i + 40, h], fill=(255, 120, 100, 255))
    return img


def make_mark_pil(w, h):
    """标记层：四角裁切线 + 顶部标记条，透明背景"""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = 24
    # 四角裁切线（红）
    d.line([(0, m), (m, 0)], fill=(255, 0, 0, 255), width=3)
    d.line([(w - m, 0), (w, m)], fill=(255, 0, 0, 255), width=3)
    d.line([(0, h - m), (m, h)], fill=(255, 0, 0, 255), width=3)
    d.line([(w - m, h), (w, h - m)], fill=(255, 0, 0, 255), width=3)
    # 顶部标记条（半透明蓝）
    d.rectangle([0, 0, w, 30], fill=(0, 0, 255, 160))
    return img


def pil_to_vips(pil_img):
    """PIL RGBA → pyvips Image（带 alpha，srgb 解释）"""
    import numpy as np
    arr = np.array(pil_img)
    v = pyvips.Image.new_from_memory(arr.tobytes(), pil_img.width, pil_img.height,
                                     bands=4, format="uchar")
    # 4 通道默认识别为 multiband，显式标记为 sRGB+alpha
    v = v.copy(interpretation=pyvips.Interpretation.SRGB)
    return v


def main():
    ensure_vips()
    w, h = 600, 800

    pattern = make_pattern_pil(w, h)
    mark = make_mark_pil(w, h)

    # ---- 1. 分层 PSD ----
    psd = PSDImage.new(mode="RGB", size=(w, h), color=(255, 255, 255))
    psd.append(psd.create_pixel_layer(pattern, name="Pattern"))
    psd.append(psd.create_pixel_layer(mark, name="Mark"))

    psd_path = OUTPUTS / "spike03_layers.psd"
    psd.save(psd_path)
    print(f"[PSD] {psd_path}  ({psd_path.stat().st_size:,} bytes)")

    # 读回确认层数
    psd2 = PSDImage.open(psd_path)
    print(f"     读回层数: {len(psd2)}  层名: {[l.name for l in psd2]}")

    # ---- 2. 平面 TIF（150 DPI）----
    # 用 pyvips 合成：图案在下，标记在上
    pat_v = pil_to_vips(pattern)
    mark_v = pil_to_vips(mark)
    # 标记层有 alpha，叠到图案层上
    flat = pat_v.composite(mark_v, "over")

    tif_path = OUTPUTS / "spike03_flat.tif"
    # 150 DPI → pixels/mm
    res = 150 / 25.4
    flat.tiffsave(str(tif_path), xres=res, yres=res, resunit="inch")
    print(f"[TIF] {tif_path}  ({tif_path.stat().st_size:,} bytes)")

    print("\n完成。请用 Photoshop 打开 PSD 确认有 Pattern / Mark 两个独立图层。")


if __name__ == "__main__":
    main()
