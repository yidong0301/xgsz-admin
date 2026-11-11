# 芯光数智 智能运维平台 · 开发指引（CLAUDE.md）

> 本文件是 AI/开发者的工作入口。每次开始工作先读本文件，按标准文档执行。

## 一、项目简介

「芯光数智」算力运维与 AI 推理调度平台。PC 主平台 `xgsz-admin`（Django + DRF + Celery + Channels），前端单文件 `app.html`，另有微信小程序 `xgsz-miniprogram`。Docker Compose 部署。

## 二、标准文档路径（必读）

| 文档 | 路径 | 用途 |
|---|---|---|
| 需求说明 | `docs/01-需求说明.md` | 本次 Demo 范围、验收标准 |
| 技术架构 | `docs/02-技术架构.md` | 技术栈、目录结构、命令 |
| 设计规范 | `docs/03-设计规范.md` | 视觉、交互、文案、术语 |
| 实施计划 | `docs/04-实施计划.md` | 阶段划分、验收方式 |
| 演示脚本 | `docs/05-演示脚本.md` | 现场演示 6 步 |
| 交付说明 | `docs/06-导出交付说明.md` | 一键导出交付包 |
| 域名/HTTPS | `docs/07-域名与HTTPS部署.md` | 生产域名、证书、替换 cpolar |
| 多集群接入 | `docs/08-多集群接入清单.md` | 8 台真实 K8s 集群接入 |
| Ubuntu 部署 | `docs/09-Ubuntu-Docker部署.md` | 镜像打包 + Ubuntu + Docker Compose |
| 后续规划 | `docs/10-后续规划.md` | P3 路线：安全止血、K8s 任务、节点管理、CI/CD |
| 真实集群接入 | `docs/11-真实集群与服务器接入手册.md` | 上线操作：kubeconfig/权限/镜像仓/自检清单/故障速查 |
| 真实推理任务 | `docs/12-真实推理任务.md` | 真实可跑的推理：镜像/一键提交/实测结果/假数据清理 |
| 开发日志 | `devlog/YYYY-MM-DD.md` | 每日开发记录 |
| 上线部署 | `上线部署文档.md` | 外网部署步骤 |

## 三、工作规范（重要）

1. **先读文档**：每次开始前先看 `docs/` 对应文档，明确本次任务范围。
2. **小步推进**：一次只做一个阶段/一个功能点，不要一口气做太多。
3. **每阶段验收**：完成一个阶段后，明确告诉用户「请验证」，等用户确认再继续。
4. **改完记日志**：每次改动后更新 `devlog/当日日期.md`（做了什么、待办、问题）。
5. **不擅自扩大范围**：需求说明里写"不做"的，不要做。
6. **保持稳定**：改前后跑回归清单（见 `docs/04-实施计划.md`）。

## 四、常用命令

```bash
# 一键启动（双击 启动平台.bat）
docker compose up -d

# 停止
docker compose stop

# 改后端代码后重建
docker compose build backend && docker compose up -d

# 建表迁移
docker exec wdxmgz-backend-1 python manage.py migrate

# 跑发布单自动化测试
docker exec wdxmgz-backend-1 python manage.py test apps.ops.tests

# 查看容器
docker ps --format "{{.Names}} | {{.Status}}"
```

## 五、访问与账号

- 本机：`http://localhost:8080`
- 局域网：`http://<本机内网IP>:8080`
- 账号：`admin / admin123456`

## 六、当前阶段

- P2-1 发布单真实滚动更新：已完成（镜像对比 / 健康检查 / 真实回滚）
- P2-2 发布单详情页：已完成（K8s 状态 / Pod / 日志）
- P2-3 域名 + HTTPS：配置与脚本已就绪，待真实域名/服务器验证
- P2-4 8 台真实 K8s 集群：多 kubeconfig + 集群接入状态页已完成，待硬件到货
- P2-5 自动化测试：发布单/重试/回滚重发/集群健康 24 个用例已通过，持续补充
- 品牌 Logo：已更新为新版蓝青渐变图标（顶栏 / 登录页 / PWA / favicon）
- Ubuntu Docker 部署：预构建镜像 + 一键部署脚本 + 离线交付包（docs/09）
  - 产物：`dist/xgsz-admin-ubuntu-20261110_1330.tar.gz`（570MB）
