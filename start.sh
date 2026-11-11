#!/bin/bash
# ============================================
#   芯光数智 · 智能运维平台 启动脚本（Linux / 云服务器）
#   用法：chmod +x start.sh && ./start.sh
# ============================================
set -e
cd "$(dirname "$0")"

echo "========================================"
echo "   芯光数智 · 智能运维平台 启动"
echo "========================================"

# 1. 检查 Docker
if ! command -v docker &> /dev/null; then
  echo "[错误] 未安装 Docker，请先安装 Docker Engine + Compose 插件"
  exit 1
fi
if ! docker compose version &> /dev/null; then
  echo "[错误] Docker Compose 插件不可用（需要 docker compose，而不是 docker-compose）"
  exit 1
fi

# 2. 等待 Docker 就绪
echo "[1/3] 等待 Docker 就绪..."
for i in $(seq 1 90); do
  if docker info >/dev/null 2>&1; then break; fi
  sleep 2
done
docker info >/dev/null 2>&1 || { echo "[错误] Docker 未就绪"; exit 1; }
echo "    Docker 已就绪"

# 3. 启动容器
echo "[2/3] 启动平台容器..."
docker compose up -d

# 4. 等待服务
echo "[3/3] 等待服务就绪..."
sleep 20

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo ""
echo "========================================"
echo "    平台已启动！"
echo "    本机访问:  http://localhost:8080"
if [ -n "$IP" ]; then
  echo "    局域网/公网: http://$IP:8080"
fi
echo "    账号:      admin / admin123456"
echo "========================================"
echo ""
