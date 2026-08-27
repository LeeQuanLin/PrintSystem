"""印前文件生成脚本。

函数 run(image, config, output, state) 接收图片路径、配置路径、输出路径、可选 state 对象，
生成分层 PSD 并返回更新后的 State。

CLI 用法：
    uv run python -m app.tasks.scripts.prepress \
        --image <图片路径> \
        --config <尺码配置 json 路径> \
        --output <输出 PSD 路径> \
        [--state <可选，最终 state 写入此 JSON 路径>]
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

# 家纺印前图普遍超 PIL 默认 89M 像素上限，放开
Image.MAX_IMAGE_PIXELS = None

from app._vendor import load_vips
from app.config.prepress import Params, Zone

from ._canvas import compute_canvas, zone_to_px
from ._config import load_params
from ._marks import (
    make_border_marks_layer,
    make_crop_marks_layer,
    make_text_marks_layer,
    make_zipper_marks_layer,
)
from ._psd_io import build_psd, generate_thumbnail_from_psd, save_flat, save_psd
from ._state import State, TaskStatus
from ._zones import (
    extract_color,
    make_color_layer,
    process_image_zone,
)


def _place_on_canvas(layer: Image.Image, zp, canvas) -> Image.Image:
    """把 zone 尺寸的层按像素坐标放到画布尺寸透明层上。"""
    full = Image.new("RGBA", (canvas.width_px, canvas.height_px), (0, 0, 0, 0))
    full.alpha_composite(layer, (zp.x_px, zp.y_px))
    return full


def _resolve_color(zone: Zone, image_path: Path) -> tuple[int, int, int]:
    """解析纯色区颜色：手动色或从源图提取。"""
    if zone.color is not None:
        r, g, b = zone.color
        return (int(r), int(g), int(b))

    if zone.auto_color is not None:
        src = Image.open(image_path).convert("RGB")
        return extract_color(src, zone.auto_color.method)

    raise ValueError(f"纯色区 {zone.name} 既无 color 也无 auto_color")


def _fill_template(template: str, vars_dict: dict[str, str]) -> str:
    """
    填充 %(name)s 模板。未提供的变量留空（空字符串），不报错。

    Args:
        template: 含 %(name)s 占位符的模板
        vars_dict: 变量字典

    Returns:
        填充后的字符串
    """
    import re
    names = re.findall(r"%\(([^)]+)\)", template)
    full_vars = {n: vars_dict.get(n, "") for n in names}
    return template % full_vars


def _resolve_save_name(
    cli_save_name: str | None,
    config_save_name: str,
    vars_dict: dict[str, str],
    type_id: str | None = None,
    size_id: str | None = None,
) -> tuple[str, str]:
    """
    解析最终保存名与 UUID。

    优先级：CLI --save-name > 配置 save_name > 可读默认名 `印前_{type}_{size}`。
    - 模板无占位符：直接用字面值
    - 模板有占位符：用 vars_dict 填充，未提供的变量留空

    Args:
        cli_save_name: CLI 传入的 save_name（可能为 None）
        config_save_name: 配置里的 save_name
        vars_dict: 占位符变量字典
        type_id / size_id: 用于可读默认名兜底

    Returns:
        (save_name, uuid) —— save_name 已填充占位符，uuid 用于子目录名
    """
    import re
    uuid_str = uuid.uuid4().hex
    if cli_save_name:
        template = cli_save_name
    elif config_save_name:
        template = config_save_name
    else:
        # 可读兜底：印前_{type}_{size}；仍缺失则用 uuid
        parts = [p for p in ("印前", type_id, size_id) if p]
        template = "_".join(parts) if len(parts) > 1 else uuid_str
    if re.search(r"%\(([^)]+)\)", template):
        save_name = _fill_template(template, vars_dict)
    else:
        save_name = template
    save_name = _sanitize_filename(save_name)
    # 兜底名可能因 sanitize 变空
    if not save_name:
        save_name = uuid_str
    return save_name, uuid_str


def _sanitize_filename(name: str) -> str:
    """替换文件名非法字符为下划线。"""
    import re
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def run(
    image: str | Path,
    config: str | Path,
    output: str | Path,
    state: State | None = None,
    save_name: str | None = None,
    vars: dict[str, str] | None = None,
) -> State:
    """
    生成印前文件。

    输出到 {output}/{uuid}/{save_name}.{fmt}，含源文件与缩略图。

    Args:
        image: 输入图片路径
        config: 尺码配置 json 路径
        output: 输出根目录（在其下建 uuid 子目录）
        state: 可选，外部传入的 State 对象
        save_name: 可选，覆盖配置的 save_name（仍解析占位符）
        vars: 占位符变量字典，填充 save_name 与 text_marks 的 %(name)s

    Returns:
        更新后的 State 对象（失败时不抛异常，state.status=FAILED）
    """
    state = state or State()
    image_path = Path(image)
    output_root = Path(output)
    vars_dict = vars or {}

    try:
        # 加载配置
        state.update("加载配置", 5, str(config))
        load_vips()
        params: Params = load_params(config)
        # 读配置顶层 type/size，用于可读默认保存名兜底
        import json as _json
        with open(Path(config), encoding="utf-8") as _f:
            _meta = _json.load(_f)
        type_id = _meta.get("type")
        size_id = _meta.get("size")

        # 解析保存名 + uuid
        final_save_name, uuid_str = _resolve_save_name(
            save_name, params.output.save_name, vars_dict, type_id, size_id
        )
        # 输出目录：output_root/{uuid}/
        out_dir = output_root / uuid_str
        state.update("预检", 10, f"save_name={final_save_name} uuid={uuid_str}")

        if not image_path.exists():
            raise FileNotFoundError(f"输入图片不存在: {image_path}")
        src_img = Image.open(image_path)
        state.message = f"输入 {src_img.size[0]}×{src_img.size[1]} {src_img.mode}"

        # 画布
        canvas = compute_canvas(
            params.width_mm, params.height_mm, params.bleed_mm, params.dpi
        )
        state.update("画布", 15, f"{canvas.width_px}×{canvas.height_px}px")

        # 处理区域
        zone_layers: list[tuple[str, Image.Image]] = []
        n_zones = len(params.zones)
        for i, zone in enumerate(params.zones):
            zp = zone_to_px(zone, params.dpi)
            if zone.type == "image":
                layer = process_image_zone(zone, image_path, params.dpi)
            else:  # color
                color = _resolve_color(zone, image_path)
                layer = make_color_layer(zone, params.dpi, color)
            full = _place_on_canvas(layer, zp, canvas)
            zone_layers.append((zone.name, full))
            progress = 15 + int((i + 1) / n_zones * 45)
            state.update("处理区域", progress, f"{zone.name} ({i+1}/{n_zones})")

        # 标记层
        mark_layers: list[tuple[str, Image.Image]] = []
        cm = params.marks.crop_marks
        if cm.enabled:
            mark_layers.append((
                "CropMarks",
                make_crop_marks_layer(canvas, params.width_mm, params.height_mm, cm, params.dpi),
            ))
        zm = params.marks.zipper_marks
        if zm.enabled:
            mark_layers.append((
                "ZipperMarks",
                make_zipper_marks_layer(canvas, params.width_mm, params.height_mm, zm, params.dpi),
            ))
        tm = params.marks.text_marks
        if tm.enabled:
            # text 占位符填充：含占位符才填充，未提供变量留空
            import re as _re
            tm_filled = tm.model_copy(deep=True)
            for item in tm_filled.items:
                if _re.search(r"%\(([^)]+)\)", item.text):
                    item.text = _fill_template(item.text, vars_dict)
            mark_layers.append((
                "TextMarks",
                make_text_marks_layer(canvas, tm_filled, params.dpi),
            ))
        bm = params.marks.border_marks
        if bm is not None and bm.enabled:
            mark_layers.append((
                "BorderMarks",
                make_border_marks_layer(canvas, bm, params.dpi),
            ))
        state.update("标记层", 85, f"{len(mark_layers)} 个标记层")

        # 组装 PSD
        psd = build_psd(canvas, params.background, zone_layers, mark_layers, dpi=params.dpi)
        state.update("组装 PSD", 90, f"层数={len(psd)} dpi={params.dpi}")

        # 写入：out_dir = {output_root}/{uuid}/，文件名用 final_save_name
        out_dir.mkdir(parents=True, exist_ok=True)
        base_name = final_save_name

        outputs: list[dict[str, Any]] = []
        formats = params.output.formats
        for i, fmt in enumerate(formats):
            file_path = out_dir / f"{base_name}.{fmt}"
            if fmt == "psd":
                save_psd(psd, file_path)
            else:  # tif / png
                save_flat(psd, file_path, fmt, params.dpi)
            outputs.append({
                "path": str(file_path),
                "format": fmt,
                "width_px": canvas.width_px,
                "height_px": canvas.height_px,
                "layers": len(psd) if fmt == "psd" else 1,
            })
            state.update("写入", 90 + int((i + 1) / len(formats) * 5),
                         f"{fmt} -> {file_path.name}")

        # 缩略图（直接从 psd 对象合成，无需重读文件）
        thumb_path = out_dir / f"{base_name}.thumb.webp"
        generate_thumbnail_from_psd(psd, thumb_path)
        state.update("写入", 95, f"缩略图 -> {thumb_path.name}")

        state.succeed(
            outputs=outputs,
            message=f"生成完成 {len(psd)} 层，{len(outputs)} 个文件 uuid={uuid_str}",
            thumb_path=str(thumb_path),
        )
    except Exception as e:
        state.fail(f"{type(e).__name__}: {e}")

    return state


def main() -> None:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(
        description="印前文件生成脚本：图片 + 配置 → 多格式输出"
    )
    parser.add_argument("--image", required=True, help="输入图片路径")
    parser.add_argument("--config", required=True, help="尺码配置 json 路径")
    parser.add_argument("--output", required=True, help="输出根目录（在其下建 uuid 子目录）")
    parser.add_argument(
        "--save-name",
        default=None,
        help="可选，覆盖配置的 save_name（仍解析占位符）",
    )
    parser.add_argument(
        "--vars",
        nargs="*",
        default=[],
        metavar="KEY=VAL",
        help="占位符变量，多个 key=val 形式，填充 save_name 与 text_marks 的 %%(name)s",
    )
    parser.add_argument(
        "--state",
        default=None,
        help="可选，最终 state 写入此 JSON 路径",
    )
    args = parser.parse_args()

    # 解析 --vars key=val → dict
    vars_dict: dict[str, str] = {}
    for kv in args.vars:
        if "=" not in kv:
            print(f"warning: 忽略非法 --vars 项 {kv!r}（需 key=val）", file=sys.stderr)
            continue
        k, v = kv.split("=", 1)
        vars_dict[k] = v

    state = run(args.image, args.config, args.output,
                save_name=args.save_name, vars=vars_dict)

    if args.state:
        state_path = Path(args.state)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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
