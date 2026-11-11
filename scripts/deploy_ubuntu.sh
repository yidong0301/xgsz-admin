#!/usr/bin/env bash
# 芯光数智 · Ubuntu 一键部署
# 用法：
#   cp .env.ubuntu.example .env && vi .env
#   sudo bash scripts/deploy_ubuntu.sh
# 可选环境变量：
#   SELF_SIGNED=1   使用自签证书（内网/测试）
#   SEED_DEMO=1     导入演示数据
#   ADMIN_RESET=1   重置 admin 密码为 .env 中的 ADMIN_PASSWORD
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f docker-compose.ubuntu.yml)

log() { echo -e "\n\033[1;36m>>> $*\033[0m"; }
die() { echo -e "\033[1;31m[ERROR] $*\033[0m" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "未安装 Docker，请先安装 Docker Engine"
docker compose version >/dev/null 2>&1 || die "未安装 Docker Compose v2"
docker info >/dev/null 2>&1 || die "当前用户无法访问 Docker（请用 root 或加入 docker 组）"

if [[ ! -f .env ]]; then
  cp .env.ubuntu.example .env
  die "已生成 .env，请编辑 DOMAIN / DB_PASS / SECRET_KEY 后重新执行"
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

: "${DOMAIN:?请在 .env 配置 DOMAIN}"
: "${DB_PASS:?请在 .env 配置 DB_PASS}"
: "${SECRET_KEY:?请在 .env 配置 SECRET_KEY}"
: "${XGSZ_VERSION:=latest}"
: "${HTTP_PORT:=80}"
: "${HTTPS_PORT:=443}"
: "${ADMIN_USERNAME:=admin}"
: "${ADMIN_PASSWORD:=admin123456}"

if [[ "$DB_PASS" == change-me-* || ${#DB_PASS} -lt 8 ]]; then
  die "请把 .env 中 DB_PASS 改成至少 8 位的强密码（不要用 change-me-*）"
fi
if [[ "$SECRET_KEY" == change-me-* || ${#SECRET_KEY} -lt 20 ]]; then
  die "请把 .env 中 SECRET_KEY 改成至少 20 位的随机值（不要用 change-me-*）"
fi

# ---------- 0. 自动把本机 IP 加入 ALLOWED_HOSTS ----------
# 用 IP 访问时，ALLOWED_HOSTS 缺了该 IP 会返回 400 + HTML（前端表现为 JSON 解析错误）
HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
if [[ -n "$HOST_IP" && "${ALLOWED_HOSTS:-*}" != "*" ]]; then
  case ",${ALLOWED_HOSTS}," in
    *",${HOST_IP},"*) ;;
    *)
      ALLOWED_HOSTS="${ALLOWED_HOSTS},${HOST_IP}"
      export ALLOWED_HOSTS
      if grep -q '^ALLOWED_HOSTS=' .env; then
        sed -i "s|^ALLOWED_HOSTS=.*|ALLOWED_HOSTS=${ALLOWED_HOSTS}|" .env
      else
        echo "ALLOWED_HOSTS=${ALLOWED_HOSTS}" >> .env
      fi
      log "ALLOWED_HOSTS 已补充本机 IP：${HOST_IP}"
      ;;
  esac
fi

log "部署版本：${XGSZ_VERSION}，域名：${DOMAIN}，端口：${HTTP_PORT}/${HTTPS_PORT}"

# ---------- 1. 导入镜像 ----------
IMG_TAR="images/xgsz-admin-images-${XGSZ_VERSION}.tar"
IMG_GZ="${IMG_TAR}.gz"
if docker image inspect "xgsz/admin-backend:${XGSZ_VERSION}" >/dev/null 2>&1; then
  log "镜像已存在，跳过导入"
elif [[ -f "$IMG_TAR" ]]; then
  log "导入镜像：$IMG_TAR（约 1~2 分钟）"
  docker load -i "$IMG_TAR"
elif [[ -f "$IMG_GZ" ]]; then
  log "导入镜像：$IMG_GZ（约 1~2 分钟）"
  gzip -dc "$IMG_GZ" | docker load
else
  die "未找到镜像包 images/xgsz-admin-images-${XGSZ_VERSION}.tar，且本机也没有该镜像"
fi

# ---------- 2. 证书 ----------
CERT_DIR="nginx/certs/live/${DOMAIN}"
mkdir -p nginx/certs nginx/www
if [[ ! -f "${CERT_DIR}/fullchain.pem" || ! -f "${CERT_DIR}/privkey.pem" ]]; then
  if [[ "${SELF_SIGNED:-0}" == "1" ]]; then
    log "生成自签证书：${DOMAIN}"
    mkdir -p "$CERT_DIR"
    # 域名是纯 IP 时用 IP: 而不是 DNS:，并把本机 IP 一起写进 SAN，避免浏览器报证书名称不匹配
    if [[ "$DOMAIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      SAN="IP:${DOMAIN},IP:127.0.0.1"
    else
      SAN="DNS:${DOMAIN},DNS:localhost,IP:127.0.0.1"
    fi
    [[ -n "${HOST_IP:-}" ]] && SAN="${SAN},IP:${HOST_IP}"
    openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
      -keyout "${CERT_DIR}/privkey.pem" \
      -out "${CERT_DIR}/fullchain.pem" \
      -subj "/CN=${DOMAIN}" \
      -addext "subjectAltName=${SAN}" >/dev/null 2>&1
    cp "${CERT_DIR}/fullchain.pem" "${CERT_DIR}/cert.pem"
    log "自签证书 SAN：${SAN}"
    log "浏览器提示不受信属正常；如需彻底消除，把 ${CERT_DIR}/fullchain.pem 导入客户端受信任根证书"
  else
    [[ -n "${EMAIL:-}" ]] || die "申请 Let's Encrypt 证书需要 EMAIL（或设置 SELF_SIGNED=1）"
    log "使用 certbot standalone 申请证书（需要 80 端口空闲）"
    docker run --rm -p 80:80 \
      -v "$ROOT/nginx/certs:/etc/letsencrypt" \
      -v "$ROOT/nginx/www:/var/www/certbot" \
      certbot/certbot certonly --standalone \
      -d "$DOMAIN" --email "$EMAIL" --agree-tos --no-eff-email
  fi
else
  log "证书已存在，跳过申请"
fi

# ---------- 3. 启动 ----------
log "启动服务"
"${COMPOSE[@]}" up -d

log "等待 backend 就绪"
READY=0
for i in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T backend python manage.py check >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done
[[ "$READY" == "1" ]] || die "backend 未在 120 秒内就绪，请查看：${COMPOSE[*]} logs -f backend"

log "执行数据库迁移"
"${COMPOSE[@]}" exec -T backend python manage.py migrate --noinput

if [[ "${SEED_DEMO:-0}" == "1" ]]; then
  log "导入演示数据"
  "${COMPOSE[@]}" exec -T backend python manage.py seed_demo || true
fi

log "确保管理员账号"
if [[ "${ADMIN_RESET:-0}" == "1" ]]; then
  "${COMPOSE[@]}" exec -T backend python manage.py ensure_admin \
    --username "$ADMIN_USERNAME" --password "$ADMIN_PASSWORD" --reset-password
else
  "${COMPOSE[@]}" exec -T backend python manage.py ensure_admin \
    --username "$ADMIN_USERNAME" --password "$ADMIN_PASSWORD"
fi

log "服务状态"
"${COMPOSE[@]}" ps

if [[ "$HTTPS_PORT" == "443" ]]; then
  URL="https://${DOMAIN}"
else
  URL="https://${DOMAIN}:${HTTPS_PORT}"
fi
echo ""
echo "============================================================"
echo " 部署完成：${URL}"
echo " 账号：${ADMIN_USERNAME} / ${ADMIN_PASSWORD}（请登录后立即修改）"
echo " 数据卷：xgsz-mysql-data / xgsz-redis-data / xgsz-mongo-data"
echo " 证书续期：${COMPOSE[*]} --profile certbot up -d certbot"
echo "============================================================"
