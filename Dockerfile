# ---- builder：编译工具链 + uv sync，产出 .venv ----
# pyvips 在 cp314 可能无预编译 wheel，需源码编译，故 builder 留 libvips-dev
FROM python:3.14-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libglib2.0-dev libvips-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python 依赖（利用层缓存：仅 pyproject/uv.lock 变化才重装）
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

# ---- final：仅运行时 libvips + 拷贝 venv ----
FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libvips libvips-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 编译好的虚拟环境直接拷入，不再带编译工具链
COPY --from=builder /app/.venv /app/.venv

# 应用代码 + 配置（configs 拷入作默认值，运行时被 compose volume 覆盖）
COPY app/ ./app/
COPY configs/ ./configs/

# venv 优先，直接 uvicorn 启动（无需 uv run 包一层）
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# 健康检查：/health 由 app/web/routes.py 提供
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
