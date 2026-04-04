# First Source Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 先把江苏人社厅第一源第一版从“可演示、可本地使用”收稳到“单源闭环可信、可维护、可作为第二源接入前基线”。

**Architecture:** 先拆掉单源硬编码和启动副作用，再修抓取与更新语义，随后收口任务系统/API/UI 契约，最后补齐测试、CI、安全和长跑门禁。第二源接入不是本计划目标；本计划只为第二源创造稳定底座。

**Tech Stack:** FastAPI, SQLAlchemy, APScheduler, requests/BeautifulSoup, Vue 3, Vitest/Jest-style frontend tests, unittest, Docker Compose, GitHub Actions

---

## 总原则

- 先收口共享契约，再动展示层。
- 先解决“数据是否可信”，再解决“页面是否好看”。
- 先让系统说真话，再让系统更自动化。
- 任何会阻塞第二源的问题都在前 4 个任务内解决。

## 阶段地图

1. Phase A: 关掉启动副作用，冻结共享边界
2. Phase B: 修抓取传输与同 URL 更新语义
3. Phase C: 收口任务中心、API 与前后台契约
4. Phase D: 建立回归、CI、安全、部署、观测门禁
5. Phase E: 通过单源收稳验收，再决定是否进入第二源接入

## 第二源前硬门禁

- 启动不再自动回填历史数据
- 通用层不再直接依赖江苏专用逻辑
- `source_id=1` / 江苏默认值 / 全局 freshness 语义清除
- 抓取链具备 HTTPS、retry/backoff、失败可见性
- 同 URL 更新能正确回写主记录、附件、岗位、分析结果
- 任务中心状态不再伪实时，前台记录不再伪完整
- 关键回归、CI、部署、安全、长跑门禁可重复执行

### Task 1: 启动副作用剥离与维护入口显式化

**Files:**
- Modify: `src/main.py`
- Modify: `src/database/bootstrap.py`
- Modify: `src/api/admin.py`
- Modify: `src/services/admin_task_service.py`
- Test: `tests/test_admin_api.py`
- Test: `tests/test_admin_task_service.py`
- Doc: `README.md`
- Doc: `STATUS.md`

- [ ] 定义启动期允许做的事情：schema 初始化、必要 seed、scheduler 初始化；不允许自动执行历史补齐、去重补齐、分析补齐。
- [ ] 把 `backfill_rule_analyses`、`backfill_rule_insights`、`backfill_post_counselor_flags`、`backfill_duplicate_posts` 从 `initialize_database()` 中移出，改为显式后台任务或一次性维护入口。
- [ ] 为后台任务增加“维护任务”分类，和抓取/附件/AI 分析区分，避免应用重启触发隐式写库。
- [ ] 补回归：重复启动应用不新增 `post_analyses`、`post_insights`、duplicate 结果，不改变帖子业务字段。
- [ ] 更新 README/STATUS，明确“首次启动”和“历史补齐”是两个动作。

**Exit Criteria:**
- 重启服务不再触发历史数据写入。
- 维护类补齐只能通过显式 API/管理台触发。
- 这一步完成后，后续任何验证都不会被启动副作用污染。

### Task 2: source 作用域与江苏专用逻辑隔离

**Files:**
- Modify: `src/api/posts.py`
- Modify: `src/api/admin.py`
- Modify: `src/services/duplicate_service.py`
- Modify: `src/services/ai_analysis_service.py`
- Modify: `src/services/post_job_service.py`
- Modify: `src/services/admin_task_service.py`
- Modify: `src/scheduler/jobs.py`
- Modify: `src/scrapers/jiangsu_hrss.py`
- Test: `tests/test_api.py`
- Test: `tests/test_admin_api.py`
- Test: `tests/test_duplicate_service.py`
- Test: `tests/test_ai_analysis_service.py`

- [ ] 列出当前通用层里直接使用江苏规则的函数和口径：正文清洗、城市判断、辅导员范围词、freshness 汇总、默认 source 解析。
- [ ] 为 source 能力建立最小共享边界：`source scope`、`content normalizer`、`location vocabulary`、`freshness scope`、`duplicate scope`。
- [ ] 把任何直接 `import jiangsu_hrss` 或直接假设“江苏=默认”的逻辑下沉到 source profile / source adapter。
- [ ] 消除 `source_id=1`、`江苏省人社厅`、单源默认值在后端接口和调度配置中的写死行为。
- [ ] 让 public freshness 和 admin default source 都显式带 scope，而不是全局唯一事实。

**Exit Criteria:**
- 通用服务不再直接依赖江苏专用逻辑。
- `source` 成为明确输入，而不是隐式全局默认。
- 这是第二源接入前最重要的结构性门禁。

### Task 3: 抓取传输可靠性与 HTTPS 切换

**Files:**
- Modify: `src/scrapers/base.py`
- Modify: `src/scrapers/jiangsu_hrss.py`
- Modify: `src/config.py`
- Modify: `src/database/bootstrap.py`
- Test: `tests/test_scraper_service.py`
- Test: `tests/test_scheduler_jobs.py`
- Script: `scripts/test_scraper.py`

