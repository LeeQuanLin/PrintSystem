"""配置模块自检：加载真实配置文件，打印类型/尺码树，确认校验通过。

运行：uv run python -m app.config
"""
from __future__ import annotations

from . import (
    get_impose,
    get_params,
    get_sizes,
    get_storage,
    list_impose_presets,
    list_types,
)


def main() -> None:
    print("=== 印前配置 ===")
    for t in list_types():
        print(f"  {t['id']}  {t['name']}")
        for s in get_sizes(t["id"]):
            print(f"    └─ {s['id']}  {s['name']}")
    # 抽查一个尺码的参数
    p = get_params("bedsheet", "150x200")
    print(f"\n  抽查 bedsheet/150x200 参数:")
    print(f"    画布: {p.width_mm}×{p.height_mm}mm  出血:{p.bleed_mm}mm  dpi:{p.dpi}")
    print(f"    区域: {[z.name + '(' + z.type + ')' for z in p.zones]}")
    print(f"    标记: crop={p.marks.crop_marks.enabled} "
          f"zipper={p.marks.zipper_marks.enabled} text={p.marks.text_marks.enabled}")

    print("\n=== 排版配置 ===")
    for preset in list_impose_presets():
        print(f"  {preset['id']}  {preset['name']}")

    print("\n=== 存储配置 ===")
    s = get_storage()
    print(f"  library: {s.library.path}  db: {s.library.db_filename}")
    print(f"  thumbnail: {s.thumbnail.format} {s.thumbnail.max_size_px}px q{s.thumbnail.quality}")
    print(f"  tasks.max_concurrency: {s.tasks.max_concurrency}")
    print(f"  db_path: {s.db_path}")

    print("\n[OK] 配置全部加载并校验通过")


if __name__ == "__main__":
    main()
