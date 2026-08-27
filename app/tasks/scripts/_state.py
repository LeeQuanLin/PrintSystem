"""任务状态领域对象。

脚本执行过程中通过 State.update() 更新进度，外部读取 State 拿当前状态。
CLI 模式下可选把最终 state 序列化为 JSON 写文件。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class TaskStatus(str, Enum):
    """任务状态枚举。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class State:
    """任务状态领域对象。"""

    status: TaskStatus = TaskStatus.PENDING
    stage: str = ""                # 当前阶段名
    progress: int = 0              # 0-100
    message: str = ""              # 当前详情
    outputs: list[dict[str, Any]] = field(default_factory=list)
    thumb_path: str = ""           # 缩略图路径（独立于 outputs）
    error: str = ""
    on_update: Optional[Callable[["State"], None]] = None  # 状态变更回调

    def update(self, stage: str, progress: int, message: str = "") -> None:
        """
        更新进度。

        Args:
            stage: 阶段名（如 "预检" / "处理图片区"）
            progress: 0-100 进度百分比
            message: 详情
        """
        self.stage = stage
        self.progress = max(0, min(100, progress))
        self.message = message
        self.status = TaskStatus.RUNNING
        self._notify()

    def succeed(
        self,
        outputs: list[dict[str, Any]] | None = None,
        message: str = "完成",
        thumb_path: str = "",
    ) -> None:
        """标记任务成功完成。"""
        self.status = TaskStatus.SUCCEEDED
        self.progress = 100
        self.outputs = outputs or []
        self.thumb_path = thumb_path
        self.message = message
        self.error = ""
        self._notify()

    def fail(self, error: str) -> None:
        """标记任务失败。"""
        self.status = TaskStatus.FAILED
        self.error = error
        self.message = error
        self._notify()

    def _notify(self) -> None:
        """触发 on_update 回调（若已注册）。"""
        if self.on_update is not None:
            try:
                self.on_update(self)
            except Exception:
                pass  # 回调失败不影响任务执行

    def to_dict(self) -> dict[str, Any]:
        """序列化为可 JSON 化的 dict（不含 on_update 回调）。"""
        d = asdict(self)
        d["status"] = self.status.value
        d.pop("on_update", None)
        return d
