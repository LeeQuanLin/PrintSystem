"""spike 05：带透明 alpha 的平面输出（排版交付格式验证）

需求：排版输出不分层，但必须是"包含透明像素的平面"。
验证：
  1. magicksave 写 PSB 能否保留 alpha 通道
  2. pyvips bigtiff 写 TIF 能否保留 alpha
  3. 读回确认 alpha 通道存在且透明区域正确

测试图：左半不透明彩色，右半全透明——读回后右半 alpha 应为 0。
"""
from _bootstrap import *  # noqa: F401,F403
import os
import pyvips
import struct


def ensure_vips():
    bin = os.path.abspath("vendor/libvips/bin")
    os.add_dll_directory(bin)
    os.environ["PATH"] = bin + os.pathsep + os.environ["PATH"]


def make_rgba_image(w, h):
    """左半不透明彩色，右半全透明"""
    base = pyvips.Image.black(w, h, bands=3) + [200, 180, 255]
    base = base.copy(interpretation=pyvips.Interpretation.SRGB)
    # alpha：左半 255，右半 0
    left = pyvips.Image.black(w // 2, h, bands=1) + 255
    right = pyvips.Image.black(w - w // 2, h, bands=1)
    alpha = left.join(right, "horizontal")
    return base.bandjoin(alpha)


def check_psb_alpha(img):
    print("=== magicksave PSB (带 alpha) ===")
    out = OUTPUTS / "spike05_alpha.psb"
    try:
        img.magicksave(str(out))
    except Exception as e:
        print(f"  写入失败: {e}")
        return False
    sz = out.stat().st_size
    # 文件头确认 PSB
    with open(out, "rb") as f:
        head = f.read(6)
    ver = struct.unpack(">H", head[4:6])[0]
    # 读回验证 alpha
    r = pyvips.Image.new_from_file(str(out))
    has_alpha = r.bands == 4
    # 取右半一个像素的 alpha
    px = r.getpoint(r.width - 5, r.height // 2)
    print(f"  写入: {out.name} ({sz:,} bytes, 版本{ver})")
    print(f"  读回: {r.width}×{r.height}, bands={r.bands}, has_alpha={has_alpha}")
    print(f"  右半像素 RGBA={px} (alpha 应为 0)")
    ok = has_alpha and len(px) >= 4 and px[3] == 0
    print(f"  结论: {'PASS — PSB 保留透明 alpha' if ok else 'FAIL — alpha 丢失'}")
    return ok


def check_bigtiff_alpha(img):
    print("\n=== pyvips bigtiff (带 alpha) ===")
    out = OUTPUTS / "spike05_alpha.tif"
    res = 150 / 25.4
    img.tiffsave(str(out), bigtiff=True, xres=res, yres=res, resunit="inch",
                 compression="deflate", premultiply=False)
    sz = out.stat().st_size
    r = pyvips.Image.new_from_file(str(out))
    has_alpha = r.bands == 4
    px = r.getpoint(r.width - 5, r.height // 2)
    print(f"  写入: {out.name} ({sz:,} bytes, bigtiff)")
    print(f"  读回: {r.width}×{r.height}, bands={r.bands}, has_alpha={has_alpha}")
    print(f"  右半像素 RGBA={px} (alpha 应为 0)")
    ok = has_alpha and len(px) >= 4 and px[3] == 0
    print(f"  结论: {'PASS — bigtiff 保留透明 alpha' if ok else 'FAIL — alpha 丢失'}")
    return ok


def main():
    ensure_vips()
    w, h = 800, 600
    img = make_rgba_image(w, h)
    print(f"测试图: {w}×{h}, bands={img.bands} (左半不透明 / 右半透明)")

    a = check_psb_alpha(img)
    b = check_bigtiff_alpha(img)

    print("\n========== 总结 ==========")
    print(f"PSB 带 alpha:   {'可行' if a else '不可行'}")
    print(f"bigtiff 带 alpha: {'可行' if b else '不可行'}")
    if a and b:
        print("排版输出方案：带透明 alpha 的平面，PSB(主) / bigtiff(备) 均可行。")


if __name__ == "__main__":
    main()
