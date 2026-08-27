"""spike 06：普通 TIF（非 bigtiff）带透明 alpha 验证

需求：排版输出用不分层的普通 TIF，验证能否保留透明像素。
普通 TIF（Classic TIFF）上限 4GB，260×900cm@150dpi RGB8+alpha ≈ 3.26GB，在范围内。

验证：
  1. 小尺寸：普通 tiffsave 带 alpha，读回确认透明区 alpha=0
  2. 真实大尺寸（15354×53150）：能否写出、alpha 是否保留、文件大小
"""
from _bootstrap import *  # noqa: F401,F403
import os
import pyvips


def ensure_vips():
    bin = os.path.abspath("vendor/libvips/bin")
    os.add_dll_directory(bin)
    os.environ["PATH"] = bin + os.pathsep + os.environ["PATH"]


def make_rgba(w, h):
    """左半不透明彩色，右半全透明（强制 sRGB 8位 uchar）"""
    base = (pyvips.Image.black(w, h, bands=3) + [200, 180, 255]).copy(
        interpretation=pyvips.Interpretation.SRGB
    )
    left = pyvips.Image.black(w // 2, h, bands=1) + 255
    right = pyvips.Image.black(w - w // 2, h, bands=1)
    alpha = left.join(right, "horizontal")
    img = base.bandjoin(alpha)
    # 关键：强制转 sRGB + cast 到 8位无符号整数，否则 pyvips 可能存成 float/scrgb
    img = img.colourspace("srgb").cast("uchar")
    return img


def check_small():
    print("=== 小尺寸普通 TIF（带 alpha）===")
    img = make_rgba(800, 600)
    out = OUTPUTS / "spike06_small.tif"
    res = 150 / 25.4
    img.tiffsave(str(out), xres=res, yres=res, resunit="inch", compression="deflate", bitdepth=8)
    sz = out.stat().st_size
    r = pyvips.Image.new_from_file(str(out))
    px = r.getpoint(r.width - 5, r.height // 2)
    has_alpha = r.bands == 4
    ok = has_alpha and px[3] == 0
    print(f"  写入: {out.name} ({sz:,} bytes)")
    print(f"  读回: {r.width}×{r.height}, bands={r.bands}, has_alpha={has_alpha}")
    print(f"  右半像素 RGBA={px} (alpha 应为 0)")
    print(f"  结论: {'PASS' if ok else 'FAIL'}")
    return ok


def check_large():
    print("\n=== 真实大尺寸 15354×53150（普通 TIF 带 alpha）===")
    w, h = 15354, 53150
    print(f"  尺寸: {w}×{h}, RGB8+alpha 理论未压缩 ≈ {w*h*4/1e9:.2f} GB")
    img = make_rgba(w, h)
    out = OUTPUTS / "spike06_large.tif"
    res = 150 / 25.4
    try:
        img.tiffsave(str(out), xres=res, yres=res, resunit="inch",
                     compression="deflate", tile=True, tile_width=256, tile_height=256)
    except Exception as e:
        print(f"  写入失败: {str(e)[:150]}")
        return False
    sz = out.stat().st_size
    # 只读头部信息（不全部载入）
    r = pyvips.Image.new_from_file(str(out), access="sequential")
    px = r.getpoint(r.width - 5, r.height // 2)
    has_alpha = r.bands == 4
    ok = has_alpha and px[3] == 0
    print(f"  写入: {out.name} ({sz/1e9:.2f} GB)")
    print(f"  读回: {r.width}×{r.height}, bands={r.bands}, has_alpha={has_alpha}")
    print(f"  右上像素 RGBA={px} (alpha 应为 0)")
    print(f"  结论: {'PASS — 普通 TIF 大尺寸带 alpha 可行' if ok else 'FAIL'}")
    return ok


def main():
    ensure_vips()
    a = check_small()
    b = check_large()
    print("\n========== 总结 ==========")
    print(f"小尺寸普通 TIF 带 alpha: {'可行' if a else '不可行'}")
    print(f"大尺寸普通 TIF 带 alpha: {'可行' if b else '不可行'}")
    if a and b:
        print("结论：排版输出用不分层的普通 TIF（带 alpha）可行，无需 bigtiff/PSB。")
        print("注：仅 8bit 适用。若需 16bit，4通道≈6.5GB 超 4GB 上限，须用 bigtiff。")


if __name__ == "__main__":
    main()
