"""排版配置：模型 + 加载 + 校验。

字段定义见 docs/02-配置文件规范.md §4。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs" / "impose" / "impose.json"
_ASCII_ID = re.compile(r"^[A-Za-z0-9_]+$")


class Canvas(BaseModel):
    model_config = ConfigDict(extra="forbid")
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    dpi: int = Field(default=150, ge=1)
    bitdepth: Literal[8, 16] = 8


class Gutters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    horizontal_mm: float = Field(default=0, ge=0)
    vertical_mm: float = Field(default=0, ge=0)
    margin_mm: float = Field(default=0, ge=0)


class ImposeMarks(BaseModel):
    model_config = ConfigDict(extra="forbid")
    crop_marks: bool = True
    crop_mark_length_mm: float = Field(default=5, gt=0)
    crop_mark_offset_mm: float = Field(default=3, ge=0)
    registration_marks: bool = False


class ImposeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["tif"] = "tif"
    compression: str = "deflate"
    color_profile: str = "srgb"


class Preset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    canvas: Canvas
    gutters: Gutters = Field(default_factory=Gutters)
    marks: ImposeMarks = Field(default_factory=ImposeMarks)
    output: ImposeOutput

    @field_validator("id")
    @classmethod
    def _id_ascii(cls, v: str) -> str:
        if not _ASCII_ID.match(v):
            raise ValueError(f"预设 id 限 ASCII: {v!r}")
        return v


class ImposeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int
    presets: list[Preset]

    @model_validator(mode="after")
    def _ids_unique(self) -> "ImposeConfig":
        ids = [p.id for p in self.presets]
        if len(ids) != len(set(ids)):
            raise ValueError(f"预设 id 全局不唯一: {ids}")
        if not self.presets:
            raise ValueError("排版配置至少需 1 个预设")
        return self


def load(path: Path = CONFIG_PATH) -> ImposeConfig:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return ImposeConfig.model_validate(data)
