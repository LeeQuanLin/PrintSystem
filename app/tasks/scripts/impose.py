"""排版拼版脚本（pyvips 引擎）。

函数 run(slots, preset, output, state, save_name) 把多个图件按网格拼到一张带透明 alpha
的普通 TIF，返回更新后的 State。

输入槽位用文件路径（已解析），引擎不依赖文件库/image_id——image_id→路径解析在 web 层
（与印前 run 接收 image_path 一致）。

CLI 用法：
    uv run python -m app.tasks.scripts.impose \
        --preset <预设 id> \
        --config <impose.json 路径> \
        --output <输出根目录> \
        --slots <path;rotation=90;fit=stretch> <path;rotation=180> ... \
        [--save-name <名>] [--state <state.json 路径>]

    --slots 每项：图件路径后接可选 ;rotation=<0|90|180|270>;fit=<stretch|contain|cover>。
    空槽位用字面量 null。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app._vendor import load_vips

load_vips()

import pyvips

from app.config.impose import ImposeConfig, Preset

from ._canvas import mm_to_px
from ._impose_geom import ImposeCanvas, compute_flow_layout, compute_impose_canvas
from ._impose_io import load_image, make_thumbnail, rotate_cw, write_alpha_tif
from ._state import State, TaskStatus

_VALID_ROT = {0, 90, 180, 270}
_VALID_FIT = {"stretch", "contain", "cover"}
_FIT_ROT_RE = re.compile(r";\s*(rotation|fit)\s*=\s*([^;]+)")


@dataclass
class SlotInput:
    """一个槽位的输入描述。path 为 None 表示空槽位。"""

    path: str | Path | None
    rotation: int = 0
    fit_mode: str | None = None  # None → 用 preset.layout.default_fit_mode


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def _resolve_save_name(cli_save_name: str | None, preset_id: str) -> tuple[str, str]:
    """返回 (save_name, uuid)。优先 CLI，兜底 排版_{preset_id}。"""
    uuid_str = uuid.uuid4().hex
    if cli_save_name:
        name = _sanitize_filename(cli_save_name)
    else:
        name = _sanitize_filename(f"排版_{preset_id}")
    if not name:
        name = uuid_str
    return name, uuid_str


def load_preset(config_path: str | Path, preset_id: str) -> Preset:
    """从 impose.json 加载并返回指定预设。"""
    with open(Path(config_path), encoding="utf-8") as f:
        data = json.load(f)
    cfg = ImposeConfig.model_validate(data)
    for p in cfg.presets:
        if p.id == preset_id:
            return p
    raise KeyError(f"排版预设不存在: {preset_id}")


def _build_canvas(canvas_px) -> pyvips.Image:
    """创建全透明 RGBA 画布（sRGB interpretation）。"""
    rgb = pyvips.Image.black(canvas_px.width_px, canvas_px.height_px, bands=3).copy(
        interpretation=pyvips.Interpretation.SRGB
    )
    alpha = pyvips.Image.black(canvas_px.width_px, canvas_px.height_px, bands=1)
    return rgb.bandjoin(alpha)


def _insert_slot(canvas: pyvips.Image, overlay: pyvips.Image, x: int, y: int) -> pyvips.Image:
    """把 overlay 放到 canvas (x,y)，越界部分裁掉（防舍入溢出）。"""
    avail_w = canvas.width - x
    avail_h = canvas.height - y
    if overlay.width > avail_w or overlay.height > avail_h:
        overlay = overlay.crop(0, 0, min(overlay.width, avail_w), min(overlay.height, avail_h))
    return canvas.insert(overlay, x, y)


def run(
    slots: list[SlotInput],
    preset: Preset,
    output: str | Path,
    state: State | None = None,
    save_name: str | None = None,
) -> State:
    """
    执行排版拼版，输出带 alpha 的普通 TIF 到 {output}/{uuid}/{save_name}.tif。

    图件按原始尺寸（仅旋转，不缩放）行优先流式铺排，从画布左上角开始，无间距无边距。
    任一图件超出画布边界则失败。

    Args:
        slots: 图件输入列表（顺序即铺排顺序），每项 {path, rotation}
        preset: 排版预设（含 canvas/output）
        output: 输出根目录（在其下建 uuid 子目录）
        state: 可选外部 State
        save_name: 可选，覆盖默认保存名

    Returns:
        更新后的 State（失败时不抛异常，state.status=FAILED）
    """
    state = state or State()
    output_root = Path(output)

    try:
        load_vips()

        state.update("载入图件", 5, f"图件数={len(slots)}")

        canvas_px = compute_impose_canvas(preset.canvas)
        state.update("载入图件", 10, f"画布 {canvas_px.width_px}×{canvas_px.height_px}px")

        # 载入并旋转（不缩放）
        loaded: list[pyvips.Image] = []
        n = len(slots)
        for i, s in enumerate(slots):
            rot = s.rotation if s.rotation in _VALID_ROT else 0
            img = load_image(s.path, _infer_fmt(s.path))
            img = rotate_cw(img, rot)
            loaded.append(img)
            state.update("载入图件", 10 + int((i + 1) / n * 20),
                         f"图件 {i} ({img.width}×{img.height}px)")

        # 流式布局（按旋转后实际尺寸）
        image_sizes = [(img.width, img.height) for img in loaded]
        placements = compute_flow_layout(image_sizes, canvas_px)
        state.update("拼版合成", 35, f"布局完成 {len(placements)} 个图件")

        # 合成
        canvas = _build_canvas(canvas_px)
        for i, (img, pl) in enumerate(zip(loaded, placements)):
            canvas = _insert_slot(canvas, img, pl.x_px, pl.y_px)
            state.update("拼版合成", 35 + int((i + 1) / n * 45),
                         f"图件 {i} → ({pl.x_px},{pl.y_px})")

        # 写出（无标记）
        final_save_name, uuid_str = _resolve_save_name(save_name, preset.id)
        out_dir = output_root / uuid_str
        out_dir.mkdir(parents=True, exist_ok=True)
        tif_path = out_dir / f"{final_save_name}.tif"
        state.update("写 TIF", 85, str(tif_path.name))
        write_alpha_tif(canvas, tif_path, canvas_px.dpi, preset.output.compression)

        # 缩略图
        thumb_path = out_dir / f"{final_save_name}.thumb.webp"
        make_thumbnail(canvas, thumb_path)

        outputs: list[dict[str, Any]] = [{
            "path": str(tif_path),
            "format": "tif",
            "width_px": canvas_px.width_px,
            "height_px": canvas_px.height_px,
            "layers": 1,
        }]
        state.succeed(
            outputs=outputs,
            message=f"排版完成 {canvas_px.width_px}×{canvas_px.height_px}px uuid={uuid_str}",
            thumb_path=str(thumb_path),
        )
    except Exception as e:
        state.fail(f"{type(e).__name__}: {e}")

    return state


def _infer_fmt(path: str | Path) -> str:
    """按扩展名推断格式（供 load_image 分流 PSD）。"""
    ext = Path(path).suffix.lower().lstrip(".")
    return {"tif": "tif", "tiff": "tif", "png": "png", "jpg": "jpg", "jpeg": "jpg",
            "psd": "psd", "webp": "webp"}.get(ext, ext or "png")


def _parse_slot(token: str) -> SlotInput:
    """解析 CLI 单个 --slots 项：path;rotation=90;fit=stretch 或 null。"""
    token = token.strip()
    if token.lower() == "null":
        return SlotInput(path=None)
    parts = token.split(";", 1)
    path = parts[0].strip()
    rotation = 0
    fit: str | None = None
    if len(parts) > 1:
        for m in _FIT_ROT_RE.finditer(parts[1]):
            key, val = m.group(1), m.group(2).strip()
            if key == "rotation":
                rotation = int(val)
            elif key == "fit":
                fit = val
    return SlotInput(path=path, rotation=rotation, fit_mode=fit)


def main() -> None:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(description="排版拼版：多图件 → 带透明 alpha 的普通 TIF")
    parser.add_argument("--preset", required=True, help="预设 id")
    parser.add_argument("--config", required=True, help="impose.json 路径")
    parser.add_argument("--output", required=True, help="输出根目录（在其下建 uuid 子目录）")
    parser.add_argument("--slots", nargs="+", required=True,
                        metavar="path;rotation=90;fit=stretch",
                        help="槽位（行优先），空槽用 null")
    parser.add_argument("--save-name", default=None, help="可选，覆盖默认保存名")
    parser.add_argument("--state", default=None, help="可选，最终 state 写入此 JSON 路径")
    args = parser.parse_args()

    preset = load_preset(args.config, args.preset)
    slots = [_parse_slot(t) for t in args.slots]

    state = run(slots, preset, args.output, save_name=args.save_name)

    if args.state:
        sp = Path(args.state)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"status: {state.status.value}")
    print(f"progress: {state.progress}%")
    print(f"stage: {state.stage}")
    print(f"message: {state.message}")
    for o in state.outputs:
        print(f"output: {o['path']}")
    if state.thumb_path:
        print(f"thumb: {state.thumb_path}")
    if state.error:
        print(f"error: {state.error}", file=sys.stderr)

    sys.exit(0 if state.status == TaskStatus.SUCCEEDED else 1)


if __name__ == "__main__":
    main()
