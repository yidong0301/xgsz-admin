# xgsz-admin 运行说明（最终版）

## 一、访问入口

| 入口 | 地址 | 说明 |
|---|---|---|
| 平台前端 | http://localhost:8080 | 登录页（标题 xgsz-admin） |
| 统计大屏 | http://localhost:8080/dashboard.html | 资产清单 + 多维统计 + 负责人 |
| 后端 API | http://localhost:8000 | Django REST API（daphne/ASGI） |
| Django admin | http://localhost:8080/admin/ | 管理后台 |

- 登录账号：`admin` / `admin123456`（用户名/邮箱/手机号均可）

## 二、运行组件（全部在线）

| 组件 | 容器/进程 | 端口 | 作用 |
|---|---|---|---|
| nginx | xgsz-nginx | 8080 | 前端托管 + 反代 /api /admin /ws |
| daphne（ASGI） | 后台进程 | 8000 | HTTP + WebSocket（SSH/日志） |
| Celery worker | 后台进程 | - | 异步任务执行 |
| Celery beat | 后台进程 | - | 定时任务调度 |
| MySQL 5.7 | xgsz-mysql | 3307 | 主数据库 |
| Redis 6 | xgsz-redis | 6379 | 缓存/队列/WebSocket 通道 |
| MongoDB 4.4 | xgsz-mongo | 27017 | 部分数据（ansible 日志等） |

## 三、完成的工作

1. **全量改名**：`devops_api` → `xgsz_admin`（包名/Celery 队列/DB 名 xgsz_admin + 显示名 xgsz-admin + 新 Logo/favicon）
2. **CMDB/资产管理**：新增 `owner`（负责人）、`environment`（环境）字段；搜索支持负责人/环境
3. **多维统计**：`/api/cmdb/v1/dashboard/count` 按云类型/状态/地域/负责人/环境分组计数
4. **统计大屏**：`dashboard.html` 浏览器直出资产清单 + 统计图表
5. **任务编排**：Celery worker + beat，8 个任务注册，全链路（派发→接收→执行→重试）验证通过
6. **WebSocket**：daphne 切换，路由/鉴权/消费者分发验证通过
7. **K8s 推理任务**：`InferenceTask` 模型 + 提交 API（映射 K8s Job，含 GPU 资源 + 优雅降级）
8. **逐条修复的报错**（共 12 项）：pip 元数据、ansible 符号链接/fcntl/正则、MySQL 字符集、登录 bug、权限、celery `.delay` 挂起、asgi 初始化顺序等

## 四、关键 API

| 接口 | 方法 | 说明 |
|---|---|---|
| /api/account/v1/user/login | POST | 登录（返回 JWT） |
| /api/cmdb/v1/server | GET | 资产列表（含 owner/environment） |
| /api/cmdb/v1/dashboard/count | GET | 多维统计 |
| /api/k8s/v1/inference/task | GET/POST | 推理任务列表/提交（K8s Job） |
| /api/k8s/v1/inference/task/{id} | GET | 推理任务详情 |

鉴权头：`Authorization: JWT <token>`

## 五、Windows 兼容性说明

- **ansible**（远程自动化）是 Unix-only，已打补丁让平台启动；实际执行需 Linux 控制机
- 已创建 `fcntl/pwd/grp/termios/tty/resource/crypt/spwd` 等 Windows 存根
- **K8s 推理任务**：代码已实现，但本地无 K8s 集群（`~/.kube/config` 指向不可达的 127.0.0.1:6443），端到端执行需接入真实集群（修改 kubeconfig 即可）

## 六、启动命令（Windows / PowerShell）

```powershell
# 1. 依赖 + 容器（已完成，如需重建）
# docker 启动 MySQL/Redis/MongoDB

# 2. 后端（daphne，ASGI，含 WebSocket）
cd D:\WDXMGZ\xgsz-admin
& D:\WDXMGZ\venv\Scripts\python.exe -m daphne xgsz_admin.asgi:application -b 0.0.0.0 -p 8000

# 3. Celery worker + beat
& D:\WDXMGZ\venv\Scripts\python.exe -m celery -A xgsz_admin worker --pool=solo -l INFO
& D:\WDXMGZ\venv\Scripts\python.exe -m celery -A xgsz_admin beat -l info

# 4. 前端（nginx 容器已托管）
# docker run -d --name xgsz-nginx -p 8080:80 -v D:\WDXMGZ\xgsz-admin-web:/usr/share/nginx/html:ro -v D:\WDXMGZ\nginx\nginx.conf:/etc/nginx/conf.d/default.conf:ro --add-host=host.docker.internal:host-gateway nginx:alpine
```

## 七、剩余事项

1. **K8s 集群接入**：提供一个真实集群的 kubeconfig（或启用 Docker Desktop Kubernetes / 部署 kind），即可端到端跑推理任务
2. **前端 Vue 源码**：当前前端是编译产物，新增字段（owner/environment/推理任务）体现在 API + 统计大屏页，完整接入主界面需 Vue 源码
