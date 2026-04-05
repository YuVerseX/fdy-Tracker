# 江苏专职辅导员招聘追踪系统

一个面向江苏高校辅导员招聘信息的追踪项目。当前已经打通“抓取 -> 解析 -> 入库 -> API -> 前端 -> 管理台”主链路，适合本地使用、演示和继续迭代。

## 当前状态

- 当前版本：`v1.1.0`
- 当前结论：`可演示、可本地使用，未生产就绪`
- 当前主数据源：`江苏省人力资源和社会保障厅`
- 当前前端页面：`列表页 / 详情页 / 管理页`
- AI 状态：`可选增强，不配 OPENAI_API_KEY 时自动退回规则分析`

当前还没收完的重点：

- 多数据源能力还没落地
- 结果公示类帖子的岗位口径还在持续收口
- 监控、真实 HTTPS 终止和 24h 长跑验证还没补齐

## 当前能力

- 江苏人社厅列表页、详情页抓取
- 辅导员相关岗位识别与分层
- 结构化字段解析
  - 性别、学历、专业、地点、人数、年龄、政治面貌、报名时间等
- 附件下载与解析
  - `xls` / `xlsx` / `pdf`
- 岗位级抽取与岗位快照
- AI 分析与规则分析双通道
- 后台管理接口
  - 手动抓取
  - 历史附件补处理
  - AI 分析
  - 岗位重建
  - 调度配置
- Vue 前端列表页、详情页、管理页
- Docker 基础运行配置
- 单机 VPS 的 Docker 双容器部署基线
- GitHub Actions 自动发布 GHCR 镜像

## 快速开始

### 1. 后端

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python scripts/init_db.py
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

说明：

- `.env.example` 现在按“部署默认收紧”给出基线。至少先填好：`ADMIN_USERNAME`、`ADMIN_PASSWORD`、`ADMIN_SESSION_SECRET`（建议至少 32 个随机字符）。
- 如果你要在本机纯 HTTP 调试管理页，请把 `ADMIN_SESSION_SECURE=false`。
- 如果你要在本机看 Swagger / OpenAPI，请把 `API_DOCS_ENABLED=true`。
- `python scripts/init_db.py` 和应用启动现在只负责数据库结构、兼容字段、内置 source / scheduler 默认配置初始化。
- 启动不会再自动补齐历史规则分析、规则洞察、辅导员口径或重复治理，避免重启实例时隐式改写历史数据。

启动后可访问：

- 健康检查：`http://127.0.0.1:8000/api/health`
- Swagger：`http://127.0.0.1:8000/docs`（仅在 `API_DOCS_ENABLED=true` 时开放）

### 2. 前端

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

默认开发地址通常是 `http://127.0.0.1:5173`。

前端生产默认走当前域名下的 `/api`；本地开发时由 Vite 代理转发到后端。

### 3. 管理页

- 地址：`/admin`
- 作用：看系统状态、执行数据处理、触发 AI 增强、查看任务记录
- 数据处理：抓取、附件补处理、重复治理、基础内容分析、岗位索引
- AI 增强：在 OpenAI 就绪时补更细摘要、阶段判断和岗位识别
- 未配置 OpenAI 时，后台仍保持基础模式可用
- 一次性维护补齐需显式触发，不会在启动阶段自动执行
  - `POST /api/admin/run-maintenance`
  - `operation` 支持：`rule_analysis_refresh`、`rule_insight_refresh`、`counselor_flag_repair`、`duplicate_full_rebuild`
- 现在默认要求后台账号密码，并使用页面内会话登录
  - 必填环境变量：`ADMIN_USERNAME` / `ADMIN_PASSWORD` / `ADMIN_SESSION_SECRET`
  - `ADMIN_SESSION_SECRET` 建议至少 32 个随机字符；过短会被后台拒绝
  - 任一未配置时，管理会话接口与管理业务接口会返回 `503`
  - 部署默认要求 `ADMIN_SESSION_SECURE=true`
  - 不再触发浏览器原生 Basic Auth 弹窗
  - 前台首页和详情页通过公开 `GET /api/posts/freshness-summary` 展示任务新鲜度，不要求后台登录

## 常用命令

### 后端核心回归（开发/提 PR）

```bash
python -m unittest -v tests.test_api tests.test_admin_api tests.test_admin_task_service tests.test_health_api tests.test_config tests.test_scraper_service tests.test_attachment_service tests.test_duplicate_service tests.test_post_job_service tests.test_scheduler_jobs tests.test_parser tests.test_filter_service 2>&1 | tee backend-tests.log
python scripts/check_ci_logs.py backend-tests.log --label backend-tests
```

### AI 专项回归（改 AI 逻辑时）

```bash
python -m unittest -v tests.test_ai_analysis_service tests.test_ai_insight_service
```

### 后端完整回归（发版/部署前）

