# 测试策略（分层执行）

## 结论

- 现有测试先全部保留，不删。
- 当前这批测试覆盖了抓取、解析、筛选、去重、任务调度、管理接口和 AI 分析，删掉会直接降低回归兜底能力。
- 先通过“分层执行”解决“测试多、跑得慢”的问题，再决定是否归档。

## 分层

### 1) 核心回归（PR 必跑）

覆盖主链路和高风险逻辑，建议每次改代码都跑：

- `tests.test_api`
- `tests.test_admin_api`
- `tests.test_admin_task_service`
- `tests.test_health_api`
- `tests.test_config`
- `tests.test_scraper_service`
- `tests.test_attachment_service`
- `tests.test_duplicate_service`
- `tests.test_post_job_service`
- `tests.test_scheduler_jobs`
- `tests.test_parser`
- `tests.test_filter_service`

命令：

```bash
python -m unittest -v tests.test_api tests.test_admin_api tests.test_admin_task_service tests.test_health_api tests.test_config tests.test_scraper_service tests.test_attachment_service tests.test_duplicate_service tests.test_post_job_service tests.test_scheduler_jobs tests.test_parser tests.test_filter_service
```

### 2) AI 专项回归（改 AI 逻辑时必跑）

- `tests.test_ai_analysis_service`
- `tests.test_ai_insight_service`

命令：

```bash
python -m unittest -v tests.test_ai_analysis_service tests.test_ai_insight_service
```

### 3) 完整回归（发版/部署前必跑）

命令：

```bash
python -m unittest discover -s tests -v
```

### 4) 部署 smoke（`main` / `v*` / 手动发布必跑）

目标：验证 Docker 部署入口至少还保留以下闭环：

- `/api/health` 返回 readiness 契约，至少包含 `ready` 与 `checks`
- `/api/posts/freshness-summary`
- 前端首页 `/`
- 管理页入口 `/admin`
- `/docs`、`/openapi.json`、`/redoc` 默认不对公网暴露
- 后台登录与关键只读接口：
  - `/api/admin/session/login`
  - `/api/admin/session/me`
  - `/api/admin/sources`
  - `/api/admin/scheduler-config`
  - `/api/admin/task-runs/summary`
- `/admin` 页面默认返回 `X-Robots-Tag: noindex` 与 `Cache-Control: no-store`

命令：

```bash
docker compose up -d --build
python scripts/smoke_deployment.py --base-url http://127.0.0.1:8080 --admin-username smoke-admin --admin-password smoke-pass
docker compose down -v --remove-orphans
```

说明：

- `wait_for_health()` 以 `/api/health.ready == true` 作为就绪条件，不要求顶层 `status` 必须是 `ok`。
- 新部署实例在尚未完成首轮成功抓取前，`/api/health.status` 可能是 `degraded`，这是允许的。
- 镜像发布阶段还会额外拉起 `docker-compose.ghcr.yml`，对 GHCR 镜像入口再做一次同口径 smoke。

### 5) 日志洁净门禁（CI 必跑）

后端测试日志默认不允许出现以下模式：

- `UNIQUE constraint failed`
- `SAWarning`
- `Traceback (most recent call last):`
- `Exception in ASGI application`
- `Task exception was never retrieved`

命令：

```bash
python -m unittest -v tests.test_api tests.test_admin_api tests.test_admin_task_service tests.test_health_api tests.test_config tests.test_scraper_service tests.test_attachment_service tests.test_duplicate_service tests.test_post_job_service tests.test_scheduler_jobs tests.test_parser tests.test_filter_service 2>&1 | tee backend-tests.log
python scripts/check_ci_logs.py backend-tests.log --label backend-tests

python -m unittest discover -s tests -v 2>&1 | tee backend-tests.log
python scripts/check_ci_logs.py backend-tests.log --label backend-tests
```

说明：

- 提 PR 或本地模拟 PR 门禁时，使用上面的“核心回归 + 日志扫描”组合。
- 合并到 `main`、打 `v*` tag 或手动发布前，使用“完整回归 + 日志扫描”组合。

## 可归档判断（先不执行）

只有同时满足下面条件，才考虑归档或合并测试：

1. 连续 2 个版本没有覆盖到任何线上问题。
2. 与其它测试有明显重复，且删掉后关键路径覆盖不下降。
3. 执行耗时明显偏高，并且有更小粒度替代测试。

## 执行节奏建议

1. 提 PR：跑“核心回归 + 日志扫描” + 前端 `npm test` + 前端 `npm run build`。
2. 改 AI 逻辑：在对应阶段额外跑“AI 专项回归”。
3. 合并到 `main`、打 `v*` tag、或手动发布：跑“完整回归 + 日志扫描” + 前端 `npm test` + 前端 `npm run build` + 部署 smoke。
4. CI 中后端测试日志必须再过一次 `scripts/check_ci_logs.py`，不接受“测试绿但日志红”。
