# 芯光数智 · Ubuntu 服务器 + Docker 部署

> 目标：把当前 Windows / Docker Desktop 的开发环境，交付为 **Ubuntu 服务器可直接运行的 Docker 部署包**。
> 交付物：镜像 tar + `docker-compose.ubuntu.yml` + 前端静态文件 + 一键部署脚本。

## 一、整体方案

```text
Windows 开发机
  ├─ docker build 后端镜像
  ├─ docker save 后端 + MySQL + Redis + Mongo + nginx + certbot
  └─ tar.gz 打包（镜像 + compose + 前端 + 脚本 + 文档）
                │
                ▼  scp / U盘 / 对象存储
Ubuntu 服务器
  ├─ docker load 镜像
  ├─ docker compose up -d
  └─ https://<域名>
```

生产栈容器：

| 容器 | 镜像 | 说明 |
|---|---|---|
| mysql | mysql:5.7 | 仅容器网络，不暴露 3306 |
| redis | redis:6-alpine | 缓存 / Celery / Channels |
| mongo | mongo:4.4 | 部分数据 |
| backend | xgsz/admin-backend:<版本> | Daphne + Django ASGI |
| celery-worker | 同上 | 异步任务 |
| celery-beat | 同上 | 定时调度 |
| nginx | nginx:alpine | 80/443、静态文件、反向代理 |
| certbot | certbot/certbot | 可选，证书续期 |

## 二、构建 Ubuntu 部署包（在开发机执行）

前置：Docker Desktop 已启动，能访问 Docker Hub（首次拉取 base image）。

```powershell
# 一键构建 + 导出镜像 + 打包
python tools/build_ubuntu_package.py

# 指定版本
python tools/build_ubuntu_package.py --version 20261110_1330

# 只打文件、不导出镜像（调试用）
python tools/build_ubuntu_package.py --skip-images
```

产物：

```text
dist/xgsz-admin-ubuntu-<版本>.tar.gz
dist/xgsz-admin-ubuntu-<版本>.tar.gz.sha256
```

包内 `images/xgsz-admin-images-<版本>.tar` 包含：

- `xgsz/admin-backend:<版本>`
- `mysql:5.7`
- `redis:6-alpine`
- `mongo:4.4`
- `nginx:alpine`
- `certbot/certbot:latest`

## 三、Ubuntu 服务器部署

```bash
# 1. 上传并解压
scp dist/xgsz-admin-ubuntu-<版本>.tar.gz root@服务器:/opt/
ssh root@服务器
cd /opt
tar -xzf xgsz-admin-ubuntu-<版本>.tar.gz
cd xgsz-admin-ubuntu-<版本>

# 2. 配置
cp .env.ubuntu.example .env
vi .env
#   DOMAIN=ops.example.com
#   DB_PASS=强密码
#   SECRET_KEY=随机值
#   EMAIL=ops@example.com（Let's Encrypt 必填）
#   XGSZ_VERSION=<版本>（包内已自动写入）
#   脚本会拒绝 change-me-* 或过短的 DB_PASS / SECRET_KEY

# 3. 一键部署
sudo bash scripts/deploy_ubuntu.sh
```

脚本自动完成：导入镜像 → 申请证书 → 启动容器 → 等待 backend → 迁移 → 导入演示数据（可选）→ 创建 admin。

访问 `https://<DOMAIN>`，默认账号 `admin / admin123456`，登录后立即修改。

完整说明见交付包内 `README-UBUNTU.md`。

## 四、关键文件

| 文件 | 作用 |
|---|---|
| `docker-compose.ubuntu.yml` | 生产编排，使用预构建镜像，不依赖服务器编译 |
| `.env.ubuntu.example` | 域名 / 密码 / 端口 / 证书模式 / 管理员配置 |
| `scripts/deploy_ubuntu.sh` | 一键部署脚本 |
| `xgsz-admin/apps/account/management/commands/ensure_admin.py` | 幂等创建管理员 |
| `xgsz-admin/apps/account/management/commands/seed_demo.py` | 容器内导入演示数据 |
| `tools/build_ubuntu_package.py` | 构建镜像并打包 |
| `nginx/prod/templates/default.conf.template` | HTTP→HTTPS、HSTS、反代 |

## 五、与开发环境的差异

| 项 | 开发（Windows） | Ubuntu 生产 |
|---|---|---|
| 编排 | `docker-compose.yml` | `docker-compose.ubuntu.yml` |
| 后端 | 本地 build | 预构建镜像 `xgsz/admin-backend:<版本>` |
| 端口 | 8080 | 80 / 443（HTTPS） |
| 数据库端口 | 127.0.0.1:3307/6380/27017 | 不对宿主机暴露 |
| DEBUG | True | False |
| 配置 | `.env` | `.env`（从 `.env.ubuntu.example` 生成） |
| 证书 | 无 / 自签 | Let's Encrypt 或自签 |
| K8s | kind 单集群 | `kube/clusters/` 多集群 |

## 六、验证清单

> 2026-11-10 已在 Ubuntu 22.04 虚拟机（x86_64）上实测：勾选项为 VM 实测通过，未勾选项需要公网域名/真实集群，等真机再做。

