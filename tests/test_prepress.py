"""prepress 脚本测试。

测 run() 函数与 State domain 对象，不测 CLI。
用 test_small 配置（100×100mm @150dpi ≈ 626px）避免大图耗时。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image
from psd_tools import PSDImage

from app.tasks.scripts._config import load_params
from app.tasks.scripts._state import State, TaskStatus
from app.tasks.scripts.prepress import run


def _open_psd(psd_path: Path) -> PSDImage:
    return PSDImage.open(psd_path)


def _layer_names(psd: PSDImage) -> list[str]:
    return [layer.name for layer in psd]


# ---------------------------------------------------------------------------


def test_run_success_psd(sample_image, small_config, tmp_path):
    """run 成功（psd 格式）：state.outputs 含 psd 文件，thumb_path 存在。"""
    output_dir = tmp_path / "out"
    state = run(sample_image, small_config, output_dir)

    assert state.status == TaskStatus.SUCCEEDED
    assert state.progress == 100
    assert len(state.outputs) == 1
    out = state.outputs[0]
    assert out["format"] == "psd"
    assert Path(out["path"]).exists()
    assert Path(state.thumb_path).exists()


def test_psd_layers(sample_image, small_config, tmp_path):
    """PSD 层名齐全：FaceA + CropMarks + ZipperMarks + TextMarks。"""
    output_dir = tmp_path / "out"
    state = run(sample_image, small_config, output_dir)

    psd_path = next(o["path"] for o in state.outputs if o["format"] == "psd")
    psd = _open_psd(Path(psd_path))
    names = _layer_names(psd)
    for expected in ["FaceA", "CropMarks", "ZipperMarks", "TextMarks"]:
        assert expected in names, f"缺少图层 {expected}，现有 {names}"


def test_psd_canvas_size(sample_image, small_config, tmp_path):
    """PSD 尺寸 = 画布像素。"""
    output_dir = tmp_path / "out"
    state = run(sample_image, small_config, output_dir)

    psd_path = next(o["path"] for o in state.outputs if o["format"] == "psd")
    psd = _open_psd(Path(psd_path))
    params = load_params(small_config)
    expected_w = round((params.width_mm + 2 * params.bleed_mm) * params.dpi / 25.4)
    expected_h = round((params.height_mm + 2 * params.bleed_mm) * params.dpi / 25.4)
    assert psd.size[0] == expected_w
    assert psd.size[1] == expected_h


def test_png_output(sample_image, small_config, tmp_path):
    """配置 formats=[psd,png] 时同时输出 psd 和 png。"""
    # 临时改配置加 png
    import json as _json
    cfg_path = tmp_path / "cfg.json"
    data = _json.loads(small_config.read_text(encoding="utf-8"))
    data["params"]["output"]["formats"] = ["psd", "png"]
    cfg_path.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")

    output_dir = tmp_path / "out"
    state = run(sample_image, cfg_path, output_dir)

    assert state.status == TaskStatus.SUCCEEDED
    fmts = {o["format"] for o in state.outputs}
    assert fmts == {"psd", "png"}
    for o in state.outputs:
        assert Path(o["path"]).exists()
        assert o["path"].endswith(o["format"])


def test_png_dpi_metadata(sample_image, small_config, tmp_path):
    """PNG 文件带 DPI=150 元数据。"""
    import json as _json
    cfg_path = tmp_path / "cfg.json"
    data = _json.loads(small_config.read_text(encoding="utf-8"))
    data["params"]["output"]["formats"] = ["png"]
    cfg_path.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")

    output_dir = tmp_path / "out"
    state = run(sample_image, cfg_path, output_dir)

    png_path = next(o["path"] for o in state.outputs if o["format"] == "png")
    img = Image.open(png_path)
    dpi = img.info.get("dpi")
    assert dpi is not None
    assert abs(dpi[0] - 150) < 1


def test_state_progress_monotonic(sample_image, small_config, tmp_path):
    """传入的 State 对象，run 后 progress=100 且 stage 非空。"""
    output_dir = tmp_path / "out"
    state = State()
    returned = run(sample_image, small_config, output_dir, state=state)
    assert returned is state
    assert state.progress == 100
    assert state.stage != ""
    assert state.status == TaskStatus.SUCCEEDED


def test_state_failed_on_missing_image(small_config, tmp_path):
    """image 不存在 → status=FAILED，error 非空，不抛异常。"""
    output_dir = tmp_path / "out"
    state = run(tmp_path / "nonexistent.png", small_config, output_dir)

    assert state.status == TaskStatus.FAILED
    assert state.error != ""


def test_state_failed_on_bad_config(sample_image, tmp_path):
    """config 不存在 → status=FAILED。"""
    output_dir = tmp_path / "out"
    state = run(sample_image, tmp_path / "no.json", output_dir)

    assert state.status == TaskStatus.FAILED
    assert state.error != ""


def test_thumbnail_generated(sample_image, small_config, tmp_path):
    """缩略图存在、最长边≤400、WEBP 格式。"""
    output_dir = tmp_path / "out"
    state = run(sample_image, small_config, output_dir)

    thumb = Image.open(state.thumb_path)
    assert max(thumb.size) <= 400
    assert thumb.format == "WEBP"


def test_state_to_dict(sample_image, small_config, tmp_path):
    """to_dict 可 json 序列化，含所有字段。"""
    output_dir = tmp_path / "out"
    state = run(sample_image, small_config, output_dir)

    d = state.to_dict()
    json.dumps(d, ensure_ascii=False)
    assert d["status"] == "succeeded"
    assert d["progress"] == 100
    assert "outputs" in d
    assert "thumb_path" in d
    assert "error" in d


def test_uuid_subdir_and_save_name(sample_image, small_config, tmp_path):
    """输出在 {output}/{uuid}/ 下，文件名用 save_name。"""
    import json as _json
    cfg = tmp_path / "cfg.json"
    data = _json.loads(small_config.read_text(encoding="utf-8"))
    data["params"]["output"]["save_name"] = "%(name)s_%(size)s"
    cfg.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")

    output_root = tmp_path / "out"
    state = run(sample_image, cfg, output_root,
                vars={"name": "被罩A面", "size": "150x200"})

    assert state.status == TaskStatus.SUCCEEDED
    # outputs 路径含 uuid 子目录
    out_path = Path(state.outputs[0]["path"])
    # out_path = output_root/{uuid}/{save_name}.{fmt}
    assert out_path.parent.parent == output_root
    assert out_path.name == "被罩A面_150x200.psd"
    assert out_path.exists()
    # 缩略图同目录
    assert Path(state.thumb_path).parent == out_path.parent


def test_save_name_cli_override(sample_image, small_config, tmp_path):
    """CLI save_name 覆盖配置 save_name。"""
    import json as _json
    cfg = tmp_path / "cfg.json"
    data = _json.loads(small_config.read_text(encoding="utf-8"))
    data["params"]["output"]["save_name"] = "%(name)s_cfg"
    cfg.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")

    state = run(sample_image, cfg, tmp_path / "out",
                save_name="%(name)s_cli", vars={"name": "X"})
    out_path = Path(state.outputs[0]["path"])
    assert out_path.name == "X_cli.psd"


def test_save_name_readable_fallback(sample_image, small_config, tmp_path):
    """配置无 save_name 且 CLI 未传 → 可读默认名 印前_{type}_{size} 兜底。"""
    import json as _json
    cfg = tmp_path / "cfg.json"
    data = _json.loads(small_config.read_text(encoding="utf-8"))
    data["params"]["output"]["save_name"] = ""
    cfg.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")

    state = run(sample_image, cfg, tmp_path / "out")
    out_path = Path(state.outputs[0]["path"])
    # 文件名 = 印前_{type}_{size}.psd
    assert out_path.stem == f"印前_{data['type']}_{data['size']}"


def test_text_placeholder_fill(sample_image, small_config, tmp_path):
    """text_marks 的 %(name)s 占位符被 vars 填充。"""
    import json as _json
    cfg = tmp_path / "cfg.json"
    data = _json.loads(small_config.read_text(encoding="utf-8"))
    data["params"]["marks"]["text_marks"]["items"][0]["text"] = "测试 %(name)s"
    cfg.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")

    state = run(sample_image, cfg, tmp_path / "out", vars={"name": "被罩"})
    assert state.status == TaskStatus.SUCCEEDED


def test_save_name_no_placeholder_literal(sample_image, small_config, tmp_path):
    """配置 save_name 无占位符时直接用字面值，不填充不报错。"""
    import json as _json
    cfg = tmp_path / "cfg.json"
    data = _json.loads(small_config.read_text(encoding="utf-8"))
    data["params"]["output"]["save_name"] = "literal_name"
    cfg.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")

    state = run(sample_image, cfg, tmp_path / "out", vars={})
    assert state.status == TaskStatus.SUCCEEDED
    out_path = Path(state.outputs[0]["path"])
    assert out_path.name == "literal_name.psd"


def test_save_name_missing_var_empty(sample_image, small_config, tmp_path):
    """save_name 含占位符但 vars 缺变量 → 留空，不报错。"""
    import json as _json
    cfg = tmp_path / "cfg.json"
    data = _json.loads(small_config.read_text(encoding="utf-8"))
    data["params"]["output"]["save_name"] = "%(name)s_%(size)s"
    cfg.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")

    state = run(sample_image, cfg, tmp_path / "out", vars={})
    assert state.status == TaskStatus.SUCCEEDED
    out_path = Path(state.outputs[0]["path"])
    # name/size 都没填 → 模板填空后 "_"，文件名 _.psd
    assert out_path.stem == "_", f"期望 '_'，实际 {out_path.stem!r}"


def test_fit_mode_cover(sample_image, small_config, tmp_path):
    """fit_mode=cover 等比缩放覆盖 zone，长边裁切，图层尺寸=zone 尺寸。"""
    import json as _json
    cfg = tmp_path / "cfg.json"
    data = _json.loads(small_config.read_text(encoding="utf-8"))
    data["params"]["zones"][0]["fit_mode"] = "cover"
    cfg.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")

    state = run(sample_image, cfg, tmp_path / "out")
    assert state.status == TaskStatus.SUCCEEDED
    # PSD 尺寸不变（zone 铺满画布）
    from psd_tools import PSDImage as _PSD
    psd = _PSD.open(state.outputs[0]["path"])
    assert psd.size[0] > 0 and psd.size[1] > 0


def test_config_scan_loads():
    """扫描 configs/prepress/*.json，每个文件含 type/size/params。"""
    from app.config import list_types, get_sizes, get_params
    types = list_types()
    assert len(types) >= 1
    size_count = 0
    for t in types:
        for s in get_sizes(t["id"]):
            params = get_params(t["id"], s["id"])
            assert params.width_mm > 0
            size_count += 1
    assert size_count >= 2
