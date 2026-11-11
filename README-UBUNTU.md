# 芯光数智 · Ubuntu 服务器部署包

> 适用：Ubuntu 20.04 / 22.04 / 24.04（x86_64）
> 形式：Docker + Docker Compose，预构建镜像，解压即部署。

## 一、部署包内容

```text
xgsz-admin-ubuntu-<版本>/
├── docker-compose.ubuntu.yml     # 生产编排（不依赖本机编译）
├── .env.ubuntu.example           # 环境变量模板
├── scripts/
│   ├── deploy_ubuntu.sh          # 一键部署
│   └── init_https.sh             # 证书申请辅助（可选）
├── xgsz-admin-web/               # 前端静态文件（nginx 直接托管）
├── nginx/prod/templates/         # 域名 + HTTPS 的 nginx 配置模板
├── nginx/certs/                  # 证书目录（运行时生成）
├── nginx/www/                    # ACME 校验目录
├── kube/clusters/                # 多集群 kubeconfig（可选）
├── data/demo_data.json           # 演示数据
├── xgsz-admin/                   # 后端源码（排障/二次构建用）
├── docs/                         # 项目文档
└── images/
    └── xgsz-admin-images-<版本>.tar   # 预构建 Docker 镜像
```

## 二、前置条件

| 项 | 要求 |
|---|---|
| 系统 | Ubuntu 20.04+，x86_64 |
| 配置 | 建议 4C8G，磁盘 40G+ |
| Docker | Docker Engine 24+ |
| Compose | Docker Compose v2（`docker compose version`） |
| 网络 | 安全组/防火墙放行 80、443（SSH 另开） |
| 域名 | 已解析 A 记录到服务器公网 IP；内网可用 IP/hosts |
| 可选 | 8 台 K8s 集群的 kubeconfig（放到 `kube/clusters/`） |

安装 Docker（Ubuntu）：

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo systemctl enable --now docker
sudo usermod -aG docker $USER   # 重新登录生效
docker compose version
```

## 三、一键部署

```bash
# 1. 解压
tar -xzf xgsz-admin-ubuntu-<版本>.tar.gz
cd xgsz-admin-ubuntu-<版本>

# 2. 配置
cp .env.ubuntu.example .env
vi .env
#   必须修改：DOMAIN、DB_PASS、SECRET_KEY
#   首次演示可保留 SEED_DEMO=1
#   脚本会拒绝 change-me-* 和过短的 DB_PASS / SECRET_KEY

# 3. 部署（需要 root 或 docker 组权限）
sudo bash scripts/deploy_ubuntu.sh
```

脚本会：

1. 从 `images/` 导入预构建镜像；
2. 检查/申请 HTTPS 证书（Let's Encrypt 或自签）；
3. 启动 MySQL / Redis / MongoDB / backend / celery / nginx；
4. 等待 backend 就绪，执行数据库迁移；
5. 可选导入演示数据；
6. 创建管理员账号（默认 `admin / admin123456`）。

完成后访问：

```text
https://你的域名
```

首次登录后请立即修改管理员密码。

## 四、证书方式

### 方式 A：Let's Encrypt（推荐，公网域名）

在 `.env` 中设置：

```env
DOMAIN=ops.example.com
EMAIL=ops@example.com
SELF_SIGNED=0
```

首次申请需要 **80 端口空闲**（脚本会短暂用 certbot standalone）。

### 方式 B：自签证书（内网/测试）

```env
DOMAIN=local.test
SELF_SIGNED=1
```

脚本生成的证书 SAN 会自动包含：`DOMAIN`、`localhost`、`127.0.0.1`、**本机首个内网 IP**。
所以用 `https://IP` 或 `https://DOMAIN` 访问都不会报"证书名称不匹配"，但仍会提示"不受信任"（自签的必然结果）。

- 浏览器点"高级 → 继续前往"即可；
- Chrome/Edge 还可以在报错页直接输入 `thisisunsafe` 跳过；
- 要彻底消除提示：把 `nginx/certs/live/<DOMAIN>/fullchain.pem` 导入客户端"受信任的根证书颁发机构"。

### 方式 C：已有商业证书

把证书放到：

```text
nginx/certs/live/<DOMAIN>/fullchain.pem
nginx/certs/live/<DOMAIN>/privkey.pem
```

然后重新执行 `sudo bash scripts/deploy_ubuntu.sh`。

### 证书续期

```bash
docker compose -f docker-compose.ubuntu.yml --profile certbot up -d certbot
# 续期后 reload nginx
docker compose -f docker-compose.ubuntu.yml exec nginx nginx -s reload
```

## 五、验证部署

```bash
# 容器状态
docker compose -f docker-compose.ubuntu.yml ps

# 后端日志
docker compose -f docker-compose.ubuntu.yml logs -f backend

# HTTP 应 301 到 HTTPS
curl -I http://你的域名
curl -I https://你的域名

# 登录接口
curl -k -X POST https://你的域名/api/account/v1/user/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123456"}'
```

