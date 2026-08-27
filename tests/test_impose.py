"""排版拼版引擎单测（原尺寸流式铺排）。

图件按原始尺寸（仅旋转，不缩放）行优先流式铺排，从画布左上角开始，无间距无边距。
验证：原尺寸放置、旋转后宽高互换、alpha 语义、PSD 输入、缩略图、写 TIF 坑回归、超出报错。
不碰文件库，直接构造 Preset + tmp_path。
"""
from __future__ import annotations

from pathlib import Path

from app._vendor import load_vips

load_vips()

import numpy as np
import pyvips
import pytest
from PIL import Image as PILImage
from psd_tools import PSDImage

from app.config.impose import (
    Canvas,
    Gutters,
    ImposeMarks,
    ImposeOutput,
    Layout,
    Preset,
)
from app.tasks.scripts._impose_io import load_image, rotate_cw
from app.tasks.scripts._state import TaskStatus
from app.tasks.scripts.impose import SlotInput, run


def _preset(*, width_mm: float = 200, height_mm: float = 100, dpi: int = 150) -> Preset:
    """构造小画布 Preset（流式布局，layout/gutters 为占位，引擎不用）。"""
    return Preset(
        id="inline",
        name="测试排版",
        canvas=Canvas(width_mm=width_mm, height_mm=height_mm, dpi=dpi, bitdepth=8),
        layout=Layout(mode="grid", rows=1, cols=1, default_fit_mode="stretch"),
        gutters=Gutters(),
        marks=ImposeMarks(crop_marks=False, registration_marks=False),
        output=ImposeOutput(format="tif", compression="deflate", color_profile="srgb"),
    )


def _mk_img(path: Path, w: int, h: int, rgba: tuple) -> Path:
    """造一张纯色 RGBA PNG。"""
    arr = np.zeros((h, w, 4), np.uint8)
    arr[:] = rgba
    PILImage.fromarray(arr).save(path)
    return path


def _read(path: Path) -> pyvips.Image:
    return pyvips.Image.new_from_file(str(path), access="random")


def _out_tif(state) -> Path:
    assert state.status == TaskStatus.SUCCEEDED, f"任务失败: {state.error}"
    assert len(state.outputs) == 1
    return Path(state.outputs[0]["path"])


def test_original_size_placement(tmp_path):
    """图件按原尺寸放置，从 (0,0) 开始，紧接摆放。"""
    a = _mk_img(tmp_path / "a.png", 150, 100, (255, 0, 0, 255))
    b = _mk_img(tmp_path / "b.png", 120, 80, (0, 255, 0, 255))
    # 画布 200x100mm@150dpi = 1181x591px
    preset = _preset()
    state = run([SlotInput(path=str(a)), SlotInput(path=str(b))], preset, tmp_path / "out")

    tif = _out_tif(state)
    r = _read(tif)
    assert r.bands == 4
    assert r.interpretation == pyvips.Interpretation.SRGB
    assert r.width == 1181 and r.height == 591

    # a 在 (0,0) 150x100，中心 (75,50) 红 alpha=255
    px = r.getpoint(75, 50)
    assert px[0] == 255 and px[3] == 255
    # b 紧接右侧 (150,0) 120x80，中心 (210,40) 绿 alpha=255
    px = r.getpoint(210, 40)
    assert px[1] == 255 and px[3] == 255
    # 空白区 alpha=0
    assert r.getpoint(1170, 580)[3] == 0


def test_rotation_swaps_dims(tmp_path):
    """90° 旋转后图件宽高互换，原尺寸不变。直接测 rotate_cw。"""
    a = _mk_img(tmp_path / "a.png", 150, 100, (255, 0, 0, 255))  # 150宽100高
    img = load_image(a, "png")
    r90 = rotate_cw(img, 90)
    assert r90.width == 100 and r90.height == 150
    r180 = rotate_cw(img, 180)
    assert r180.width == 150 and r180.height == 100
    r270 = rotate_cw(img, 270)
    assert r270.width == 100 and r270.height == 150


def test_rotation_in_layout(tmp_path):
    """旋转图件在布局中用旋转后尺寸摆放。"""
    a = _mk_img(tmp_path / "a.png", 150, 100, (255, 0, 0, 255))
    # 旋转90 → 100x150；画布 200x100mm@150dpi=1181x591，放得下
    preset = _preset()
    state = run([SlotInput(path=str(a), rotation=90)], preset, tmp_path / "out")
    r = _read(_out_tif(state))
    # 图件 100x150 在 (0,0)，中心 (50,75) 红 alpha=255
    px = r.getpoint(50, 75)
    assert px[0] == 255 and px[3] == 255
    # 右侧空白 alpha=0（100 之外）
    assert r.getpoint(200, 50)[3] == 0


