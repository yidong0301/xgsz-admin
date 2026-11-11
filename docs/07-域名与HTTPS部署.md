# 芯光数智 · 域名 + HTTPS 部署（替换 cpolar 临时隧道）

> 目标：把当前 `cpolar` 临时公网地址，替换为**固定域名 + 可信 HTTPS 证书**。
> 适用：云服务器 / 公司内网服务器（Linux + Docker Compose）。

## 一、前置条件

| 项 | 要求 |
|---|---|
| 域名 | 已备案（国内服务器），DNS 添加 A 记录指向服务器公网 IP |
| 服务器 | 2C4G 以上，已安装 Docker 与 Docker Compose v2 |
| 端口 | 安全组/防火墙放行 80、443 |
| 证书 | Let's Encrypt 免费证书（脚本自动申请），或已有商业证书 |

DNS 验证（在本地执行）：

```bash
nslookup ops.example.com
# 应返回服务器公网 IP
```

## 二、首次部署（Let's Encrypt）

```bash
# 1. 进入项目目录
cd /opt/xgsz-admin

# 2. 配置环境变量（至少改 DOMAIN 与 DB_PASS）
cat > .env <<'EOF'
DOMAIN=ops.example.com
DB_PASS=请换成强密码
HTTP_PORT=80
HTTPS_PORT=443
EOF

# 3. 申请证书并启动生产栈
chmod +x scripts/init_https.sh
./scripts/init_https.sh --domain ops.example.com --email ops@example.com
```

脚本会：

1. 用 `certbot standalone` 在 80 端口完成 HTTP-01 校验，证书写入 `nginx/certs/live/<域名>/`；
2. 启动 `docker-compose.prod.yml`（MySQL / Redis / Mongo / backend / celery / nginx）；
3. nginx 用 `nginx/prod/templates/default.conf.template` 渲染出 HTTP→HTTPS 跳转 + 443 TLS 站点。

验证：

```bash
curl -I http://ops.example.com           # 应返回 301 到 https
curl -I https://ops.example.com          # 应返回 200
docker compose -f docker-compose.prod.yml ps
```

浏览器打开 `https://ops.example.com`，用 `admin / admin123456` 登录后**立即修改密码**。

> 首次调试建议加 `--staging` 使用 Let's Encrypt 测试环境，避免触发正式环境频率限制：
> `./scripts/init_https.sh --domain ops.example.com --email ops@example.com --staging`

## 三、本地 / 内网自签验证（无公网域名时）

```bash
./scripts/init_https.sh --domain local.test --self-signed
# 浏览器访问 https://local.test（需把 local.test 指向服务器，或直接 https://<IP> 并信任自签证书）
```

Windows PowerShell：

```powershell
.\scripts\init_https.ps1 -Domain local.test -SelfSigned
```

自签证书仅用于验证链路，正式对外请使用 Let's Encrypt。

## 四、证书自动续期

Let's Encrypt 证书有效期 90 天。启动 certbot 续期容器：

```bash
docker compose -f docker-compose.prod.yml --profile certbot up -d certbot
```

容器每 12 小时执行一次 `certbot renew`。续期成功后需要让 nginx 重新加载证书：

```bash
# 方案 A：每天定时 reload（推荐）
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload

# 方案 B：crontab 每天 03:30 reload
30 3 * * * cd /opt/xgsz-admin && docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

验证证书到期时间：

```bash
echo | openssl s_client -servername ops.example.com -connect ops.example.com:443 2>/dev/null \
  | openssl x509 -noout -dates
```

## 五、从 cpolar 切换过来

1. 关闭并取消 cpolar 开机自启（`tunnel.bat` / `隧道-启动.bat` 不再使用）；
2. 确认域名解析到服务器；
3. 按第二节部署生产栈；
4. 把对外通知、小程序、演示脚本里的地址统一改为 `https://ops.example.com`；
5. 旧 cpolar 地址保留 1~2 天观察，确认无调用后再释放。

## 六、生产安全清单

- [ ] `.env` 中 `DB_PASS` 改为强密码，且不要提交到 Git（`.gitignore` 已忽略 `.env`）
- [ ] `admin` 默认密码已修改
- [ ] 生产 compose 不暴露 3306 / 6379 / 27017 端口（本文件已移除）
- [ ] 防火墙仅放行 80 / 443 / SSH
- [ ] 定期备份 `prod-mysql-data` 卷
- [ ] 检查 `kube/config` 指向真实 K8s 集群（8 台小集群接入后替换）
- [ ] 开启 HSTS 前确认全站 HTTPS 无混合内容（模板已默认开启，可按需移除）

## 七、常见问题

| 现象 | 排查 |
|---|---|
| 502 Bad Gateway | `docker compose -f docker-compose.prod.yml logs -f backend`，确认 backend 已启动、`/api/` 可访问 |
| 证书申请失败 | 80 端口被占用 / DNS 未生效 / 域名未备案；先 `curl http://<域名>/.well-known/acme-challenge/test` 验证 |
| 浏览器证书不受信 | 自签证书需手动信任；正式环境确认使用 Let's Encrypt 正式证书而非 `--staging` |
| 上传大文件失败 | 模板已设 `client_max_body_size 100m`，如仍失败检查云厂商 WAF/网关限制 |
| 登录后接口 403 | 检查 `X-Forwarded-Proto` 与 CORS 配置，确认请求走的是 `https://` |
