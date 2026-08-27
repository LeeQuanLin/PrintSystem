"""印前配置树：模型 + 加载 + 校验。

字段定义见 docs/02-配置文件规范.md §3，校验规则见 §3.9。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs" / "prepress" / "prepress.json"

# 类型/尺码 id：允许中文等非 ASCII，仅禁路径非法字符与空白
# （id 用于文件名/路径，不写入 PSD；zone.name 才写入 PSD，须 ASCII）
_SAFE_ID = re.compile(r"^[^/\\:*?\"<>|\s]+$")
# 图层名限 ASCII（psd-tools mac_roman 编码限制，见 CLAUDE.md）
_ASCII_NAME = re.compile(r"^[\x20-\x7E]+$")


class CornerCrop(BaseModel):
    """四角裁剪，统一样式（02 §3.5a）。"""
    model_config = ConfigDict(extra="forbid")

    style: Literal["square", "rounded", "chamfer"] = "square"
    radius_mm: float = Field(default=0, ge=0)
    chamfer_mm: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _check_style_params(self) -> "CornerCrop":
        if self.style == "rounded" and self.radius_mm <= 0:
            raise ValueError("rounded 样式需 radius_mm > 0")
        if self.style == "chamfer" and self.chamfer_mm <= 0:
            raise ValueError("chamfer 样式需 chamfer_mm > 0")
        return self


class AutoColor(BaseModel):
    """自动主色提取（02 §3.5d）。"""
    model_config = ConfigDict(extra="forbid")

    source: str
    method: Literal["dominant", "average"] = "dominant"


class Zone(BaseModel):
    """区域：图片区或纯色区（02 §3.5）。"""
    model_config = ConfigDict(extra="forbid")

    name: str
    type: Literal["image", "color"] = "image"
    x_mm: float
    y_mm: float
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    corner_crop: Optional[CornerCrop] = None
    offset_x_mm: float = 0
    offset_y_mm: float = 0
    scale: float = Field(default=1.0, gt=0)
    rotation: float = 0
    # 图片区专属
    fit_mode: Optional[Literal["stretch", "contain", "cover"]] = None
    # 纯色区专属
    color: Optional[list[int]] = None
    auto_color: Optional[AutoColor] = None

    @field_validator("name")
    @classmethod
    def _name_ascii(cls, v: str) -> str:
        if not _ASCII_NAME.match(v):
            raise ValueError(f"区名限 ASCII（psd-tools 限制）: {v!r}")
        return v

    @model_validator(mode="after")
    def _check_type_specific(self) -> "Zone":
        if self.type == "image":
            if self.fit_mode is None:
                self.fit_mode = "stretch"
            if self.color is not None or self.auto_color is not None:
                raise ValueError("图片区不应配置 color/auto_color")
        else:  # color
            if self.fit_mode is not None:
                raise ValueError("纯色区不应配置 fit_mode")
            has_color = self.color is not None
            has_auto = self.auto_color is not None
            if has_color == has_auto:  # 同时有或同时无
                raise ValueError("纯色区必须二选一：color 或 auto_color")
            if self.color is not None and len(self.color) != 3:
                raise ValueError("color 须为 3 元素 RGB")
        return self


class Background(BaseModel):
    """背景层（02 §3.4）。"""
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    fill_color: list[int] = Field(default_factory=lambda: [255, 255, 255])


class CropMarks(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    color: str = "black"
    width_mm: float = Field(default=0.2, gt=0)
    length_mm: float = Field(default=5, gt=0)
    offset_mm: float = Field(default=3, ge=0)
    dashed: bool = False              # 虚线开关
    dash_length_mm: float = Field(default=2, gt=0)   # 虚线段长
    gap_length_mm: float = Field(default=2, gt=0)    # 虚线间隙长


class ZipperMarks(BaseModel):
    """拉链标记线（02 §3.6a）。"""
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    side: Literal["top", "bottom", "left", "right"] = "left"
    span_mm: Optional[float] = Field(default=None, gt=0)
    pitch_mm: Optional[float] = Field(default=None, gt=0)
    line_width_mm: float = Field(default=0.5, gt=0)
    alignment: Literal["start", "center", "end", "distribute"] = "center"
    offset_mm: float = Field(default=5, ge=0)
    length_mm: float = Field(default=10, gt=0)
    color: str = "black"

    @model_validator(mode="after")
    def _check_span_pitch(self) -> "ZipperMarks":
        if self.enabled:
            if self.span_mm is None or self.pitch_mm is None:
                raise ValueError("拉链标记启用时需提供 span_mm 与 pitch_mm")
        return self


class TextMarkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str                # 支持 %(name)s 占位符，由 vars 填充
    x_mm: float
    y_mm: float
    rotation: float = 0


class TextMarks(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    color: str = "black"
    font_size_pt: float = 12
    items: list[TextMarkItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_items(self) -> "TextMarks":
        if self.enabled and not self.items:
            raise ValueError("文字标记启用时 items 不能为空")
        return self


class BorderMarks(BaseModel):
    """虚线边框标记（可作为裁剪线替代）。"""
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    color: str = "black"
    x_mm: float = 0                  # 左上角 X（毫米，相对画布左上角）
    y_mm: float = 0                  # 左上角 Y
    width_mm: float = Field(gt=0)    # 边框宽
    height_mm: float = Field(gt=0)   # 边框高
    width_mm_line: float = Field(default=0.17, gt=0)  # 线粗（毫米），0.17≈1px@150dpi
    dash_length_mm: float = Field(default=2, gt=0)    # 虚线段长
    gap_length_mm: float = Field(default=2, gt=0)     # 虚线间隙


class Marks(BaseModel):
    model_config = ConfigDict(extra="forbid")
    crop_marks: CropMarks = Field(default_factory=CropMarks)
    zipper_marks: ZipperMarks = Field(default_factory=ZipperMarks)
    text_marks: TextMarks = Field(default_factory=TextMarks)
    border_marks: BorderMarks | None = None


class Output(BaseModel):
    """输出设置。formats 支持多格式同时导出。save_name 支持占位符。"""
    model_config = ConfigDict(extra="forbid")
    formats: list[Literal["psd", "tif", "png"]] = Field(min_length=1)
    save_name: str = ""      # 保存名（含占位符 %(name)s），空则用 uuid 兜底


class Params(BaseModel):
    """印前参数（02 §3.3）。"""
    model_config = ConfigDict(extra="forbid")

    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    bleed_mm: float = Field(default=3, ge=0)
    dpi: int = Field(default=150, ge=1)
    bitdepth: Literal[8, 16] = 8
    color_profile: str = "srgb"
    background: Optional[Background] = None
    zones: list[Zone] = Field(min_length=1)
    marks: Marks = Field(default_factory=Marks)
    output: Output

    @model_validator(mode="after")
    def _check_zones(self) -> "Params":
        names = [z.name for z in self.zones]
        if len(names) != len(set(names)):
            raise ValueError(f"区域 name 尺码内不唯一: {names}")
        # auto_color.source 必须指向存在的图片区
        image_names = {z.name for z in self.zones if z.type == "image"}
        canvas_w = self.width_mm + 2 * self.bleed_mm
        canvas_h = self.height_mm + 2 * self.bleed_mm
        for z in self.zones:
            if z.auto_color and z.auto_color.source not in image_names:
                raise ValueError(
                    f"auto_color.source '{z.auto_color.source}' 未指向存在的图片区"
                )
            # 区域在画布范围内
            if z.x_mm < 0 or z.y_mm < 0 or z.x_mm + z.width_mm > canvas_w or z.y_mm + z.height_mm > canvas_h:
                raise ValueError(
                    f"区域 {z.name} 超出画布范围 ({canvas_w}×{canvas_h}mm)"
                )
        return self


class SizeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    params: Params

    @field_validator("id")
    @classmethod
    def _id_safe(cls, v: str) -> str:
        if not _SAFE_ID.match(v):
            raise ValueError(f"尺码 id 含非法字符（禁 / \\ : * ? \" < > | 及空白）: {v!r}")
        return v


class TypeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    sizes: list[SizeEntry]

    @field_validator("id")
    @classmethod
    def _id_safe(cls, v: str) -> str:
        if not _SAFE_ID.match(v):
            raise ValueError(f"类型 id 含非法字符（禁 / \\ : * ? \" < > | 及空白）: {v!r}")
        return v

    @model_validator(mode="after")
    def _size_ids_unique(self) -> "TypeEntry":
        ids = [s.id for s in self.sizes]
        if len(ids) != len(set(ids)):
            raise ValueError(f"尺码 id 类型内不唯一: {ids}")
        if not self.sizes:
            raise ValueError("类型至少需 1 个尺码")
        return self


class PrepressConfig(BaseModel):
    """印前配置树根。"""
    model_config = ConfigDict(extra="forbid")
    version: int
    types: list[TypeEntry]

    @model_validator(mode="after")
    def _type_ids_unique(self) -> "PrepressConfig":
        ids = [t.id for t in self.types]
        if len(ids) != len(set(ids)):
            raise ValueError(f"类型 id 全局不唯一: {ids}")
        if not self.types:
            raise ValueError("配置至少需 1 个类型")
        return self


def load(path: Path = CONFIG_PATH) -> PrepressConfig:
    """加载并校验印前配置。校验失败抛 ValidationError。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return PrepressConfig.model_validate(data)