## 六、常用运维命令

```bash
# 查看状态
docker compose -f docker-compose.ubuntu.yml ps

# 重启后端
docker compose -f docker-compose.ubuntu.yml restart backend

# 查看日志
docker compose -f docker-compose.ubuntu.yml logs -f backend
docker compose -f docker-compose.ubuntu.yml logs -f nginx

# 执行迁移（升级后）
docker compose -f docker-compose.ubuntu.yml exec backend python manage.py migrate

# 导入演示数据
docker compose -f docker-compose.ubuntu.yml exec backend python manage.py seed_demo

# 创建/修正管理员
docker compose -f docker-compose.ubuntu.yml exec backend python manage.py ensure_admin \
  --username admin --password 新密码 --reset-password

# 停止（保留数据）
docker compose -f docker-compose.ubuntu.yml down

# 停止并删除数据（谨慎）
docker compose -f docker-compose.ubuntu.yml down -v
```

## 七、数据备份

数据在 Docker 卷里：

```bash
# 备份 MySQL
docker run --rm -v xgsz_xgsz-mysql-data:/var/lib/mysql -v "$PWD:/backup" alpine \
  tar czf /backup/mysql-$(date +%F).tar.gz -C /var/lib/mysql .

# 备份 Mongo
docker run --rm -v xgsz_xgsz-mongo-data:/data/db -v "$PWD:/backup" alpine \
  tar czf /backup/mongo-$(date +%F).tar.gz -C /data/db .
```

> 卷名前缀与 `docker-compose.ubuntu.yml` 的 `name: xgsz` 对应，实际名称可用 `docker volume ls` 查看。

## 八、升级

1. 备份数据库卷；
2. 解压新版本交付包；
3. 替换 `images/` 中的镜像 tar；
4. 修改 `.env` 中 `XGSZ_VERSION` 为新版本；
5. `sudo bash scripts/deploy_ubuntu.sh`；
6. 脚本会自动执行迁移。

## 九、接入 8 台 K8s 集群

把每台集群的 kubeconfig 放到：

```text
kube/clusters/cluster-01.yaml
kube/clusters/cluster-02.yaml
...
kube/clusters/cluster-08.yaml
```

然后：

```bash
docker compose -f docker-compose.ubuntu.yml restart backend celery-worker celery-beat
```

平台「环境管理 → K8s 集群接入状态」会自动显示在线状态；发布单里填写同名「目标集群」即可。
详细步骤见 `docs/08-多集群接入清单.md`。

## 十、常见问题

| 现象 | 排查 |
|---|---|
| `permission denied /var/run/docker.sock` | 用 `sudo` 或把用户加入 docker 组后重新登录 |
| 80/443 被占用 | `ss -lntp \| grep -E ':80\|:443'`，停掉占用进程或改 `HTTP_PORT/HTTPS_PORT` |
| 502 Bad Gateway | `docker compose ... logs -f backend`，确认 backend 已启动、DB 已就绪 |
| 证书申请失败 | 80 端口被占用 / DNS 未生效 / 域名未备案；先用 `SELF_SIGNED=1` 验证链路 |
| MySQL 启动慢 | 首次初始化 20~60 秒，`docker compose ... logs -f mysql` 查看 |
| 页面能开但接口 500 | 检查 `.env` 的 `DB_PASS` 与容器实际密码是否一致；首次改密码需删卷重来 |
| 浏览器证书不受信 | 自签证书需手动信任；正式环境确认使用 Let's Encrypt 正式证书 |
| 重启/重建 backend 后全站接口 502（静态页正常） | 旧版 nginx 把 `backend` 解析成固定 IP。本版已改为 `resolver 127.0.0.11` + 变量式 `proxy_pass`，可自动重解析；旧版临时处理：`docker compose -f docker-compose.ubuntu.yml restart nginx` |
| 用 IP 访问登录报 400，前端显示 `Unexpected token '<'` | `ALLOWED_HOSTS` 缺该 IP。部署脚本会自动补本机 IP；手工补：`sed -i 's/^ALLOWED_HOSTS=.*/ALLOWED_HOSTS=域名,IP,localhost,127.0.0.1/' .env` 后 `up -d backend` + `restart nginx` |
| 前端提示"服务暂时不可用（HTTP 5xx）" | 这是前端统一的非 JSON 响应兜底提示，说明后端/网关异常，查 `logs backend` 与 `logs nginx` |

## 十一、安全清单

- [ ] 修改 `DB_PASS` 为强密码
- [ ] 修改 `SECRET_KEY` 为随机值
- [ ] 修改 admin 默认密码
- [ ] `ALLOWED_HOSTS` 改为域名白名单（不要长期用 `*`）
- [ ] 防火墙仅放行 22 / 80 / 443
- [ ] 不把 `.env`、`kube/`、`nginx/certs/` 提交到 Git
- [ ] 定期备份 MySQL/Mongo 数据卷
- [ ] 生产环境建议在 nginx 前再加云 WAF / SLB