- P3-0 安全止血第一批：已完成并部署 VM（删明文口令页/下线未鉴权诊断/修 3 个必崩/权限/审计/分页待补）
  - VM：`root@192.168.5.129`，镜像 `xgsz/admin-backend:20261111_p30`，备份 `/opt/backup-20261111-1000`
- P3-1 真实 K8s 任务闭环第一批：已完成并部署 VM（SERVICE=Deployment+NodePort / BATCH=Job、15s 状态同步、事件、重跑、前端选集群）
  - VM 镜像 `xgsz/admin-backend:20261111_p31`；迁移 `k8s.0004` 已应用
- P3-2 节点/机器管理第一批：已完成并部署 VM（节点列表/详情、cordon/uncordon、drain 预检、审计、机器节点页）
  - VM 镜像 `xgsz/admin-backend:20261111_p33`
- P3-2 节点/机器管理第二批：已完成并部署 VM（drain=Eviction API+PDB 预检、标签/污点编辑、metrics 降级提示+用量列、节点↔CMDB 资产匹配与一键登记；43 用例全绿）
  - VM 镜像 `xgsz/admin-backend:20261111_p34`，`.env.p34.bak` 可回滚
  - 演示用 PDB：`xgsz-dev/xgsz-demo-pdb`（minAvailable=2，会让 drain 被拒；不需要时 `kubectl delete pdb xgsz-demo-pdb -n xgsz-dev`）
- P3-3 CMDB 深化第一批：已完成并部署 VM（`AssetRelation` + `cmdb.0004`、关系增删查、BFS 拓扑 depth 1–3、前端「配置关系」SVG 拓扑页；55 用例全绿）
  - VM 镜像 `xgsz/admin-backend:20261111_p35`，`.env.p35.bak` 可回滚
  - 演示关系 5 条：生产集群/GPU 节点 → gpu-dev-01、gpu-dev-01 → 核心交换机、核心交换机 → 光模块、生产集群 → web-prod-01
  - 待办：生命周期字段、CSV 导入、拓扑补「命名空间/应用」类型
- P3-3 CMDB 深化第二批：已完成并部署 VM（`AssetChangeRequest` + `cmdb.0005`；提交→审批→执行/驳回/撤销，执行逐字段落库并写 AssetChangeLog；资产管理「变更申请」面板；67 用例全绿）
  - VM 镜像 `xgsz/admin-backend:20261111_p36`，`.env.p36.bak` 可回滚
- UI 对齐 + 分页 + 中文化（2026-11-11）：列表改紧凑企业后台风格（`.lt`/`.tag`/`.pager`）；推理任务/发布单/审计/运维日志接服务端分页；节点详情中文化（中文摘要、条件/Pod 状态/事件中文简述 + 原文）；推理任务日志加中文简述（原始日志保留）
  - VM 镜像 `xgsz/admin-backend:20261111_p37`（推理列表新增 `status` 筛选），`.env.p37.bak` 可回滚
  - 已知遗留：`account.History.created_at`、`rbac.Permission.name` 迁移漂移（历史问题）
- 功能定位对齐 + 环境管理真实配置（2026-11-11）：各页面加职责说明；推理任务改为「已部署模型状态」（状态统计 + 表单收起）；**环境管理改真实配置**（`EnvConfig` + `ops.0008`，下发写入 K8s ConfigMap 并只重启引用它的 Deployment）；发布单新增「重启」动作（rollout restart）
  - VM 镜像 `xgsz/admin-backend:20261111_p38`，`.env.p38.bak` 可回滚
  - 验证用演示应用：`xgsz-dev/xgsz-config-demo`（envFrom `xgsz-env-config`，启动打印环境变量）
  - 仍未对齐：任务编排仍是 backend shell（P3-5 改 K8s Job）、告警页缺独立指标面板