```bash
python -m unittest discover -s tests -v
```

### 前端构建

```bash
cd frontend
npm run build
```

### 前端回归（改列表 / 详情 / 管理台时）

```bash
cd frontend
npm test
npm run build
```

### Docker

```bash
copy .env.example .env
docker compose up -d --build
docker compose logs -f
docker compose down
```

默认访问地址：

- 前端页面：`http://服务器IP/`
- 健康检查：`http://服务器IP/api/health`

部署基线说明：

- `/docs`、`/openapi.json`、`/redoc` 默认不会从公网入口暴露。
- `/admin` 前端入口虽然仍可访问，但不应直接裸露公网；至少要放在 HTTPS 反向代理后，再补 IP 白名单、额外鉴权或等效访问控制。
- `/api/health` 现在是 readiness 聚合探针；新部署实例在首轮成功抓取前，可能出现 `status=degraded` 但 `ready=true`。

### 统一出站代理（可选）

如果你的 VPS 已经提供本地 HTTP / SOCKS5 代理端口，可以通过 `OUTBOUND_PROXY_URL` 让抓取、附件下载、智能摘要整理、智能岗位识别统一走该出口。

示例：

```text
OUTBOUND_PROXY_URL=http://127.0.0.1:7890
```

或：

```text
OUTBOUND_PROXY_URL=socks5://127.0.0.1:40000
```

说明：

- 未配置时，服务保持默认直连行为。
- 当使用 `socks5` 时，运行环境必须安装 `socksio`。
- 管理台“系统设置”区会显示当前代理状态、脱敏后的代理出口和代理范围。
- 宿主机级 WARP / 路由改写仍属于系统网络层；`OUTBOUND_PROXY_URL` 只控制应用级显式代理出口。

更完整的 VPS 步骤见 `docs/deploy-vps-docker.md`。

### GHCR 镜像部署

仓库已补 GitHub Actions 自动发布镜像流程：

- 后端镜像：`ghcr.io/yuversex/fdy-tracker-api`
- 前端镜像：`ghcr.io/yuversex/fdy-tracker-web`

发布触发方式：

- 提 PR：跑后端核心回归 + 后端日志扫描 + 前端测试 + 前端构建
- push 到 `main`：跑后端完整回归 + 后端日志扫描 + 前端测试/构建 + Docker compose smoke，再发布镜像并验证 `docker-compose.ghcr.yml`
- push `v*` tag：跑同一套完整回归 + 后端日志扫描 + smoke，再发布镜像并验证 `docker-compose.ghcr.yml`
- 手动发布：从 `CI` workflow 触发，同样先走完整回归 + 后端日志扫描 + smoke

如果你在 VPS / 1Panel 上直接拉镜像，优先使用根目录 `docker-compose.ghcr.yml`。对应说明见 `docs/deploy-1panel-ghcr.md`。

不建议把 `latest` 当成稳定部署锚点。要做可回滚部署，优先使用 `v*` 或 `sha-*` 标签。

## 项目结构

```text
fdy-Tracker/
├── src/                  # 后端
├── frontend/             # 前端
├── tests/                # 回归测试
├── scripts/              # 手工脚本
├── docs/                 # 项目文档
├── data/                 # 本地数据，不提交
├── logs/                 # 本地日志，不提交
├── README.md
├── STATUS.md
├── CONTRIBUTING.md
├── CHANGELOG.md
└── LICENSE
```

## 文档入口

- `README.md`：项目总入口，以当前实现为准
- `STATUS.md`：当前状态、风险和下一步
- `CONTRIBUTING.md`：本地开发和提交流程
- `SECURITY.md`：安全问题上报和密钥管理基线
- `docs/README.md`：文档导航
- `docs/release-checklist.md`：发布前检查清单
- `docs/test-strategy.md`：测试分层和执行口径
- `docs/deploy-vps-docker.md`：单机 VPS Docker 部署说明
- `docs/deploy-1panel-ghcr.md`：1Panel / GHCR 镜像部署说明

## 配置说明

根目录 `.env.example` 提供后端配置模板，重点变量包括：

- `DATABASE_URL`
- `SCRAPER_INTERVAL`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `AI_ANALYSIS_MODEL`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `ADMIN_SESSION_SECRET`
- `ADMIN_SESSION_SECURE`
- `API_DOCS_ENABLED`
- `WEB_PORT`
- `GHCR_NAMESPACE`
- `IMAGE_TAG`

前端配置见 `frontend/.env.example`。

## 开源说明

- 协议：`MIT`
- 欢迎提 Issue / PR，提交流程见 `CONTRIBUTING.md`
- 已补分层 CI：PR 跑核心回归 + 后端日志扫描；`main` / `v*` / 手动发布跑完整回归 + 后端日志扫描 + compose smoke
- `data/`、`logs/`、构建产物、运行日志、临时文件默认不进仓库