- [x] `docker compose -f docker-compose.ubuntu.yml ps` 全部 Up/healthy（7 个容器）
- [x] `curl -I http://域名` 返回 301（VM：`https://ops.local`）
- [x] `curl -I https://域名` 返回 200
- [x] `POST /api/account/v1/user/login` 返回 `errcode=0`
- [x] 页面显示新 Logo、发布单、环境管理、集群接入状态
- [x] 发布单可创建/审批/发布/回滚（VM 内 kind 集群实测，见第九节）
- [x] `docker compose ... exec backend python manage.py check` 无问题
- [x] MySQL/Redis/Mongo 未暴露公网端口
- [ ] 证书续期任务已启用（可选，待真实域名）
- [ ] 真实公网域名 + Let's Encrypt 证书（待服务器/域名，见 `docs/07`）

## 七、升级与回滚

升级：

1. 备份 MySQL/Mongo 数据卷；
2. 上传新版本包，解压；
3. 修改 `.env` 的 `XGSZ_VERSION`；
4. `sudo bash scripts/deploy_ubuntu.sh`（自动迁移）。

回滚：把 `.env` 的 `XGSZ_VERSION` 改回旧版本，重新执行脚本（旧镜像需保留或重新导入旧包）。

## 八、注意事项

1. `xgsz/admin-backend` 镜像为 **linux/amd64**；ARM 服务器（如鲲鹏）需在 ARM 机器上重新构建。
2. 首次 Let's Encrypt 申请需要 80 端口空闲；如 80 被占用，先用 `SELF_SIGNED=1` 验证。
3. `.env`、`kube/`、`nginx/certs/` 含敏感信息，不要提交 Git 或放进公开网盘。
4. `ALLOWED_HOSTS` 生产建议改成 `域名,localhost,127.0.0.1`，不要长期用 `*`。
   - **注意**：如果既用域名又用 IP 访问，必须把 IP 也写进去（如 `ALLOWED_HOSTS=ops.local,192.168.5.129,localhost,127.0.0.1`），漏了会返回 **400 + HTML**，前端表现为 `Unexpected token '<' ... is not valid JSON`，很难定位。
   - 改 `ALLOWED_HOSTS` 是环境变量，必须 `docker compose up -d backend` 重建 backend 才生效；重建后 **紧接着 `restart nginx`**（见第九节 9.5 静态上游缺陷）。
5. 生产环境建议在 nginx 前再加云 SLB/WAF，并限制 SSH 来源 IP。
6. kind 演练会把 **6443 暴露到 0.0.0.0**，仅限内网演练；生产不要对外暴露 K8s API，也不要长期使用 `insecure-skip-tls-verify`。

## 九、虚拟机 / 内网演练（没有公网域名时）

> 适用：交付前在本地 Ubuntu 虚拟机复现生产部署，并验证「发布单 → 真实 K8s」链路。
> 2026-11-10 实测环境：Ubuntu 22.04 虚拟机、x86_64、4C/15G、Docker 镜像通过 daocloud 加速。
> 结论：7 容器 healthy、HTTPS 200、登录 `errcode=0`、发布单创建/审批/发布/回滚全链路通过。

### 9.1 两个前置条件

1. **Docker 镜像加速**（VM 直连 Docker Hub 会超时）：编辑 `/etc/docker/daemon.json`

   ```json
   {"registry-mirrors": ["https://docker.m.daocloud.io", "https://docker.1ms.run", "https://docker.xuanyuan.me"]}
   ```

   `sudo systemctl restart docker`，容器会被短暂重启，`restart: unless-stopped` 会自动拉起。

2. **`ALLOWED_HOSTS` 覆盖所有访问方式**：用 IP 访问就必须把 IP 写进 `.env`，否则 400。

### 9.2 在 VM 里建一个 kind 集群（充当"真实集群"）

```bash
# 1) 装 kubectl + kind
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -m 0755 kubectl /usr/local/bin/kubectl
curl -Lo kind https://kind.sigs.k8s.io/dl/v0.24.0/kind-linux-amd64
sudo install -m 0755 kind /usr/local/bin/kind

# 2) 建集群：必须绑 0.0.0.0，否则 backend 容器连不上 API Server
cat > /tmp/kind-xgsz.yaml <<'EOF'
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
networking:
  apiServerAddress: "0.0.0.0"
  apiServerPort: 6443
EOF

# 3) 镜像源返回的 digest 与 kind 内置 @sha256 不一致时，用本地 tag + --image 绕过
docker pull kindest/node:v1.31.0
docker tag kindest/node:v1.31.0 kindest/node:v1.31.0-local
kind create cluster --name xgsz --config /tmp/kind-xgsz.yaml --image kindest/node:v1.31.0-local
kubectl get nodes   # 期望 xgsz-control-plane Ready v1.31.0

# 4) 导出 kubeconfig 并改成"容器可用"
mkdir -p kube/clusters
kind export kubeconfig --name xgsz --kubeconfig kube/clusters/kind.yaml
python3 - <<'PY'
import re, pathlib
p = pathlib.Path('kube/clusters/kind.yaml')
s = p.read_text()
s = re.sub(r'https://(127\.0\.0\.1|0\.0\.0\.0):', 'https://host.docker.internal:', s)
s = re.sub(r'^(\s*)certificate-authority-data:.*$', r'\1insecure-skip-tls-verify: true', s, flags=re.MULTILINE)
p.write_text(s)
PY

# 5) 业务镜像灌进 kind 节点（节点内 containerd 不走宿主的 registry-mirrors）
docker pull nginx:1.27-alpine
kind load docker-image nginx:alpine nginx:1.27-alpine --name xgsz

# 6) 重启 backend/celery 清掉缓存的 ApiClient，然后验证
docker compose -f docker-compose.ubuntu.yml restart backend celery-worker celery-beat
docker compose -f docker-compose.ubuntu.yml exec backend python manage.py shell -c \
  "from apps.ops import k8s_release as k; print(k.check_cluster('kind'))"
# 期望：reachable=True, node_count=1, version=v1.31.0
```