- 发布单详情闪动修复（2026-11-11）：详情轮询改为「内容不变不重绘 + 保留滚动与日志 + 最多 20 次轮询后自动停」；`restart` 改为等待滚动完成后再写 `HEALTHY/UNHEALTHY`（不再永久 DEPLOYING）
  - VM 镜像 `xgsz/admin-backend:20261111_p39`，`.env.p39.bak` 可回滚
- P3-5 任务编排第一批（真实调度，2026-11-11）：模板增加执行目标（cluster/namespace/image/cpu/memory/gpu），`target_type=k8s` 时**每步创建一个 K8s Job**，按 CPU/内存/GPU 分配、超时、TTL 保留日志，镜像拉取失败快速失败；`workflow.0002` 迁移
  - VM 镜像 `xgsz/admin-backend:20261111_p41`，`.env.p41.bak` 可回滚（84 用例全绿）
  - 默认镜像改为 `nginx:alpine`（kind 无外网，busybox 拉不到）
  - 仍缺：定时 cron、并行/DAG、nodeSelector、执行取消
- UI 风格对齐参考图（2026-11-11 下午）：全局字体/配色改企业后台风格（#F5F6F8 底 + 白卡片 + #1677FF）；人员管理去掉「通知组管理」、角色列纯文字无下拉/边框、去掉用户 ID 灰色后缀、按角色权限+创建先后排序；角色划分 Tab 重做
  - 截图：`docs/images/ui-personnel-20261111.png`、`ui-role-20261111.png`、`ui-dashboard-20261111.png`
  - 前端静态文件改动，nginx 直接生效；Ubuntu 部署包需在上线前重新打包
- 侧边栏精简（2026-11-11 下午）：日常操作只保留「推理任务 / 告警与自检 / 审计日志」；「任务编排 / 发布单 / 环境管理 / 运维日志 / 配置关系」移入底部「高级功能」折叠组（默认收起、记忆状态、进入页面自动展开）；工作台常用功能移除任务编排/运维日志快捷卡
  - 截图：`docs/images/ui-advanced-closed-20261111.png`、`ui-advanced-open-20261111.png`
- 指标面板（告警与自检，2026-11-11）：kind 装上 metrics-server（阿里云镜像 + kind load + `--kubelet-insecure-tls`）；`MetricSample` + 每分钟采样（`ops.0009/0010`）；`GET /api/ops/v1/metrics/overview`（节点 CPU/内存、Pod Top、60 点趋势、阈值告警）；页面加实时指标卡片 + 自适应趋势曲线 + Pod Top，20 秒刷新且内容不变不重绘
  - VM 镜像 `xgsz/admin-backend:20261111_p45`，`.env.p45.bak` 可回滚
  - 修复：K8s CPU 数量可能是纳核（`201838822n`）导致显示 0；Pod 用量在 `containers[].usage`；`tasks.metrics` 需加进 celery include
- 体验修复（2026-11-11 下午）：后端镜像重建（旧容器缺 topology/metrics/events 路由 → 3 处 404 全消，`docker compose build backend` + 迁移补齐）；kind 重装 metrics-server（`k8s/metrics-server.yaml`，阿里云镜像导入节点 + `--kubelet-insecure-tls`）；任务编排 4 张 KPI 卡加色（蓝/紫/绿/橙）+ 任务模板「查看/触发」加 14px 间距；实时日志改黑底白字、3s 真增量刷新（内容不变不重绘、在底部自动跟随、标题显示「有更新/无新日志 + 时间 + 行数」）+ 事件面板修好 404；补 5 条演示配置关系
  - 截图：`docs/images/ui-wf-stats-color-20261111.png`、`ui-task-log-live-20261111.png`、`ui-metrics-real-20261111.png`、`ui-topology-20261111.png`
  - 全平台字号 rem 化 + 顶栏 Aa 调节（默认 115%）：见 `docs/images/ui-fontscale-*.png`
