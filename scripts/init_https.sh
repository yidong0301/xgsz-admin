#!/usr/bin/env bash
# 芯光数智 · 域名 + HTTPS 初始化（Linux / macOS / WSL）
# 用法：
#   ./scripts/init_https.sh --domain ops.example.com --email ops@example.com
#   ./scripts/init_https.sh --domain local.test --self-signed
#   ./scripts/init_https.sh --domain ops.example.com --email ops@example.com --staging
set -euo pipefail

DOMAIN=""
EMAIL=""
SELF_SIGNED=0
STAGING=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="${2:-}"; shift 2 ;;
    --email) EMAIL="${2:-}"; shift 2 ;;
    --self-signed) SELF_SIGNED=1; shift ;;
    --staging) STAGING=1; shift ;;
    -h|--help)
      sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "未知参数：$1"; exit 1 ;;
  esac
done

if [[ -z "$DOMAIN" ]]; then
  echo "请指定域名：--domain ops.example.com"; exit 1
fi

if [[ ! -f docker-compose.prod.yml ]]; then
  echo "请在项目根目录执行本脚本（找不到 docker-compose.prod.yml）"; exit 1
fi

mkdir -p nginx/certs nginx/www

if [[ "$SELF_SIGNED" -eq 1 ]]; then
  PYTHON="${PYTHON:-python3}"
  "$PYTHON" tools/gen_self_signed_cert.py --domain "$DOMAIN"
else
  if [[ -z "$EMAIL" ]]; then
    echo "申请 Let's Encrypt 证书需要邮箱：--email ops@example.com"; exit 1
  fi
  STAGING_ARG=""
  if [[ "$STAGING" -eq 1 ]]; then STAGING_ARG="--staging"; fi
  echo ">>> 使用 certbot standalone 申请证书（需要 80 端口空闲）"
  docker run --rm -p 80:80 \
    -v "$PWD/nginx/certs:/etc/letsencrypt" \
    -v "$PWD/nginx/www:/var/www/certbot" \
    certbot/certbot certonly --standalone \
    -d "$DOMAIN" --email "$EMAIL" --agree-tos --no-eff-email $STAGING_ARG
fi

export DOMAIN
export HTTP_PORT="${HTTP_PORT:-80}"
export HTTPS_PORT="${HTTPS_PORT:-443}"
echo ">>> 启动生产栈（域名：$DOMAIN）"
docker compose -f docker-compose.prod.yml up -d

echo ""
echo "完成。访问：https://$DOMAIN"
echo "证书续期：docker compose -f docker-compose.prod.yml --profile certbot up -d certbot"
