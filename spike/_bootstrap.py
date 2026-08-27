"""spike 公共引导：加载 vendor/libvips 的 DLL。

Windows 下 pyvips 需要手动指向 libvips-42.dll 所在目录。
所有 spike 脚本开头 `from _bootstrap import *` 即可。
"""
import os
import sys
from pathlib import Path

# 项目根目录（spike/ 的上一级）
ROOT = Path(__file__).resolve().parent.parent
VIPS_BIN = ROOT / "vendor" / "libvips" / "bin"

if VIPS_BIN.exists():
    os.add_dll_directory(str(VIPS_BIN))
    os.environ["PATH"] = str(VIPS_BIN) + os.pathsep + os.environ["PATH"]

# spike/ 本身加入 sys.path，便于互相 import
sys.path.insert(0, str(Path(__file__).resolve().parent))

# 数据目录
DATA = ROOT / "data"
INPUTS = DATA / "inputs"      # 输入文件（上传的设计图）
OUTPUTS = DATA / "outputs"    # 输出文件（生成的印前文件）
IMAGES = DATA / "images"      # 文件库（生成结果归档，存储方式待定）
for d in (INPUTS, OUTPUTS, IMAGES):
    d.mkdir(parents=True, exist_ok=True)

# spike 临时输出
OUT = ROOT / "spike" / "out"
OUT.mkdir(parents=True, exist_ok=True)
