# xgsz-admin 平台改造与开发 —— 初步思路与处理流程

## 一、现状盘点

### 1.1 源仓库 devops-api（dnsjia/devops-api）
- 定位：自动化运维平台（**后端部分**）
- 技术栈：
  - 后端：Python Django 3.0 + Django REST framework + Celery(+Beat) + Channels(WebSocket)
  - 前端：Vue 3.0 + Ant Design of Vue（**独立仓库** small-flying-pigs/devops，不在本仓库）
  - 存储：MySQL（主库）、Redis（缓存/任务队列/WebSocket 通道）、MongoDB（部分数据）
  - 自动化/云：Kubernetes client 12.0.1、Ansible 2.8.8、Paramiko(SSH)、阿里云 SDK（ECS/DNS/域名）
- 功能模块（apps/）：
  - account —— 账号
  - cmdb —— 资产管理（服务器、云桌面、SSH）
  - application —— 应用管理（含 Java 应用在线诊断）
  - k8s —— Kubernetes 管理（Node / Deployment / Workload / 弹性伸缩 / 容器日志 / 容器 SSH / YAML 在线编辑）
  - rbac —— 权限
- 支撑目录：consumer（WebSocket 消费，任务日志实时回流）、tasks（Celery 任务）、controller、utils、metrices、exception

### 1.2 新仓库 xgsz-admin（zyongqiang252-debug/xgsz-admin）
- 现状：**devops-api 的 1:1 原样拷贝**（.env / README / apps / devops_api / requirements.txt 等文件 SHA 完全一致），仅仓库名不同
- 默认分支：v2.1；创建于 2026-11-03；无 description / topics
- 即：尚未做任何"改名 / 换图标 / 二次开发"

### 1.3 关键结论
- 这是一个 **Django 后端仓库**；"平台名称 + 图标"主要在 **Vue 前端仓库**里，需要一并提供/克隆。
- "改名 xgsz-admin" 涉及三层：代码内（settings、app 命名、Celery 队列、WebSocket 路由）、前端（标题/Logo/favicon）、部署侧（域名、数据库名、镜像名等）。

## 二、整体定位与目标

把 devops-api 复制体改造成一套面向「机器管理与推理任务编排」的私有运维平台 xgsz-admin：

1. CMDB / 资产管理 + CI/CD + DevOps 能力
2. 任务编排 + 持续交付 + 运维管理
3. 对接 K8s：登录平台即可提交/运行「推理任务」，并管理集群机器/节点/GPU 资源

## 三、品牌改造（改名 + 换图标）—— 建议最先做、做成"统一配置"

1. 后端 Python 侧：
   - `devops_api/settings.py` 项目名、日志前缀、时区等
   - `manage.py` / `asgi.py` / `wsgi.py` / `celery.py` 中 `DJANGO_SETTINGS_MODULE` 与 `-A devops` 引用
   - Celery app 名（`-A devops beat/worker` → `-A xgsz_admin`）
   - 数据库名/连接、Redis 前缀、Channels 通道前缀
2. 前端 Vue 侧（独立仓库）：
   - `index.html` 的 `<title>`、favicon、logo 图片资源
   - 登录页/侧边栏品牌名、主题色
3. 建议引入统一"品牌配置点"（settings + 前端 env），把平台名/图标路径/主题色集中管理。

> 建议顺序：先"纯改名 + 换图标"出一条可运行基线并打 tag（如 `v2.1-xgsz`），再做功能开发，避免返工。

## 四、功能开发路线（分阶段）

### 阶段 0：基线确认与环境打通
- 克隆 xgsz-admin + 前端仓库到开发机
- 准备 MySQL / Redis / MongoDB、Python 3.8+（原依赖 Django 3.1 / Python 3.5+，先在 py3.8 验证兼容）
- 跑通 migrate、celery beat/worker、channels、前端联调
- 产出：环境搭建文档 + 一键启动脚本（docker-compose 更佳）

### 阶段 1：CMDB / 资产管理 / CI-CD / DevOps 加固
- 梳理 cmdb/app/application 模型，补齐机器台账（IP/机型/CPU/内存/GPU/机架/负责人/标签）、凭据库（密码/密钥）、分组/拓扑
- 打通资产与 SSH/Ansible 联动（一键巡检、批量执行）
- 补 CI/CD：代码仓库接入、构建流水线、制品管理、发布单审批
- 产出：CMDB 字段规范、批量导入导出（openpyxl 已有基础）