- [ ] 将江苏源 `base_url`、Ajax URL、详情页拼接 URL 全量切到 HTTPS。
- [ ] 去掉 `verify=False`，把 timeout、重试次数、退避策略纳入统一抓取配置。
- [ ] 统一分页抓取、详情抓取、附件抓取的错误处理语义：失败可统计、可记录、不可静默把有效旧值洗成空值。
- [ ] 为列表页空页、重复页、页码越界、详情页失败、Ajax 临时失败补回归。
- [ ] 输出抓取结果统计：成功页数、失败页数、重试次数、详情失败数、跳过数。

**Exit Criteria:**
- 源站短时抖动不会直接让抓取任务失败或静默丢数据。
- 同一条帖子详情失败不会覆盖旧正文为空。
- 所有种子配置、默认 source URL、抓取脚本都改为 HTTPS。

### Task 4: 同 URL 刷新语义与子记录差量同步

**Files:**
- Modify: `src/services/scraper_service.py`
- Modify: `src/services/attachment_service.py`
- Modify: `src/services/post_job_service.py`
- Modify: `src/database/models.py`
- Test: `tests/test_scraper_service.py`
- Test: `tests/test_attachment_service.py`
- Test: `tests/test_post_job_service.py`

- [ ] 定义“同 URL 更新”的 authoritative 语义：哪些字段跟随正文刷新，哪些字段保留人工结果，哪些字段需要重算。
- [ ] 把当前“只补缺不刷新”的策略改成“按变更检测差量刷新”，覆盖正文、结构化字段、附件元数据、岗位集合、派生分析。
- [ ] 把附件和岗位从 `delete + reinsert` 改为 diff/upsert，同步时保留稳定 identity，避免 1:1/1:n 关系反复抖动。
- [ ] 为“帖子更新后 duplicate、岗位、摘要、附件来源说明如何同步”定义统一刷新顺序。
- [ ] 加回归：同 URL 内容变化、附件列表变化、岗位表变化、多次重复抓取幂等。

**Exit Criteria:**
- 同 URL 帖子变更能正确刷新而不残留脏数据。
- 重复抓取不再出现 `SAWarning`。
- 附件/岗位/派生分析结果有稳定同步顺序。

### Task 5: AI 分析幂等写入与冲突围栏

**Files:**
- Modify: `src/services/ai_analysis_service.py`
- Modify: `src/services/admin_task_service.py`
- Modify: `src/api/admin.py`
- Test: `tests/test_ai_analysis_service.py`
- Test: `tests/test_ai_insight_service.py`

- [ ] 盘点 `post_analyses` / `post_insights` 的唯一约束和写入路径，统一成幂等更新路径。
- [ ] 对抓取后联动分析、后台批量分析、基础分析补齐建立同帖冲突围栏。
- [ ] 让 `IntegrityError` 从日志告警升级为显式失败路径和测试断言。
- [ ] 明确分析结果与正文/附件/岗位变更的重算触发条件。

**Exit Criteria:**
- 批量 AI、重试、补齐、抓取联动不再产生唯一约束冲突日志。
- 同帖最终只保留一份权威分析记录。

### Task 6: 管理任务状态可信化

**Files:**
- Modify: `src/services/admin_task_service.py`
- Modify: `src/services/task_progress.py`
- Modify: `src/api/admin.py`
- Test: `tests/test_admin_task_service.py`
- Test: `tests/test_admin_api.py`

- [ ] 明确任务状态模型：`queued/running/cancel_requested/success/failed/cancelled` 与 `stage/stage_label/live_metrics/final_metrics` 的 canonical 契约。
- [ ] 区分“可信快照”“降级快照”“仅本机状态”，禁止把本地 JSON 心跳当成强一致实时状态。
- [ ] 补任务状态 envelope：`snapshot_at`、`trust_level`、`degraded_reason`、`instance_scope`、`scope_summary`。
- [ ] 为取消、重试、心跳超时、跨实例不可见状态定义明确文案与动作禁用条件。
- [ ] 如果仍保留本地 JSON 方案，至少让前端知道这只是降级态；中期目标应迁移到 DB 或统一状态存储。

**Exit Criteria:**
- 管理台接口返回的任务状态语义单一、可解释、可测试。
- 降级模式下不会再伪装成可信实时状态。

### Task 7: API 与前后台展示契约收口

**Files:**
- Modify: `src/api/posts.py`
- Modify: `src/api/admin.py`
- Modify: `frontend/src/views/PostList.vue`
- Modify: `frontend/src/views/PostDetail.vue`
- Modify: `frontend/src/views/AdminDashboard.vue`
- Modify: `frontend/src/views/post-list/usePostListState.js`
- Modify: `frontend/src/views/post-detail/usePostDetailState.js`
- Modify: `frontend/src/views/admin/useAdminDashboardState.js`
- Modify: `frontend/src/views/admin/adminDashboardDataService.js`
- Modify: `frontend/src/views/admin/adminTaskRunPresentation.js`
- Modify: `frontend/src/views/admin/adminDashboardTaskActions.js`
- Modify: `frontend/src/utils/postListPresentation.js`
- Modify: `frontend/src/utils/postDetailPresentation.js`
- Test: `frontend/tests/`

