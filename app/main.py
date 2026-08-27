"""FastAPI 应用入口。

启动时加载 libvips，注册主事件循环给 WS 跨线程广播用。
运行：uv run uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app._vendor import load_vips
from app.web import ws as _ws
from app.web.routes import router

STATIC_DIR = "app/web/static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时注册主事件循环给 WS 跨线程广播用。"""
    _ws.set_loop(asyncio.get_running_loop())
    yield


def create_app() -> FastAPI:
    """构造 FastAPI app。"""
    load_vips()
    app = FastAPI(title="印前文件服务器", lifespan=lifespan)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(router)
    return app


app = create_app()
