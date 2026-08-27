"""spike 01：psd-tools 写分层 PSD（基线验证）

目标：确认 psd-tools 能否组装出"真分层"PSD。
分层：图案层 + 标记层（两层独立，可单独开关）。

判定标准：
- 写出的 PSD 用 psd-tools 读回，能看到 2 个独立图层
- 图层名/内容与写入一致
"""
from _bootstrap import *  # noqa: F401,F403  提供 OUT 等
from psd_tools import PSDImage
from PIL import Image, ImageDraw


def make_pattern_layer(w, h):
    """图案层：彩色渐变 + 色块"""
    img = Image.new("RGB", (w, h), (200, 180, 255))
    d = ImageDraw.Draw(img)
    for i in range(0, w, 80):
        d.rectangle([i, 0, i + 40, h], fill=(255, 120, 100))
    return img


def make_mark_layer(w, h):
    """标记层：裁切线 + 文字标记，透明背景"""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 四角裁切线
    m = 20
    d.line([(0, m), (m, 0)], fill=(255, 0, 0, 255), width=2)
    d.line([(w - m, 0), (w, m)], fill=(255, 0, 0, 255), width=2)
    d.line([(0, h - m), (m, h)], fill=(255, 0, 0, 255), width=2)
    d.line([(w - m, h), (w, h - m)], fill=(255, 0, 0, 255), width=2)
    # 顶部标记条
    d.rectangle([0, 0, w, 30], fill=(0, 0, 255, 160))
    return img


def main():
    w, h = 600, 800
    psd = PSDImage.new(mode="RGB", size=(w, h), color=(255, 255, 255))

    # 图案层
    pattern = make_pattern_layer(w, h)
    layer1 = psd.create_pixel_layer(
        pattern.convert("RGBA"),
        name="Pattern",
    )
    psd.append(layer1)

    # 标记层（带透明）
    mark = make_mark_layer(w, h)
    layer2 = psd.create_pixel_layer(
        mark,
        name="Mark",
    )
    psd.append(layer2)

    out_path = OUT / "spike01_layers.psd"
    psd.save(out_path)
    print(f"写入: {out_path}  ({out_path.stat().st_size} bytes)")

    # 读回验证
    psd2 = PSDImage.open(out_path)
    names = [l.name for l in psd2]
    print(f"读回层数: {len(psd2)}  层名: {names}")

    ok = len(psd2) == 2 and "Pattern" in names and "Mark" in names
    print("结论:", "PASS — psd-tools 可写真分层 PSD" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    main()
