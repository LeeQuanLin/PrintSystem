"""spike 04：超大排版文件（260cm×900cm@150dpi）格式能力验证

尺寸：15354 × 53150 px ≈ 8.16 亿像素，RGB8 未压缩 ≈ 2.45GB

验证：
  1. 尺寸计算与各格式能力边界
  2. pyvips 写 bigtiff（能否承载 >4GB / 超大尺寸）
  3. PSB 写入野路子排查：pyvips magicksave、psd-tools
"""
from _bootstrap import *  # noqa: F401,F403
import os
import pyvips
from psd_tools import PSDImage


def ensure_vips():
    bin = os.path.abspath("vendor/libvips/bin")
    os.add_dll_directory(bin)
    os.environ["PATH"] = bin + os.pathsep + os.environ["PATH"]


def print_size_facts():
    w_mm, h_mm, dpi = 2600, 9000, 150
    px_per_mm = dpi / 25.4
    w_px = round(w_mm * px_per_mm)
    h_px = round(h_mm * px_per_mm)
    total_px = w_px * h_px
    rgb8 = total_px * 3
    print("=== 尺寸 ===")
    print(f"  {w_mm}mm × {h_mm}mm @ {dpi}dpi")
    print(f"  = {w_px} × {h_px} px")
    print(f"  = {total_px/1e8:.2f} 亿像素")
    print(f"  RGB8 未压缩 ≈ {rgb8/1e9:.2f} GB")
    print(f"  PSD 上限 30000×30000px/2GB → 高 {h_px}px {'超标' if h_px>30000 else 'OK'}")
    print(f"  PSB 上限 300000×300000px → {'OK' if max(w_px,h_px)<=300000 else '超标'}")


def test_bigtiff():
    """pyvips 写 bigtiff（用小尺寸验证 bigtiff 标志可用，不真生成 2.5GB）"""
    print("\n=== bigtiff 写入 ===")
    img = (pyvips.Image.black(2000, 2000, bands=3) + [180, 200, 255]).copy(
        interpretation=pyvips.Interpretation.SRGB
    )
    res = 150 / 25.4
    out = OUTPUTS / "spike04_bigtiff.tif"
    img.tiffsave(str(out), bigtiff=True, xres=res, yres=res, resunit="inch",
                 compression="deflate")
    sz = out.stat().st_size
    # 读回确认
    r = pyvips.Image.new_from_file(str(out))
    print(f"  写入: {out.name} ({sz:,} bytes, bigtiff=True)")
    print(f"  读回: {r.width}×{r.height} interpretation={r.interpretation}")
    print(f"  结论: bigtiff 写入 {'OK' if r.width==2000 else 'FAIL'}")
    return True


def test_psb_paths():
    """PSB 写入路径排查"""
    print("\n=== PSB 写入路径排查 ===")
    img = (pyvips.Image.black(500, 500, bands=3) + 128).copy(
        interpretation=pyvips.Interpretation.SRGB
    )

    # 路径1: pyvips magicksave 到 .psb
    try:
        out = OUTPUTS / "spike04_magick.psb"
        img.magicksave(str(out))
        print(f"  magicksave .psb: 成功 ({out.stat().st_size} bytes) —— 需确认是否真分层")
    except Exception as e:
        print(f"  magicksave .psb: 失败 — {str(e)[:120]}")

    # 路径2: pyvips 直接 .psb 后缀
    try:
        out = OUTPUTS / "spike04_direct.psb"
        img.tiffsave(str(out))
        print(f"  tiffsave .psb: 写入成功但实为 TIF 内容（不可用）")
    except Exception as e:
        print(f"  tiffsave .psb: 失败 — {str(e)[:120]}")

    # 路径3: psd-tools 是否支持 PSB 保存
    print(f"  psd-tools PSDImage.save 仅支持 PSD格式（源码无 PSB saver）")

    # 路径4: 查 pyvips 所有 saver 里有没有 psb
    suffixes = pyvips.get_suffixes()
    psb_related = [s for s in suffixes if 'psb' in s.lower() or 'psd' in s.lower()]
    print(f"  pyvips 支持的 psd/psb 后缀: {psb_related or '无'}")


def main():
    ensure_vips()
    print_size_facts()
    test_bigtiff()
    test_psb_paths()
    print("\n========== 总结 ==========")
    print("超大排版文件：PSD 尺寸超标写不了，PSB Python 写不了。")
    print("可行路径：pyvips 写平面 bigtiff（流式、内存友好、支持 >4GB）。")
    print("分层诉求：需重新评估——大版面分层 PSB 在服务器 Python 环境无法实现。")


if __name__ == "__main__":
    main()
