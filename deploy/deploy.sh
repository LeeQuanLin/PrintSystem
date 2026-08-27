#!/usr/bin/env bash
# 部署印前文件服务器到 Ubuntu Server
#
# 流程：rsync 同步源码（排除 vendor/本地数据）→ ssh 远程装 Docker（若缺）→ docker compose up -d --build
#
# 用法：
#   SERVER=user@host REMOTE_DIR=/opt/prepress bash deploy/deploy.sh
#
# 环境变量：
#   SERVER      必填，SSH 目标，如 ubuntu@10.0.0.1
#   REMOTE_DIR  选填，服务器项目路径，默认 /opt/prepress
set -euo pipefail

: "${SERVER:?请设置 SERVER=user@host}"
REMOTE_DIR="${REMOTE_DIR:-/opt/prepress}"

echo "==> 同步源码到 ${SERVER}:${REMOTE_DIR}（排除 vendor / 本地数据 / .venv）"
rsync -azP --delete \
    --exclude='vendor/' \
    --exclude='.venv/' \
    --exclude='data/' \
    --exclude='logs/' \
    --exclude='.git/' \
    --exclude='__pycache__/' \
    --exclude='**/__pycache__/' \
    --exclude='*.pyc' \
    --exclude='spike/' \
    --exclude='.claude/' \
    ./ "${SERVER}:${REMOTE_DIR}/"

echo "==> 远程：确保 Docker 已安装并启动服务"
ssh "${SERVER}" "bash -s" <<'REMOTE'
set -euo pipefail
# Docker 未装则安装（Ubuntu 官方仓库）
if ! command -v docker >/dev/null 2>&1; then
    echo "Docker 未安装，开始安装..."
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo systemctl enable --now docker
else
    echo "Docker 已安装：$(docker --version)"
fi
# compose 插件检查
if ! docker compose version >/dev/null 2>&1; then
    echo "缺少 docker compose 插件，安装 docker-compose-plugin"
    sudo apt-get update && sudo apt-get install -y docker-compose-plugin
fi
REMOTE

echo "==> 远程：构建并启动容器"
ssh "${SERVER}" "cd ${REMOTE_DIR} && docker compose up -d --build"

echo "==> 部署完成。验证："
echo "    ssh ${SERVER} 'curl -s http://localhost:8000/health'"
echo "    浏览器访问 http://<服务器IP>:8000"