### 9.3 演练用例与实测结果

| 步骤 | 操作 | 预期 | VM 实测 |
|---|---|---|---|
| 1 | 发布单：`xgsz-demo-web` / 测试 / `xgsz-dev` / `nginx:alpine` / 2 副本 | 命名空间与 Deployment 自动创建 | ✅ 2123ms，`RELEASED/HEALTHY`，2 Pod Running |
| 2 | 再建单换 `nginx:1.27-alpine` → 审批 → 发布 | 镜像对比提示变化、滚动更新、记录 `previous_image` | ✅ 2229ms，滚动中 4 Pod（2 旧 + 2 新） |
| 3 | 第 2 单回滚 | Deployment 镜像回到 `nginx:alpine`，副本恢复 | ✅ `ROLLED_BACK/HEALTHY`，2/2 Ready |
| 4 | 环境管理 → K8s 集群接入状态 | `kind` 在线、1 节点、v1.31.0 | ✅ |

### 9.4 已踩的坑

| 现象 | 根因 | 规避 |
|---|---|---|
| 发布单列表空 | `seed_demo` 只导资产/任务，不生成发布单 | 正常现象，按 9.3 建单 |
| 全站 `/api` 502、静态页正常 | nginx 固定上游 `proxy_pass http://backend:8000;`，backend 重建换 IP 后仍朝旧 IP 转发 | `docker compose ... restart nginx`；根治见 9.5 |
| 登录 400 + HTML | `ALLOWED_HOSTS` 未包含访问用的 IP | 见 9.1 |
| `kind create` 卡在 `Ensuring node image` | 镜像源 digest 与 kind 内置 `@sha256:53df...` 不一致 | 本地 tag + `--image` |
| 前端报 `Unexpected token '<'` | 后端返回 HTML 时前端直接 `r.json()` | 待改（检查 `r.ok` / `Content-Type`） |
| 节点刚建完 `NotReady` | CNI 还在初始化 | 等 30~60 秒，`kubectl wait --for=condition=Ready node/...` |

### 9.5 20261110_1620 已修复的缺陷

| 缺陷 | 修复方式 | 实机复验 |
|---|---|---|
| backend 重建后全站 `/api` 502 | nginx 模板加 `resolver 127.0.0.11 valid=10s ipv6=off;` + `set $xgsz_backend http://backend:8000;`，`/api/`、`/admin/`、`/ws/` 全部改变量式 `proxy_pass`；backend 增加 8000 端口 healthcheck，nginx `depends_on: service_healthy` | backend IP `172.18.0.3 → 172.18.0.9`，**未重启 nginx**，API 连续 3 次 200 |
| 前端把 HTML 当 JSON（`Unexpected token '<'`） | `app.html` 统一包装 `fetch`：`/api/` 响应 `Content-Type` 非 JSON 时抛"服务暂时不可用（HTTP xxx），请稍后重试" | 线上 `app.html` 已包含该逻辑 |
| 用 IP 访问登录 400 | `deploy_ubuntu.sh` 自动把 `hostname -I` 首个 IP 追加进 `ALLOWED_HOSTS` 并写回 `.env` | `.env` 已含 `192.168.5.129`，IP / 域名登录均 200 |
| 自签证书只覆盖 `DOMAIN`，用 IP 访问名称不匹配 | 自签 SAN 自动追加本机 IP；`DOMAIN` 为纯 IP 时用 `IP:` 而非 `DNS:` | 证书 SAN：`DNS:ops.local,DNS:localhost,IP:127.0.0.1,IP:192.168.5.129` |

> 升级后 `docker compose ... ps` 中 backend 显示 `(healthy)`；nginx 会等 backend 健康后才启动（旧的固定上游问题消失）。

### 9.6 遗留问题

- `manage.py migrate` 会提示 `Your models have changes that are not yet reflected in a migration`（`account.History.created_at` 的 `default` 写成了实例而非可调用，模型与迁移不一致）。不影响运行，建议单独补一个迁移修正。
- 真实 8 台 K8s 集群、公网域名 / Let's Encrypt 证书仍待硬件与域名。

