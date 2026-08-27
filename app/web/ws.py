"""WebSocket 连接管理与广播。

任务线程（同步）通过 broadcast_threadsafe 把 State 推到事件循环，
事件循环再 send_text 给所有连接的前端。
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import WebSocket


# 已连接的 WebSocket 客户端
_connections: set[WebSocket] = set()
# 主事件循环（app 启动时设置，供同步线程提交协程）
_loop: Optional[asyncio.AbstractEventLoop] = None


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    """注册主事件循环，供同步线程跨线程提交协程。"""
    global _loop
    _loop = loop


async def connect(ws: WebSocket) -> None:
    """接受新连接并加入集合。"""
    await ws.accept()
    _connections.add(ws)


def disconnect(ws: WebSocket) -> None:
    """移除连接。"""
    _connections.discard(ws)


async def _broadcast(task_id: str, state_dict: dict) -> None:
    """向所有连接广播一条任务状态消息。"""
    msg = json.dumps({"task_id": task_id, **state_dict}, ensure_ascii=False)
    dead: list[WebSocket] = []
    for ws in list(_connections):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _connections.discard(ws)


def broadcast_threadsafe(task_id: str, state_dict: dict) -> None:
    """同步线程调用：把广播协程提交到主事件循环。"""
    if _loop is None:
        return
    asyncio.run_coroutine_threadsafe(_broadcast(task_id, state_dict), _loop)