- 拓扑树形化 + 日志终端风格（2026-11-11 下午）：`relLayout` 改组织架构图式树形（根在上、正交折线、方向朝上的关系走虚线）；新增 `.term-log/.term-bar` 终端风格（黑底白字等宽 + 红/黄/绿按级别着色），用于运维日志详情/任务编排执行日志/发布单 Pod 日志；日志统一可导出 `.log`（集群接入诊断、节点事件、发布单 Pod 日志、推理任务实时日志、任务编排执行日志、运维日志详情）
  - 截图：`docs/images/ui-topology-tree-20261111.png`、`ui-opslog-term-20261111.png`、`ui-wf-log-term-20261111.png`、`ui-cluster-export-20261111.png`、`ui-tasklog-export-20261111.png`
  - 实时日志面板按反馈改为浅色（与「事件」面板一致、深色字）：`docs/images/ui-tasklog-light-20261111.png`
- 通知中心未读/已读（2026-11-11 下午）：铃铛面板「未读红点 / 已读绿点 + 全部已读」，红点改按未读数显示（0 条或全部已读不亮）；`NotificationRead` + `ops.0011`、`POST /api/account/v1/alerts/read`（按用户、幂等）；修复 `sw.js` 缓存 `/api/*` 导致已读状态不刷新（缓存版本 v4）
  - 截图：`docs/images/ui-notif-read-20261111.png`、`ui-notif-mixed-20261111.png`、`ui-notif-allread-20261111.png`
  - 日志面板再调：黑底终端改为「柔和终端」（浅灰底 + 低饱和淡绿/淡红/淡黄着色、透明标题行），四个日志面板统一、夜间同步：`docs/images/ui-log-soft-20261111.png`
  - 拓扑改横向树形（图2配色，含夜间调色板）+ 整体换浅蓝白主题（图3：浅蓝渐变底、白卡片 16px 圆角、蓝系主色、图标统一淡蓝）：`docs/images/ui-topology-horizontal-20261111.png`、`ui-theme-blue-dashboard-20261111.png`
  - 拓扑终版：思维导图式横向（根为蓝色胶囊、一级分支各一色、圆点+文字、贝塞尔曲线无箭头，夜间自动换亮色）；`/api/` 加 `Cache-Control: no-store` 修旧数据缓存：`docs/images/ui-topology-mindmap-20261111.png`
  - 关键指标四色区分（蓝/紫/青/红，数字随色）+ 公告通知加「P1 高危」胶囊与实心红错误标签、灰字加深 + Logo 改 `1.3rem` 与字体等高：`docs/images/ui-kpi-notice-20261111.png`
  - 灰字加深（告警时间 `#475569`）+ 公告状态语义色（已失败红/正常绿）；思维导图连线：层距 300、标签按贝塞尔取点并后绘制避免被遮；帮助弹层改「图标+说明+箭头」菜单：`docs/images/ui-notice-contrast-20261111.png`
  - 夜间可读性修复：运维日志行改主题化 class（摘要 `#EAF1FA`、行底深红/深琥珀）、表头/单元格/侧边栏/次要文字整体提亮、指标节点卡改深色卡：`docs/images/ui-dark-opslog-20261111.png`
- 个人设置重构 + 角色权限迁移（2026-11-11 下午）：个人设置只留「基础信息 / 通知偏好 / 安全设置」3 Tab（告警/巡检/审计开关、MFA 开关、本人登录日志），删除角色权限 Tab；侧边栏「人员与组织 → 平台用户」改「系统管理 → 用户管理」，角色改在用户详情由超级管理员下拉分配；左侧简介精简为一句（如「超级管理员，拥有平台全部操作权限」）；`GET /user/profile` 增加 `role/role_label/login_records`（本人最近 5 条登录）
  - 截图：`docs/images/ui-profile-info-20261111.png`、`ui-profile-notify-20261111.png`、`ui-profile-security-20261111.png`、`ui-profile-engineer-20261111.png`、`ui-user-role-20261111.png`
  - 夜间模式二次提亮（深蓝灰）：底 `#1B2434`、卡片 `#242F42`、表头 `#2B3648`、描边 `#36435A`、正文 `#B6C2D4`，banner 与卡片同层：`docs/images/ui-dark-lighter-20261111.png`
