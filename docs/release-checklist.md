# 发布检查清单（稳妥版）

这份清单用于“准备推 GitHub / 打 tag / 部署前”的最后收口。

## 1. 代码与仓库

- [ ] `git status` 里没有误提交的本地文件（`data/`、`logs/`、`.env`、临时脚本）
- [ ] 文档入口一致：`README.md`、`STATUS.md`、`CONTRIBUTING.md`
- [ ] `CHANGELOG.md` 的 `Unreleased` 已更新

## 2. 安全与配置

- [ ] `.env.example` 不含真实密钥，也不保留默认弱口令
- [ ] `docker-compose*.yml` 不写死真实密钥
- [ ] `docker-compose*.yml` 已强制要求非空 `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `ADMIN_SESSION_SECRET`
- [ ] 部署默认值保持 `ADMIN_SESSION_SECURE=true`、`API_DOCS_ENABLED=false`
- [ ] 仓库扫描无明显密钥痕迹（示例命令）：

```bash
rg -n "sk-[A-Za-z0-9]{10,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}" -S .
```

## 3. 质量门禁

- [ ] PR 合并前已通过核心回归：

```bash
python -m unittest -v tests.test_api tests.test_admin_api tests.test_admin_task_service tests.test_health_api tests.test_config tests.test_scraper_service tests.test_attachment_service tests.test_duplicate_service tests.test_post_job_service tests.test_scheduler_jobs tests.test_parser tests.test_filter_service
```

- [ ] 发版 / 手动发布前已通过完整后端回归：

```bash
python -m unittest discover -s tests -v
```

- [ ] 前端测试通过：

```bash
cd frontend
npm test
```

- [ ] 前端构建通过：

```bash
cd frontend
npm run build
```

- [ ] 后端测试日志已通过危险模式扫描：

```bash
python -m unittest discover -s tests -v 2>&1 | tee backend-tests.log
python scripts/check_ci_logs.py backend-tests.log --label backend-tests
```

说明：这里按发版口径固定使用“完整回归 + 日志扫描”。如果只是模拟 PR 门禁，请改用 `README.md` / `docs/test-strategy.md` 里的“核心回归 + 日志扫描”命令。

## 4. 关键功能冒烟

- [ ] Docker 部署入口已通过 smoke：

```bash
docker compose up -d --build
python scripts/smoke_deployment.py --base-url http://127.0.0.1:8080 --admin-username smoke-admin --admin-password smoke-pass
docker compose down -v --remove-orphans
```

- [ ] `/api/health` 已返回 `ready=true`，并透出 `database / scheduler / freshness / tasks / admin_security`
- [ ] `/docs`、`/openapi.json`、`/redoc` 默认不可从公网入口访问
- [ ] `/admin` 页面已返回 `X-Robots-Tag: noindex` 与 `Cache-Control: no-store`

- [ ] 管理接口提交返回 `202`
- [ ] 任务状态覆盖 `queued/pending -> running/processing -> cancel_requested -> success/failed/cancelled`
- [ ] 管理页任务中心展示 canonical `status / stage / live_metrics / final_metrics`
- [ ] AI 岗位任务提交与重试后仍保持 `ai_job_extraction / 智能岗位识别` 展示口径
- [ ] `finalizing` 中间态和 `cancelled` 归档都显式携带 canonical stage，不依赖前端猜测
- [ ] collecting 阶段只显示采集指标，不伪造结果数
- [ ] 运行态每个可操作状态最多一个主动作，终态只保留少量高价值后续动作，`cancel_requested` 不再展示主动作
- [ ] 前台 freshness 仍保持最近一次成功快照语义

## 5. 发布动作

- [ ] 合并到 `main`
- [ ] 如需发版，打 tag（例如 `v1.2.0`）
- [ ] 确认 GHCR 镜像发布成功（`publish-images.yml`）
- [ ] 确认 `publish-images.yml` 已对 `docker-compose.ghcr.yml` 跑过镜像 smoke
- [ ] 部署侧执行拉取与重启（1Panel 或 docker compose）

## 6. 长跑观察

- [ ] 至少做过一次 24h 定时抓取长跑验证
- [ ] 24h 内没有 stale heartbeat
- [ ] 24h 内没有 freshness 倒退
- [ ] 24h 内没有容器重启循环