def test_flow_wraps(tmp_path):
    """图件排满一行宽度后换行。"""
    # 三张 500x100 图件，画布 200x100mm@150dpi=1181x591
    # 500+500=1000<1181，第三张 500+1000=1500>1181 → 换行到 y=100
    a = _mk_img(tmp_path / "a.png", 500, 100, (255, 0, 0, 255))
    b = _mk_img(tmp_path / "b.png", 500, 100, (0, 255, 0, 255))
    c = _mk_img(tmp_path / "c.png", 500, 100, (0, 0, 255, 255))
    preset = _preset()
    state = run([SlotInput(path=str(a)), SlotInput(path=str(b)), SlotInput(path=str(c))],
                preset, tmp_path / "out")
    r = _read(_out_tif(state))
    # a (0,0) 红，b (500,0) 绿，c 换行 (0,100) 蓝
    assert r.getpoint(250, 50)[0] == 255   # a
    assert r.getpoint(750, 50)[1] == 255   # b
    assert r.getpoint(250, 150)[2] == 255  # c 换行


def test_alpha_transparent_regions(tmp_path):
    """图件区 alpha=255，未覆盖区 alpha=0。"""
    a = _mk_img(tmp_path / "a.png", 150, 100, (255, 0, 0, 255))
    preset = _preset()
    state = run([SlotInput(path=str(a))], preset, tmp_path / "out")
    r = _read(_out_tif(state))
    # 图件内 alpha=255
    assert r.getpoint(75, 50)[3] == 255
    # 图件外 alpha=0
    assert r.getpoint(200, 50)[3] == 0
    assert r.getpoint(75, 150)[3] == 0


def test_psd_input(tmp_path):
    """PSD 输入图件可载入拼版。"""
    psd = PSDImage.new(mode="RGBA", size=(100, 80), color=(10, 20, 30, 255))
    psd_path = tmp_path / "s.psd"
    psd.save(psd_path)
    preset = _preset()
    state = run([SlotInput(path=str(psd_path))], preset, tmp_path / "out")
    r = _read(_out_tif(state))
    assert r.bands == 4
    assert r.getpoint(50, 40)[3] == 255


def test_thumbnail_generated(tmp_path):
    """缩略图 webp 生成且尺寸合规。"""
    a = _mk_img(tmp_path / "a.png", 150, 100, (255, 0, 0, 255))
    preset = _preset()
    state = run([SlotInput(path=str(a))], preset, tmp_path / "out")
    assert state.thumb_path
    thumb = Path(state.thumb_path)
    assert thumb.exists()
    t = pyvips.Image.new_from_file(str(thumb))
    assert max(t.width, t.height) <= 400


def test_tif_bitdepth_alpha_regression(tmp_path):
    """写 TIF 坑回归：4 band、uchar、srgb、alpha 保留。"""
    a = _mk_img(tmp_path / "a.png", 150, 100, (255, 0, 0, 255))
    preset = _preset()
    state = run([SlotInput(path=str(a))], preset, tmp_path / "out")
    r = _read(_out_tif(state))
    assert r.bands == 4
    assert r.format == pyvips.BandFormat.UCHAR
    assert r.interpretation == pyvips.Interpretation.SRGB
    alpha = r.extract_band(3)
    assert alpha.min() == 0
    assert alpha.max() == 255


def test_out_of_bounds_fails(tmp_path):
    """图件超出画布边界 → FAILED。"""
    big = _mk_img(tmp_path / "big.png", 600, 600, (0, 0, 255, 255))
    # 画布 100x80mm@150dpi=591x472，图件 600x600 超出
    preset = _preset(width_mm=100, height_mm=80)
    state = run([SlotInput(path=str(big))], preset, tmp_path / "out")
    assert state.status == TaskStatus.FAILED
    assert "超出" in state.error


def test_rotated_out_of_bounds_fails(tmp_path):
    """旋转后超出也报错。"""
    # 100x400 旋转90 → 400x100；画布 100x80mm@150dpi=591x472，宽400<591 高100<472 OK
    # 改用 500x100 旋转90 → 100x500，高500>472 报错
    img = _mk_img(tmp_path / "r.png", 500, 100, (0, 0, 255, 255))
    preset = _preset(width_mm=100, height_mm=80)
    state = run([SlotInput(path=str(img), rotation=90)], preset, tmp_path / "out")
    assert state.status == TaskStatus.FAILED
    assert "超出" in state.error