- 配置关系拓扑改网络拓扑风格（2026-11-11 下午）：`renderTopology` 重写为网络拓扑图——集群/交换机画蓝色网络条、服务器/GPU/光模块画设备卡片（新增 `relIcon` 5 类图标），连线改正交折线+箭头（实线正向/虚线反向），关系名带描边；夜间切换自动重绘；面板改「网络拓扑图」
  - 截图：`docs/images/ui-topology-network-20261111.png`、`ui-topology-network-cluster-20261111.png`、`ui-topology-network-dark-20261111.png`
  - 说明：参考图的防火墙/专线/网络段/PC/打印机/电话暂无资产类型，现按现有类型映射；1:1 复刻需新增类型与演示数据
  - 上线接入：新增 `docs/11-真实集群与服务器接入手册.md` + `manage.py check_access` 连通性自检（组件/集群/权限/指标/镜像仓，FAIL 退出码 1）
- 拓扑线框统一 + 用户删除/重置密码（2026-11-11 下午）：拓扑所有设备卡片统一 210×58 / 1px 描边，去掉根节点粗边与光晕，2 层图不再横向滚动；用户管理新增「删除」行内操作与详情头部「重置密码 / 删除用户」，删除需输入 DELETE、不能删自己，重置密码走 `POST /user/reset_password`（超管、审计）；登录页「忘记密码？」提示联系管理员重置
  - 截图：`docs/images/ui-topology-network-20261111.png`、`ui-user-manage-actions-20261111.png`、`ui-user-manage-detail-20261111.png`、`ui-user-delete-confirm-20261111.png`、`ui-user-reset-pwd-20261111.png`
- 真实推理任务替换假推理（2026-11-11 下午）：告警中心里 26 条「推理任务失败：图像分类-030 / 风格迁移-028 …」是演示脚本写库的假数据（镜像 `registry.local/*` 不存在、状态写死 FAILED、K8s 里查不到 Job）。现改为真下发真运行：
  - 新增 `k8s/infer-demo/`（Dockerfile + train.py + infer.py）：构建期在真实数据集训练 sklearn MLP（UCI 手写数字 / Fisher Iris），镜像内置模型；BATCH 用 K8s Job 真推理打印逐条预测+准确率，SERVICE 用 Deployment+NodePort 提供 `/healthz /info /predict /metrics`
  - 新增 `scripts/real_inference_demo.py`：走平台 API 提交 3 个真实任务并等就绪、打印真实日志；实测 手写数字 353/360=98.06%、鸢尾花 29/30=96.67%，在线服务 NodePort 真实打分
  - 清理：删 28 条假任务；`data/demo_data.json` 的 `inference_tasks` 置空；`scripts/seed_more.py`、`seed_demo.py`、`adjust_demo.py`、`manage.py seed_demo`、`tools/seed_from_json.py` 不再造推理任务（`adjust_demo.py` 原先还会误删全部任务，已去掉）
  - 文档：`docs/12-真实推理任务.md`
- 拓扑大节点量止损（2026-11-11 下午）：拓扑容器改「按内容自适应、最多 680px + 内部滚动」（原来整页被撑到上万像素）；新增缩放工具条（−/＋/适配/1:1/回到起点 + Ctrl+滚轮以光标为锚点）与「搜索节点定位」（命中高亮并居中）；打开即定位到根节点；关系名标签改贴子节点卡片左侧（不再沿竖直干线堆叠）；后端 `MAX_NODES=150` + `node_truncated` + 截断后过滤悬空边
  - 截图：`docs/images/topo-real-20261111.png`、`topo-big-20261111.png`（合成 60 节点）
  - 待做（第二批）：网格换列、集群节点聚合折叠、按资产类型配色
- 登录页扫码 + 忘记密码（2026-11-11 下午）：账号登录/扫码登录双通道；扫码为本机手机授权（`qr.html` 手机确认、桌面轮询一次票据，Redis 120s，前端 `js/qrcode.js` 本地生成二维码，不依赖钉钉/企业微信）；「忘记密码」改规范弹窗，引导管理员在「用户管理 → 用户详情 → 重置密码」处理；`POST /user/qr/create|status|approve`、nginx 加 `X-Forwarded-Host/Proto`
  - 截图：`docs/images/ui-qr-login-20261111.png`、`ui-qr-login-success-20261111.png`、`ui-qr-phone-form-20261111.png`、`ui-qr-phone-20261111.png`、`ui-forgot-password-20261111.png`、`ui-qr-login-957-20261111.png`、`ui-qr-login-390-20261111.png`
