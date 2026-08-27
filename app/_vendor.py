"""外部依赖加载：libvips DLL。

Windows 下 pyvips 需手动指向 libvips-42.dll 所在目录（vendor/libvips/bin）。
Linux Docker 部署时 libvips 装在系统路径，无需此处理。

spike 验证结论：必须同时 add_dll_directory + PATH 双设才能加载（见 CLAUDE.md 3a）。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIPS_BIN = ROOT / "vendor" / "libvips" / "bin"


def load_vips():
    """加载 vendor 下的 libvips DLL。仅在 Windows + vendor 目录存在时生效。"""
    if not VIPS_BIN.exists():
        # Linux/Docker：libvips 在系统路径，pyvips 可直接 import
        return
    if sys.platform == "win32":
        os.add_dll_directory(str(VIPS_BIN))
        os.environ["PATH"] = str(VIPS_BIN) + os.pathsep + os.environ.get("PATH", "")