### 阶段 2：任务编排 / 持续交付 / 运维管理
- 基于 tasks + Celery + Beat 增强：任务模型（作业/步骤/参数/依赖/超时/重试/回调）、定时+手动触发+审批流、执行日志经 Channels 实时推送（consumer 已有基础）
- 持续交付：发布任务（构建 → 制品 → 部署 → 健康检查 → 回滚）
- 运维管理：监控指标（metrices）、告警、审计日志、权限（rbac）

### 阶段 3：K8s 对接 —— 推理任务 + 机器管理（核心增值）
- 复用 apps/k8s，扩展"推理任务"能力。

#### 3.1 推理任务模型（建议）
```
InferenceTask
├─ 镜像 / 命令 / 参数 / 资源配额（CPU / 内存 / GPU）
├─ 输入数据源（对象存储 / 数据集路径）
├─ 输出回传（结果 / 日志 / 指标）
├─ 调度策略（指定节点 / GPU 亲和 / 优先级 / 队列）
└─ 状态机：PENDING → QUEUED → RUNNING → SUCCEEDED / FAILED / CANCELLED
```
- 落地两条路线（先易后难）：
  - 路线 A（推荐先做）：推理任务映射为 K8s **Job**，用 kubernetes client 创建/查询/删除，日志用 channels 回流，结果写对象存储并回传。
  - 路线 B（进阶）：需要复杂编排/排队/GPU 调度时引入 **Argo Workflows / Volcano**，平台只做任务定义与调度接口。

#### 3.2 机器/资源管理
- 集群列表（多集群 kubeconfig）、节点/GPU 资源视图、污点/标签、命名空间 ResourceQuota、镜像仓库对接。

## 五、处理流程（里程碑）

| 里程碑 | 内容 | 产出 | 优先级 |
|---|---|---|---|
| M0 | 环境搭建 + 双仓克隆 + 跑通基线 | 可运行系统 + 部署文档 | P0 |
| M1 | 全局改名 xgsz-admin + 换图标 | 正确品牌基线 tag `v2.1-xgsz` | P0 |
| M2 | CMDB/资产管理加固 + CI/CD | 资产台账 + 流水线 | P1 |
| M3 | 任务编排 + 持续交付 + 运维管理 | 作业/发布/监控/审计 | P1 |
| M4 | K8s 对接：机器管理 | 集群/节点/GPU/配额视图 | P2 |
| M5 | K8s 推理任务（Job/Workflow） | 提交→调度→日志→结果闭环 | P2 |
| M6 | 联调验收 + 文档 + 打包部署 | 生产可用版本 | P2 |

迭代方式：每阶段独立可验收，边开发边在 xgsz-admin 仓库提交，前端仓库同步跟进。

## 六、风险与注意点

1. **前端是独立仓库**：改名/换图标/新功能都牵涉前端，需要前端仓库权限与代码。
2. **依赖偏旧**：Django 3.1 / Python 3.5+ / kubernetes client 12 / Ansible 2.8，新机器建议 Python 3.8，注意 channels/celery/kubernetes client 与新版 K8s API 的兼容。
3. **安全**：`.env` 已提交（含连接串/密钥），接手后第一时间更换密钥并把 `.env` 移出版本库（改 `.gitignore`）。
4. **GPU 调度**：若涉及 GPU 资源管理，需集群装 nvidia device plugin / 队列调度器（Volcano），提前与集群方确认。
5. **多集群/凭据**：kubeconfig 与 SSH 凭据要加密存储，确认密码库加密方式。

## 七、待确认问题

1. 前端 Vue 仓库地址？是否已有 xgsz-admin 对应的前端仓库（改名+图标主要在这里）？
2. 目标部署环境：Linux + 哪个 Python 版本？MySQL/Redis/MongoDB 是否已就绪？
3. "推理任务"具体形态：AI 模型推理（镜像+GPU）？输入/输出数据放哪？是否需要 GPU 调度与排队？
4. 改名范围：只改"显示名 + 图标"，还是连 Python 包名/数据库名/Celery 队列名等底层标识一起改？
5. 下一步优先要哪个产出：改名+换图标的具体文件改动清单，还是更细的功能开发设计文档？
