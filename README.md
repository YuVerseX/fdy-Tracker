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
- 监控、HTTPS 和长期运行验证还没补齐

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

启动后可访问：

- Swagger：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/health`

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
- 作用：看任务状态、触发抓取、附件补处理、AI 分析、岗位重建、查看统计摘要
- 现在默认要求后台账号密码
  - 环境变量：`ADMIN_USERNAME` / `ADMIN_PASSWORD`
  - 不配置时管理接口会返回 `503`
  - 前端会话内登录，不做长期记住

## 常用命令

### 后端核心回归（开发/提 PR）

```bash
python -m unittest -v tests.test_api tests.test_admin_api tests.test_admin_task_service tests.test_scraper_service tests.test_attachment_service tests.test_duplicate_service tests.test_post_job_service tests.test_scheduler_jobs tests.test_parser tests.test_filter_service
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

### Docker

```bash
copy .env.example .env
docker compose up -d --build
docker compose logs -f
docker compose down
```

默认访问地址：

- 前端页面：`http://服务器IP/`
- 管理页：`http://服务器IP/admin`
- Swagger：`http://服务器IP/docs`
- 健康检查：`http://服务器IP/api/health`

更完整的 VPS 步骤见 `docs/deploy-vps-docker.md`。

### GHCR 镜像部署

仓库已补 GitHub Actions 自动发布镜像流程：

- 后端镜像：`ghcr.io/yuversex/fdy-tracker-api`
- 前端镜像：`ghcr.io/yuversex/fdy-tracker-web`

发布触发方式：

- push 到 `main`
- push `v*` tag
- 手动触发 workflow

如果你在 VPS / 1Panel 上直接拉镜像，优先使用根目录 `docker-compose.ghcr.yml`。对应说明见 `docs/deploy-1panel-ghcr.md`。

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
- `WEB_PORT`
- `GHCR_NAMESPACE`
- `IMAGE_TAG`

前端配置见 `frontend/.env.example`。

## 开源说明

- 协议：`MIT`
- 欢迎提 Issue / PR，提交流程见 `CONTRIBUTING.md`
- 已补基础 CI（后端测试 + 前端构建），PR 默认走自动检查
- `data/`、`logs/`、构建产物、运行日志、临时文件默认不进仓库