- 告警处置 + 任务改名 + 耗时（2026-11-11 下午）：P2「服务器已停机」是演示数据写死的 `Stopped`，已真落库处置（`old-server-01` → 新增状态 `Retired` 已退役，`cmdb.0006`；node-007/014/021/028 → 巡检确认恢复 Running），每台写审计 + 运维日志；演示 JSON 与 seed 脚本同步，告警中心 5 条 → 0 条
  - 推理任务新增改名 `POST /api/k8s/v1/inference/task/<id>/rename`（只改显示名，K8s 资源名不变，写审计），详情顶部「✎ 改个名字」；三个真实任务已改名为 手写数字识别-批量推理（UCI digits 8×8）/ 鸢尾花分类-批量推理（Fisher Iris）/ 手写数字识别-在线推理服务（NodePort）
  - 任务详情修「命令/参数」：原来所有值被 `.slice(0,19)` 截断，现按真实命令行展示、长值换行
  - 耗时：`InferenceTask.started_at/finished_at`（`k8s.0005`）取 Job `startTime/completionTime`、Deployment 创建时间；序列化 `duration_seconds/duration_text`，列表加「耗时 / 运行」列（已结束「耗时 4 秒」、运行中「运行 16 分 22 秒」），提交表单加时长说明
  - 实测：容器内纯推理 0.15 s（360 张）；任务整体 4 s / 7 s；提交到界面「已成功」5–15 s（15 s 同步周期）；在线服务 10–20 s 就绪
  - 截图：`docs/images/ui-real-infer-tasks-v2-20261111.png`、`ui-real-infer-detail-v2-20261111.png`、`ui-alerts-empty-20261111.png`
  - 部署：后端三镜像已重建；迁移 `cmdb.0006`、`k8s.0005` 已应用；`apps.cmdb + apps.k8s + apps.ops` 87 用例全绿
- 拓扑节点统一浅蓝胶囊（2026-11-11 下午）：按反馈「都改成中间集群一样、明显点但颜色浅一点」——删掉「网络条 / 白卡片」两套画法，所有资产统一 210×42 浅蓝胶囊；集群 / 交换机深一档（`#A6C6F8→#88B0F3`）做网络核心，服务器 / GPU / 光模块浅一档（`#EDF4FF→#D8E7FC`）；文字统一深蓝 `#143F86`（白字在中浅蓝上只有 1.7–2.2:1）；取消按一级分支的 6 色循环，连线统一 `#7FA9E8`；夜间同步为 `#5477AE→#44679E` / `#2D3E58→#354863`
  - 截图：`docs/images/topo-real-20261111.png`、`topo-real-dark-20261111.png`、`topo-big-20261111.png`
  - 备注：想保留白字需把 hub 压到 `#4A7BD0` 左右（达标对比度但不再是浅色）
- 任务卡「已提交」快速判失败（2026-11-11 下午）：用户提交 `registry.k8s.io/kube-proxy:v1.29.2` + 命令留空 → 容器 `CreateContainerError: no command specified`（该镜像无 CMD），平台原先只看 `available_replicas`，要等 600 秒进度超时才失败
  - `apps/k8s/services.py` 新增 `pod_failure_reason()`：同步时读 Pod 状态，≤15 秒判失败并写 `failure_reason`（CreateContainerError 立即；ImagePull/Unschedulable 60 秒宽限；CrashLoopBackOff 重启 ≥2 次）
  - 任务日志接口遇「容器未启动」改为友好提示（原因 + 建议看事件）；告警详情中文化（`no command specified` → 「镜像没有默认启动命令且未填命令」）
  - 提交表单提示：命令留空 = 用镜像 CMD；简单命令用批任务（Job）+ `["sh","-c","echo hi"]`
  - 文档：`docs/12-真实推理任务.md` 第八节；截图 `docs/images/ui-kubeproxy-fail-20261111.png`、`ui-alerts-fail-20261111.png`；`apps.k8s + apps.ops + apps.account` 75 用例全绿