- [x] 把前后台共享契约收口为四类对象：`source scope`、`freshness scope`、`task snapshot trust`、`record completeness/provenance`。
- [x] 管理台初始态不再硬编码江苏，任何默认 source 都来自后端 source options。
- [x] public freshness 文案改成“当前查询范围最近一次成功抓取”，不再给全站唯一 freshness 错觉。
- [x] 列表/详情显式展示 duplicate、附件来源、岗位来源、AI/rule 摘要来源、记录完整度，而不是把缺失数据渲染成正常数据。
- [x] 管理台总览和处理卡片变成 source-aware：展示作用范围、禁用原因、最近成功/失败、backlog。

**Exit Criteria:**
- 前台不会再出现“页面正常但数据不完整/不可信”的误导。
- 后台不会再出现“单源默认值 + 伪实时状态”的误导。

### Task 8: 第一源回归门禁与日志洁净

**Files:**
- Modify: `docs/test-strategy.md`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/publish-images.yml`
- Test: `tests/test_api.py`
- Test: `tests/test_admin_api.py`
- Test: `tests/test_scraper_service.py`
- Test: `tests/test_attachment_service.py`
- Test: `tests/test_post_job_service.py`
- Test: `tests/test_admin_task_service.py`
- Test: `tests/test_ai_analysis_service.py`
- Test: `frontend/tests/`

- [x] 把以下回归固化为 PR 门禁：抓取入库幂等、同 URL 更新、附件回写、岗位回写、freshness 作用域、任务取消/重试/降级、duplicate 展示。
- [x] 把 `UNIQUE constraint failed`、`SAWarning`、未批准异常日志升级为 CI 失败信号。
- [x] PR 跑关键回归 + 前端 `npm test` + `npm run build`；主干/Tag 跑全量回归 + 镜像 smoke。
- [x] 增加 smoke：`/api/health`、`/api/posts/freshness-summary`、前端首页、管理台关键接口。

**Exit Criteria:**
- 任何会打破第一源闭环的改动都能在 PR 阶段被阻断。
- “测试绿但日志红”不再被接受。

### Task 9: 安全部署基线与长跑验证

**Files:**
- Modify: `src/config.py`
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `docker-compose.ghcr.yml`
- Modify: `frontend/nginx.conf`
- Modify: `src/api/health.py`
- Modify: `SECURITY.md`
- Modify: `docs/release-checklist.md`
- Modify: `docs/deploy-vps-docker.md`
- Modify: `docs/deploy-1panel-ghcr.md`
- Modify: `STATUS.md`

- [x] 去掉部署态弱默认值，强制非空 admin 凭证与 session secret。
- [x] 明确 HTTPS、secure cookie、`/admin` 和 `/docs` 的暴露策略。
- [x] 把 health 升级为 readiness/调度状态/最新成功抓取年龄/任务心跳可观测。
- [ ] 至少做一次 24h 定时抓取长跑验证；目标是无 stale heartbeat、无 freshness 倒退、无容器重启循环。
- [x] 文档以代码和 workflow 为准收口，不再保留互相冲突的默认值、命令和门禁描述。

**Exit Criteria:**
- 当前实例即使不接第二源，也具备长期运行的最低安全和运维基线。
- 这一阶段完成后，才能说“第一源第一版已收稳”。

## 推荐并行方式

- 串行：Task 1 -> Task 2 -> Task 3 -> Task 4
- 可并行：Task 5 与 Task 6 可在 Task 2 完成后分别启动
- 可并行：Task 7 需要等待 Task 6 的任务契约冻结，但可以和 Task 8 前后脚推进
- 收尾：Task 9 最好在 Task 8 的 CI 门禁稳定后执行

## 最短路径

如果目标是“先把第一源收稳，再接第二源”，最短路径是：

1. Task 1 关掉启动副作用
2. Task 2 拆 source 边界和单源写死
3. Task 3 修抓取传输可靠性和 HTTPS
4. Task 4 修同 URL 刷新与附件/岗位差量同步
5. Task 6 收口任务状态可信化
6. Task 7 收口前后台共享契约
7. Task 8 建回归和 CI 门禁
8. Task 9 做安全基线和 24h 长跑

## 完成定义

同时满足以下条件，才建议进入第二源接入：

- 第一源重复抓取、定时抓取、手动抓取、附件补处理、去重、分析、岗位抽取都可重复验证
- 后端无 `source_id=1`、江苏默认值、全局 freshness 假设
- 前台和后台能准确说明数据来源、完整度、duplicate 状态、任务状态可信度
- 全量测试、前端构建、镜像 smoke、24h 长跑全部通过
- README / STATUS / test strategy / release checklist / deploy docs 与代码一致
