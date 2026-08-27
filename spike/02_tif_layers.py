"""spike 02：分层 TIF / PSB 写入可行性（核心风险点）

问题：pyvips 能写 TIF/PSB 位图，但不支持 Photoshop 式"图层"。
       psd-tools 只能写 PSD，不能写 TIF/PSB。

本 spike 验证三条路径：
  A. pyvips 写多页 TIF（page_height）——"多页"非"分层"，但可作为多面/多尺码容器
  B. pyvips 直接写 PSB —— 能否写出、是否平面
  C. psd-tools 写 PSD 后转 TIF —— 转换是否丢层

判定：记录每条路径的实际能力，供 06-任务处理引擎 定方案。
"""
from _bootstrap import *  # noqa: F401,F403
import os
import pyvips
from PIL import Image
from psd_tools import PSDImage


def _ensure_vips():
    bin = os.path.abspath("vendor/libvips/bin")
    os.add_dll_directory(bin)
    os.environ["PATH"] = bin + os.pathsep + os.environ["PATH"]


def make_pattern_vips(w, h):
    """图案层：pyvips 版彩色块"""
    base = pyvips.Image.black(w, h, bands=3)
    red = pyvips.Image.black(w, h, bands=3) + [255, 120, 100]
    mask = pyvips.Image.black(w // 2, h, bands=1)
    mask = mask.gravity("west", w, h)  # 左半 0
    # 简化：直接做纯色 + 渐变
    return base + [200, 180, 255]


def path_a_multipage_tif():
    """路径 A：pyvips 多页 TIF（非分层，验证作为多面容器）"""
    w, h = 600, 800
    pattern = make_pattern_vips(w, h)
    mark = pyvips.Image.black(w, h, bands=4)
    # 合成：图案 + 标记
    # 多页：上下拼成 page_height=h 的两页
    out = OUT / "spike02_multipage.tif"
    combined = pattern.bandjoin(pyvips.Image.black(w, h, bands=1))  # 加 alpha
    two_pages = combined.join(combined, "vertical")  # 2h 高，page_height 分页
    two_pages.tiffsave(str(out), page_height=h, xres=150 / 25.4, yres=150 / 25.4)
    print(f"[A] 多页 TIF: {out} ({out.stat().st_size} bytes)")
    # 读回验证页数
    pages = pyvips.Image.new_from_file(str(out), n=-1)
    print(f"    读回高度: {pages.height} (预期 {h*2}) → 多页容器 {'OK' if pages.height==h*2 else 'FAIL'}")
    return out.exists()


def path_b_psb():
    """路径 B：pyvips 写 PSB（大尺寸 PSD）"""
    w, h = 600, 800
    pattern = make_pattern_vips(w, h)
    out = OUT / "spike02.psb"
    try:
        pattern.tiffsave(str(out))  # pyvips 无 psb 专用 saver，先看能否写
        print(f"[B] pyvips 写 .psb 后缀: 成功 ({out.stat().st_size} bytes)")
        # 实际是 tif 内容套 psb 名，不可用
        print("    （注：pyvips 无 PSB saver，此文件实为 TIF 内容，路径 B 不可行）")
        return False
    except Exception as e:
        print(f"[B] pyvips 写 PSB: 失败 — {e}")
        return False


def path_c_psd_then_tif():
    """路径 C：psd-tools 写分层 PSD → 用 PIL 读平面 → 转 TIF（验证是否丢层）"""
    w, h = 600, 800
    psd = PSDImage.new(mode="RGB", size=(w, h), color=(255, 255, 255))
    layer1 = psd.create_pixel_layer(
        Image.new("RGBA", (w, h), (200, 180, 255, 255)), name="Pattern"
    )
    psd.append(layer1)
    layer2 = psd.create_pixel_layer(
        Image.new("RGBA", (w, h), (255, 0, 0, 128)), name="Mark"
    )
    psd.append(layer2)

    psd_path = OUT / "spike02_src.psd"
    psd.save(psd_path)

    # 合成成平面 TIF
    composited = psd.composite()  # psd-tools 自带合成
    tif_path = OUT / "spike02_from_psd.tif"
    composited.save(str(tif_path), dpi=(150, 150))
    print(f"[C] PSD({psd_path.stat().st_size}B) → 平面 TIF({tif_path.stat().st_size}B)")
    print("    （注：合成为平面 TIF，图层丢失，仅保留合成结果）")

    # 读回 PSD 确认原图层还在
    psd2 = PSDImage.open(psd_path)
    print(f"    源 PSD 层数: {len(psd2)} → 分层信息保留在 PSD 中，TIF 为平面合成")
    return len(psd2) == 2


def main():
    _ensure_vips()
    print("=== 路径 A: pyvips 多页 TIF ===")
    a = path_a_multipage_tif()
    print("\n=== 路径 B: pyvips 写 PSB ===")
    b = path_b_psb()
    print("\n=== 路径 C: PSD 分层 → TIF 平面 ===")
    c = path_c_psd_then_tif()

    print("\n========== 结论 ==========")
    print(f"A 多页 TIF 容器: {'可行（多页≠分层）' if a else '不可行'}")
    print(f"B pyvips 直写 PSB: {'可行' if b else '不可行（无 PSB saver）'}")
    print(f"C 分层 PSD 存档 + 平面 TIF 交付: {'可行' if c else '不可行'}")
    print("\n综合：真'分层 TIF/PSB' 在 Python 生态无法直写。")
    print("推荐方案：分层信息存 PSD/PSB(需 Photoshop 或 psd-tools)，TIF 作平面交付。")


if __name__ == "__main__":
    main()
