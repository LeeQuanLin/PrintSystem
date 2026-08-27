"""单尺码配置加载。

每个尺码配置单独一个 json 文件，结构：{type, size, name, params:{...}}。
复用 app/config/prepress.py 的 pydantic 模型校验 params。
"""
from __future__ import annotations

import json
from pathlib import Path

from app.config.prepress import Params


def load_params(config_path: str | Path) -> Params:
    """
    加载单个尺码配置文件并校验。

    Args:
        config_path: 尺码配置 json 路径

    Returns:
        Params 校验后的模型实例

    Raises:
        FileNotFoundError: 文件不存在
        ValidationError: 配置不合法
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return Params.model_validate(data["params"])
