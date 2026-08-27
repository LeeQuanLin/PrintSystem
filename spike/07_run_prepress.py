"""spike 07：CLI 调用印前脚本，用真实图片生成 测试.psd。

等价命令：
    uv run python -m app.tasks.scripts.prepress \
        --image "data/inputs/src 哈利波特3.png" \
        --config "configs/prepress/sizes/test_152x202.json" \
        --output "data/outputs/测试.psd" \
        --state "data/outputs/测试.state.json"

本脚本用 subprocess 调 CLI，验证命令行可用。
"""
from _bootstrap import *  # noqa: F401,F403  提供 ROOT
import subprocess
import sys


def main():
    image = INPUTS / "src 哈利波特3.png"
    config = ROOT / "configs" / "prepress" / "sizes" / "test_152x202.json"
    output = OUTPUTS / "测试.psd"
    state = OUTPUTS / "测试.state.json"

    if not image.exists():
        raise SystemExit(f"源图不存在: {image}")

    cmd = [
        sys.executable, "-m", "app.tasks.scripts.prepress",
        "--image", str(image),
        "--config", str(config),
        "--output", str(output),
        "--state", str(state),
    ]
    print(f"[run] {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode == 0:
        print(f"\n[OK] {output}  ({output.stat().st_size:,} bytes)")
        print(f"[state] {state}")
    else:
        print(f"\n[FAIL] 退出码 {result.returncode}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
