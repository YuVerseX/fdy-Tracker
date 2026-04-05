# 第一源稳定性与 UI 收口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前第一源版本收口到“后端状态说真话、管理台失败态不伪装、公开页错误可恢复、发布链不会先暴露坏镜像”的可继续迭代基线。

**Architecture:** 后端只修正当前单源版本最关键的运行语义，不引入多源平台抽象；重点是 scheduler readiness、后台任务 cancel/source 校验契约和管理入口的一致性。前端保持现有 admin/public 视觉体系，不重做风格，只按 `ui-ux-pro-max` 把错误恢复、空态/失败态分离、表单可访问性和动态提示播报语义收口到可信状态。

**Tech Stack:** FastAPI, SQLAlchemy, APScheduler, unittest, Vue 3, node:test, Vite, Tailwind, GitHub Actions, ui-ux-pro-max

---

## File Structure

**Backend runtime truthfulness**
- Modify: `src/scheduler/jobs.py`
- Test: `tests/test_scheduler_jobs.py`
- Test: `tests/test_health_api.py`

**Task cancel and source validation**
- Modify: `src/services/admin_task_service.py`
- Modify: `src/api/admin.py`
- Modify: `frontend/src/views/admin/adminDashboardTaskActions.js`
- Test: `tests/test_admin_task_service.py`
- Test: `tests/test_admin_api.py`
- Test: `frontend/tests/adminDashboardTaskActions.test.mjs`

**Admin UI reliability and accessibility**
- Modify: `frontend/src/views/admin/useAdminDashboardState.js`
- Modify: `frontend/src/views/admin/adminDashboardDataService.js`
- Modify: `frontend/src/views/admin/adminDashboardSectionAdapters.js`
- Modify: `frontend/src/views/admin/sections/AdminSystemSection.vue`
- Modify: `frontend/src/views/admin/sections/AdminTaskRunsSection.vue`
- Modify: `frontend/src/views/AdminDashboard.vue`
- Modify: `frontend/src/components/ui/AppNotice.vue`
- Test: `frontend/tests/adminDashboardDataService.test.mjs`
- Test: `frontend/tests/adminDashboardStateBindings.test.mjs`
- Test: `frontend/tests/adminDashboardSharedUi.test.mjs`
- Test: `frontend/tests/adminDashboardTaskCardsUi.test.mjs`

**Public page recovery**
- Modify: `frontend/src/utils/postFilters.js`
- Modify: `frontend/src/views/post-list/usePostListState.js`
- Modify: `frontend/src/views/post-detail/usePostDetailState.js`
- Modify: `frontend/src/views/PostList.vue`
- Modify: `frontend/src/views/PostDetail.vue`
- Test: `frontend/tests/postFilters.test.mjs`
- Test: `frontend/tests/postListCopy.test.mjs`
- Test: `frontend/tests/postDetailPresentation.test.mjs`

**Release and smoke docs**
- Modify: `.github/workflows/publish-images.yml`
- Modify: `docs/test-strategy.md`
- Modify: `docs/release-checklist.md`
- Create: `tests/test_release_artifacts.py`

## UI Constraint

Task 3 和 Task 4 必须显式遵守 `ui-ux-pro-max`，但保留当前站点的公共视觉语言，不做无关“改头换面”：

- 保留现有 admin/public shell，不引入营销式 hero、视频背景、夸张动效。
- 采用 `ui-ux-pro-max` 里真正适用的部分：`Data-Dense Dashboard`、高对比 slate/sky 信息层级、清晰 focus states、紧凑卡片布局。
- 错误态必须给恢复动作，不能只显示一句失败文案。
- 空态和失败态必须分开。
- 表单控件必须有可关联 label。
- 动态反馈必须能被辅助技术播报；静态说明性 notice 不强制进入 live region。

### Task 1: 修正 scheduler readiness 语义

**Files:**
- Modify: `src/scheduler/jobs.py`
- Test: `tests/test_scheduler_jobs.py`
- Test: `tests/test_health_api.py`

- [ ] **Step 1: 先补 readiness 失真回归测试**

在 `tests/test_scheduler_jobs.py` 中补两条真正的问题用例，锁定“enabled 但 scheduler 没跑”和“enabled 但 job 丢了”都必须 `ready=false`：

```python
def test_get_scheduler_runtime_health_should_require_running_scheduler_when_enabled(self):
    db = MagicMock()
    config = SimpleNamespace(
        enabled=True,
        interval_seconds=1800,
        default_source_id=9,
        default_max_pages=5,
    )
    source_query = MagicMock()
    source_query.filter.return_value.first.return_value = SimpleNamespace(
        id=9,
        name="江苏省人社厅",
        is_active=True,
    )
    db.query.return_value = source_query

    with patch("src.scheduler.jobs.peek_scheduler_config", return_value=config), patch(
        "src.scheduler.jobs.scheduler"
    ) as mocked_scheduler:
        mocked_scheduler.running = False
        mocked_scheduler.get_job.return_value = None
        payload = scheduler_jobs.get_scheduler_runtime_health(db)

    self.assertEqual(payload["status"], "degraded")
    self.assertFalse(payload["ready"])
    self.assertIn("scheduler_not_running", payload["issues"])


def test_get_scheduler_runtime_health_should_require_registered_scrape_job_when_enabled(self):
    db = MagicMock()
    config = SimpleNamespace(
        enabled=True,
        interval_seconds=1800,
        default_source_id=9,
        default_max_pages=5,
    )
    source_query = MagicMock()
    source_query.filter.return_value.first.return_value = SimpleNamespace(
        id=9,
        name="江苏省人社厅",
        is_active=True,
    )
    db.query.return_value = source_query

    with patch("src.scheduler.jobs.peek_scheduler_config", return_value=config), patch(
        "src.scheduler.jobs.scheduler"
    ) as mocked_scheduler:
        mocked_scheduler.running = True
        mocked_scheduler.get_job.return_value = None
        payload = scheduler_jobs.get_scheduler_runtime_health(db)

    self.assertEqual(payload["status"], "degraded")
    self.assertFalse(payload["ready"])
    self.assertIn("scrape_job_missing", payload["issues"])
```

在 `tests/test_health_api.py` 里补顶层健康检查用例，确认 `/api/health.ready` 会随 scheduler readiness 一起变成 `false`：

```python
def test_health_should_return_error_when_enabled_scheduler_is_not_running(self):
    self.db.execute.return_value = 1

    with patch.multiple(
        "src.api.health.settings",
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="secret-pass",
        ADMIN_SESSION_SECRET="x" * 32,
        ADMIN_SESSION_SECURE=True,
        API_DOCS_ENABLED=False,
    ), patch(
        "src.api.health.get_scheduler_runtime_health",
        return_value={
            "status": "degraded",
            "ready": False,
            "scheduler_running": False,
            "enabled": True,
            "interval_seconds": 3600,
            "default_source_id": 1,
            "default_source_scope": "source",
            "default_max_pages": 5,
            "source_name": "江苏省人社厅",
            "next_run_at": None,
            "issues": ["scheduler_not_running", "scrape_job_missing"],
        },
    ), patch(
        "src.api.health.get_public_task_freshness_summary",
        return_value={
            "scope": "source",
            "requested_source_id": 1,
            "latest_success_at": None,
            "latest_success_run": None,
        },
    ), patch(
        "src.api.health.get_task_runtime_health_summary",
        return_value={
            "running_task_count": 0,
            "stale_task_count": 0,
            "latest_heartbeat_at": None,
            "latest_heartbeat_age_seconds": None,
            "stale_tasks": [],
        },
    ):
        response = self.client.get("/api/health")

    self.assertEqual(response.status_code, 200)
    payload = response.json()
    self.assertEqual(payload["status"], "error")
    self.assertFalse(payload["ready"])
    self.assertIn("scrape_job_missing", payload["checks"]["scheduler"]["issues"])
```

- [ ] **Step 2: 跑定向后端测试，确认新断言先失败**

Run:

```bash
python -m unittest tests.test_scheduler_jobs tests.test_health_api -v
```

Expected:
- FAIL
- `get_scheduler_runtime_health()` 现在仍可能在 `scheduler.running=False` 或 `job=None` 时返回 `ready=True`
- `/api/health` 还会接受这个错误的 scheduler readiness

- [ ] **Step 3: 在 scheduler runtime health 中把“enabled + running + job registered”作为真实 ready 条件**

在 `src/scheduler/jobs.py` 只修正当前单源语义，不做额外架构扩张：

```python
def get_scheduler_runtime_health(db) -> dict[str, Any]:
    issues: list[str] = []
    config: SchedulerConfig | None = None
    source = None

    try:
        config = peek_scheduler_config(db)
    except Exception as exc:
        return {
            "status": "error",
            "ready": False,
            "scheduler_running": bool(scheduler.running),
            "enabled": None,
            "interval_seconds": None,
            "default_source_id": None,
            "default_source_scope": "source",
            "default_max_pages": None,
            "source_name": None,
            "next_run_at": None,
            "issues": [f"scheduler_config_unavailable:{exc}"],
        }

    if config is None:
        return {
            "status": "error",
            "ready": False,
            "scheduler_running": bool(scheduler.running),
            "enabled": None,
            "interval_seconds": None,
            "default_source_id": None,
            "default_source_scope": "source",
            "default_max_pages": None,
            "source_name": None,
            "next_run_at": None,
            "issues": ["scheduler_config_missing"],
        }

    job = scheduler.get_job(SCRAPE_JOB_ID)
    if not scheduler.running:
        issues.append("scheduler_not_running")
    if not config.enabled:
        issues.append("scheduler_disabled")

    if not config.default_source_id:
        issues.append("default_source_missing")
    else:
        source = db.query(Source).filter(Source.id == config.default_source_id).first()
        if source is None:
            issues.append("default_source_not_found")
        elif not source.is_active:
            issues.append("default_source_inactive")

    if config.enabled and job is None:
        issues.append("scrape_job_missing")

    next_run_at = job.next_run_time.isoformat() if job and getattr(job, "next_run_time", None) else None
    ready = (
        not config.enabled
        or (
            bool(scheduler.running)
            and source is not None
            and bool(source.is_active)
            and job is not None
        )
    )
    status = "ok" if not issues else "degraded"

    return {
        "status": status,
        "ready": ready,
        "scheduler_running": bool(scheduler.running),
        "enabled": bool(config.enabled),
        "interval_seconds": config.interval_seconds,
        "default_source_id": config.default_source_id,
        "default_source_scope": "source",
        "default_max_pages": config.default_max_pages,
        "source_name": source.name if source else None,
        "next_run_at": next_run_at,
        "issues": issues,
    }
```

`src/api/health.py` 不需要改 readiness 聚合逻辑，只保留：

```python
ready = bool(database_check["ready"] and scheduler_check["ready"])
```

这样新部署但尚无成功抓取时仍可保持 `status="degraded", ready=true`，前提是 scheduler 本身真的健康。

- [ ] **Step 4: 再跑定向后端测试**

Run:

```bash
python -m unittest tests.test_scheduler_jobs tests.test_health_api -v
```

Expected:
- PASS
- `enabled=true + scheduler.running=false` 时，`scheduler.ready == false`
- `enabled=true + job missing` 时，`scheduler.ready == false`
- `/api/health.ready` 不再吃掉这类 scheduler 失真

- [ ] **Step 5: 提交 readiness 语义修正**

```bash
git add src/scheduler/jobs.py tests/test_scheduler_jobs.py tests/test_health_api.py
git commit -m "fix: 修正调度健康检查的真实就绪语义"
```

### Task 2: 收口任务取消契约并统一 source-scoped 入口校验

**Files:**
- Modify: `src/services/admin_task_service.py`
- Modify: `src/api/admin.py`
- Modify: `frontend/src/views/admin/adminDashboardTaskActions.js`
- Test: `tests/test_admin_task_service.py`
- Test: `tests/test_admin_api.py`
- Test: `frontend/tests/adminDashboardTaskActions.test.mjs`

- [ ] **Step 1: 先补取消与 source 校验回归测试**

在 `tests/test_admin_task_service.py` 中补 scrape cancel 拒绝用例：

```python
def test_request_task_run_cancel_should_reject_running_scrape_task(self):
    created = admin_task_service.start_task_run(
        task_type="manual_scrape",
        summary="手动抓取进行中",
        params={"source_id": 1, "max_pages": 3},
    )

    with self.assertRaisesRegex(ValueError, "task_not_cancelable"):
        admin_task_service.request_task_run_cancel(task_id=created["id"])
```

在 `tests/test_admin_api.py` 中补 API 层校验：

```python
def test_cancel_task_run_should_return_409_for_non_cancelable_scrape_task(self):
    self._login()
    with patch(
        "src.api.admin.request_task_run_cancel",
        side_effect=ValueError("task_not_cancelable"),
    ):
        response = self.client.post("/api/admin/task-runs/run-scrape-1/cancel")

    self.assertEqual(response.status_code, 409)
    self.assertIn("当前任务类型不支持提前终止", response.json()["detail"])


def test_backfill_attachments_task_should_return_404_when_source_missing(self):
    self._login()
    with patch(
        "src.api.admin.ensure_scrape_source_ready",
        side_effect=admin_api.ScrapeSourceError("数据源不存在", 404),
    ):
        response = self.client.post(
            "/api/admin/backfill-attachments",
            json={"source_id": 999, "limit": 50},
        )

    self.assertEqual(response.status_code, 404)
    self.assertIn("数据源不存在", response.json()["detail"])


def test_run_job_extraction_task_should_return_409_when_source_inactive(self):
    self._login()
    with patch(
        "src.api.admin.ensure_scrape_source_ready",
        side_effect=admin_api.ScrapeSourceError("数据源已停用，不能启动抓取任务", 409),
    ):
        response = self.client.post(
            "/api/admin/run-job-extraction",
            json={"source_id": 9, "limit": 5, "only_unindexed": True, "use_ai": False},
        )

    self.assertEqual(response.status_code, 409)
    self.assertIn("数据源已停用", response.json()["detail"])
```

在 `frontend/tests/adminDashboardTaskActions.test.mjs` 中补前端兜底过滤，防止后端旧快照把不支持的 cancel 重新暴露出来：

```javascript
test('getTaskActionDefinitions should drop unsupported backend cancel action for scrape tasks', () => {
  const actions = getTaskActionDefinitions({
    task_type: 'manual_scrape',
    status: 'running',
    actions: [{ key: 'cancel', label: '提前终止' }]
  })

  assert.deepEqual(actions, [])
})
```

- [ ] **Step 2: 跑任务取消与 source 校验的定向测试，确认先失败**

Run:

```bash
python -m unittest tests.test_admin_task_service tests.test_admin_api -v
cd frontend && node --test tests/adminDashboardTaskActions.test.mjs
```

Expected:
- FAIL
- `request_task_run_cancel()` 还不会拒绝 scrape 任务
- `backfill-base-analysis` / `backfill-attachments` / `run-job-extraction` 还不会按各自真实语义做 source 校验
- 前端会盲信 backend `actions`

- [ ] **Step 3: 在服务层限制 cancel，并在管理入口按真实语义收口 source 校验**

先在 `src/services/admin_task_service.py` 明确“不支持取消”不是运行态错误，而是能力边界：

```python
def request_task_run_cancel(
    task_id: str,
    *,
    cancel_reason: str = "user_requested",
    cancel_requested_by: str | None = None,
) -> Dict[str, Any]:
    with TASK_RUNS_LOCK:
        current_runs = _load_task_runs_with_cleanup()
        next_runs: List[Dict[str, Any]] = []
        updated_run: Dict[str, Any] | None = None

        for task_run in current_runs:
            if task_run.get("id") != task_id or updated_run is not None:
                next_runs.append(task_run)
                continue

            current_status = normalize_task_status(task_run.get("status"))
            if not _is_running_task_status(current_status):
                raise ValueError("task_not_running")
            if task_run.get("task_type") not in TASK_CANCELABLE_TYPES:
                raise ValueError("task_not_cancelable")

            merged_details = dict(task_run.get("details") or {})
            if not merged_details.get("cancel_requested_at"):
                merged_details["cancel_requested_at"] = datetime.now(timezone.utc).isoformat()
            merged_details["cancel_reason"] = cancel_reason
            if cancel_requested_by:
                merged_details["cancel_requested_by"] = cancel_requested_by

            cancel_stage_label = (
                "任务尚未开始，启动前会直接停止"
                if current_status == "queued"
                else "当前处理单元结束后会停止"
            )
            merged_details["stage"] = "finalizing"
            merged_details["stage_label"] = cancel_stage_label
            merged_details["stage_started_at"] = merged_details.get("cancel_requested_at")

            updated_run = {
                **task_run,
                "status": "cancel_requested",
                "phase": cancel_stage_label,
                "details": merged_details,
                "heartbeat_at": datetime.now(timezone.utc).isoformat(),
            }
            next_runs.append(updated_run)
```

再在 `src/api/admin.py` 加轻量 helper，但不要把所有补处理都错误地收成和抓取完全同一套 readiness：

- `backfill-attachments` 仍要求 source 存在且处于 active/ready 状态
- `backfill-base-analysis`、`run-job-extraction` 只要求 source 存在，允许对已停用 source 的历史记录继续补处理

可以拆成两个 helper：

```python
def _ensure_optional_source_exists(db: Session, source_id: int | None) -> None:
    if source_id is None:
        return
    source = db.query(Source).filter(Source.id == source_id).first()
    if source is None:
        raise HTTPException(status_code=404, detail="数据源不存在")


def _ensure_optional_source_ready(db: Session, source_id: int | None) -> None:
    if source_id is None:
        return
    try:
        ensure_scrape_source_ready(db, source_id)
    except ScrapeSourceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
```

把它接到这些入口顶部：

```python
@protected_router.post("/backfill-base-analysis", status_code=202)
async def backfill_base_analysis_task(
    request: BackfillBaseAnalysisRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    _ensure_optional_source_exists(db, request.source_id)
    params = {
        "source_id": request.source_id,
        "limit": request.limit,
        "only_pending": request.only_pending,
        "rerun_of_task_id": request.rerun_of_task_id,
    }
    running_task = _start_task_or_raise_conflict(
        task_type="base_analysis_backfill",
        summary="基础分析补齐进行中",
        params=params,
        conflict_task_types=CONTENT_MUTATION_TASK_TYPES,
    )
    background_tasks.add_task(
        _run_base_analysis_in_background,
        running_task["id"],
        running_task.get("started_at"),
        params,
    )


@protected_router.post("/backfill-attachments", status_code=202)
async def backfill_attachments_task(
    request: BackfillAttachmentsRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    _ensure_optional_source_ready(db, request.source_id)
    params = {
        "source_id": request.source_id,
        "limit": request.limit,
        "rerun_of_task_id": request.rerun_of_task_id,
    }
    running_task = _start_task_or_raise_conflict(
        task_type="attachment_backfill",
        summary="历史附件补处理中",
        params=params,
        conflict_task_types=CONTENT_MUTATION_TASK_TYPES,
    )
    background_tasks.add_task(
        _run_attachment_backfill_in_background,
        running_task["id"],
        running_task.get("started_at"),
        params,
    )


@protected_router.post("/run-job-extraction", status_code=202)
async def run_job_extraction_task(
    request: RunJobExtractionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    _ensure_optional_source_exists(db, request.source_id)
    resolved_only_unindexed = request.only_unindexed
    if resolved_only_unindexed is None:
        resolved_only_unindexed = request.only_pending if request.only_pending is not None else True
    params = {
        "source_id": request.source_id,
        "limit": request.limit,
        "only_unindexed": resolved_only_unindexed,
        "use_ai": request.use_ai,
        "rerun_of_task_id": request.rerun_of_task_id,
    }
    task_copy = _get_job_extraction_runtime_copy(request.use_ai)
    running_task = _start_task_or_raise_conflict(
        task_type=task_copy["task_type"],
        summary=task_copy["running_summary"],
        params=params,
        conflict_task_types=CONTENT_MUTATION_TASK_TYPES,
    )
    background_tasks.add_task(
        _run_job_extraction_in_background,
        running_task["id"],
        running_task.get("started_at"),
        params,
    )
```

取消接口对 `task_not_cancelable` 明确给 409：

```python
@protected_router.post("/task-runs/{task_id}/cancel", status_code=202)
async def cancel_task_run(task_id: str):
    try:
        task_run = request_task_run_cancel(
            task_id,
            cancel_reason="user_requested",
            cancel_requested_by="admin",
        )
    except ValueError as exc:
        if str(exc) == "task_not_cancelable":
            raise HTTPException(status_code=409, detail="当前任务类型不支持提前终止") from exc
        if str(exc) == "task_not_running":
            raise HTTPException(status_code=409, detail="当前任务已经结束，不能再终止") from exc
        raise HTTPException(status_code=404, detail="任务记录不存在") from exc
```

最后在 `frontend/src/views/admin/adminDashboardTaskActions.js` 过滤掉不应信任的 backend cancel：

```javascript
const getBackendActionDefinitions = (run = {}) => {
  const taskType = run?.task_type || run?.taskType
  if (!Array.isArray(run.actions)) return []
  return run.actions
    .filter((action) => action?.key !== 'cancel' || CANCELABLE_TASK_TYPES.has(taskType))
    .map((action) => resolveActionDefinition(taskType, action?.key, action?.label))
    .filter(Boolean)
}
```

- [ ] **Step 4: 再跑定向测试**

Run:

```bash
python -m unittest tests.test_admin_task_service tests.test_admin_api -v
cd frontend && node --test tests/adminDashboardTaskActions.test.mjs
```

Expected:
- PASS
- scrape 任务 cancel 不再是“看起来能点、其实做不到”的伪能力
- 维护入口遇到无效 `source_id` 时返回明确错误，而不是 0-count success
- 前端即使收到旧 backend 快照，也不会为 scrape 任务渲染 cancel

- [ ] **Step 5: 提交任务契约和入口校验修正**

```bash
git add src/services/admin_task_service.py src/api/admin.py frontend/src/views/admin/adminDashboardTaskActions.js tests/test_admin_task_service.py tests/test_admin_api.py frontend/tests/adminDashboardTaskActions.test.mjs
git commit -m "fix: 收口后台任务取消契约并统一数据源校验"
```

### Task 3: 用 ui-ux-pro-max 收口管理台失败态、表单可访问性和动态提示语义

**Files:**
- Modify: `frontend/src/views/admin/useAdminDashboardState.js`
- Modify: `frontend/src/views/admin/adminDashboardDataService.js`
- Modify: `frontend/src/views/admin/adminDashboardSectionAdapters.js`
- Modify: `frontend/src/views/admin/sections/AdminSystemSection.vue`
- Modify: `frontend/src/views/admin/sections/AdminTaskRunsSection.vue`
- Modify: `frontend/src/views/AdminDashboard.vue`
- Modify: `frontend/src/components/ui/AppNotice.vue`
- Test: `frontend/tests/adminDashboardDataService.test.mjs`
- Test: `frontend/tests/adminDashboardStateBindings.test.mjs`
- Test: `frontend/tests/adminDashboardSharedUi.test.mjs`
- Test: `frontend/tests/adminDashboardTaskCardsUi.test.mjs`

- [ ] **Step 1: 先补管理台真实失败态与 a11y 回归测试**

在 `frontend/tests/adminDashboardDataService.test.mjs` 中补“任务记录加载失败”和“scheduler 未成功加载时禁止保存”：

```javascript
test('fetchTaskRuns should preserve load failure separately from empty state', async () => {
  const taskRunsError = new Error('task-runs-failed')
  taskRunsError.response = { status: 500, data: { detail: '加载任务记录失败' } }

  const { service, state, loaded, feedback } = createHarness({
    adminApiOverrides: {
      getTaskRuns: async () => { throw taskRunsError }
    }
  })

  const result = await service.fetchTaskRuns()

  assert.equal(result, false)
  assert.equal(loaded.taskRuns, false)
  assert.deepEqual(state.taskRuns, [])
  assert.equal(state.taskRunsError, '加载任务记录失败')
  assert.equal(feedback.value.type, 'error')
})


test('saveSchedulerConfig should refuse submit until scheduler config loads successfully', async () => {
  let receivedPayload = null
  const { service, feedback } = createHarness({
    adminApiOverrides: {
      updateSchedulerConfig: async (payload) => {
        receivedPayload = payload
        return { data: { message: '定时抓取配置已更新', config: payload } }
      }
    }
  })

  await service.saveSchedulerConfig()

  assert.equal(receivedPayload, null)
  assert.equal(feedback.value.type, 'warning')
  assert.match(feedback.value.message, /重新加载后才能保存/)
})
```

在 `frontend/tests/adminDashboardStateBindings.test.mjs` 中补缺失 import 的静态兜底：

```javascript
import { readFileSync } from 'node:fs'

const readSource = (relativePath) => readFileSync(new URL(`../src/${relativePath}`, import.meta.url), 'utf8')

test('useAdminDashboardState should import isRunningTaskStatus for active task aggregation', () => {
  const source = readSource('views/admin/useAdminDashboardState.js')

  assert.match(source, /isRunningTaskStatus/)
  assert.match(source, /from '..\/..\/utils\/adminTaskSnapshots\.js'/)
})
```

在 `frontend/tests/adminDashboardSharedUi.test.mjs` 和 `frontend/tests/adminDashboardTaskCardsUi.test.mjs` 里补组件分支与语义断言：

```javascript
test('admin system section should disable save until scheduler config is loaded', () => {
  const source = readSource('views/admin/sections/AdminSystemSection.vue')

  assert.match(source, /:disabled="saveDisabled"/)
  assert.match(source, /saveBlockedReason/)
  assert.match(source, /for="scheduler-default-source"/)
  assert.match(source, /id="scheduler-default-source"/)
})


test('admin task runs section should render failure notice before empty state', () => {
  const source = readSource('views/admin/sections/AdminTaskRunsSection.vue')

  assert.match(source, /v-else-if="taskRunsError"/)
  assert.match(source, /title="任务记录暂时不可用"/)
  assert.match(source, /@click="refreshTaskStatus"/)
})


test('AppNotice should expose opt-in live region semantics for dynamic feedback', () => {
  const source = readSource('components/ui/AppNotice.vue')

  assert.match(source, /announce/)
  assert.match(source, /:role=/)
  assert.match(source, /:aria-live=/)
  assert.match(source, /aria-atomic/)
})
```

- [ ] **Step 2: 跑管理台定向测试，确认新增断言先失败**

Run:

```bash
cd frontend && node --test tests/adminDashboardDataService.test.mjs tests/adminDashboardStateBindings.test.mjs tests/adminDashboardSharedUi.test.mjs tests/adminDashboardTaskCardsUi.test.mjs
```

Expected:
- FAIL
- `useAdminDashboardState.js` 还没导入 `isRunningTaskStatus`
- `fetchTaskRuns()` 失败后不会保留独立错误状态
- `saveSchedulerConfig()` 还会在 `loaded.scheduler === false` 时直接发请求
- `AppNotice` 还没有 live region 语义
- `AdminSystemSection` 标签还是纯视觉文本，未做 `for/id` 绑定

- [ ] **Step 3: 在状态层分离失败态，并按 ui-ux-pro-max 给出明确恢复路径**

先在 `frontend/src/views/admin/useAdminDashboardState.js` 的初始状态里把失败态字段补齐，并修掉缺失 import：

```javascript
import {
  isRunningTaskStatus
} from '../../utils/adminTaskSnapshots.js'

const state = reactive({
  taskRuns: [],
  taskRunsError: '',
  taskSummary: null,
  taskSummaryUnavailable: false,
  analysisSummary: null,
  insightSummary: null,
  jobSummary: null,
  duplicateSummary: null,
  expandedTaskIds: [],
  retryingTaskId: '',
  retryingTaskActionKey: '',
  cancelingTaskId: '',
  pollingInFlight: false,
  pollingTimerId: null,
  nowTs: Date.now(),
  jobsSummaryUnavailable: false,
  taskStatusLastSyncedAt: '',
  schedulerConfigError: '',
})
```

在 `frontend/src/views/admin/adminDashboardDataService.js` 中分开“空数据”和“加载失败”：

```javascript
const clearAdminRuntimeState = () => {
  runtimeGeneration += 1
  Object.assign(state, {
    taskRuns: [],
    taskRunsError: '',
    taskSummary: null,
    taskSummaryUnavailable: false,
    analysisSummary: null,
    insightSummary: null,
    jobSummary: null,
    duplicateSummary: null,
    expandedTaskIds: [],
    retryingTaskId: '',
    retryingTaskActionKey: '',
    cancelingTaskId: '',
    jobsSummaryUnavailable: false,
    taskStatusLastSyncedAt: '',
    schedulerConfigError: '',
  })
  Object.keys(loaded).forEach((key) => { loaded[key] = false })
  Object.keys(requests).forEach((key) => { requests[key] = false })
  sourceOptions.value = []
  resetTaskForms()
}

const fetchTaskRuns = async ({ isCurrentRequest = () => true } = {}) => {
  const isCurrent = createRequestGuard('taskRuns', isCurrentRequest)
  loading.taskRuns = true
  try {
    const response = await adminApi.getTaskRuns({ limit: 10 })
    if (!isCurrent()) return getCurrentTaskRunsResult()
    state.taskRuns = (response.data.items || []).map((run) => normalizeAdminTaskSnapshot(run))
    state.taskRunsError = ''
    loaded.taskRuns = true
    return true
  } catch (error) {
    if (!isCurrent()) return getCurrentTaskRunsResult()
    state.taskRuns = []
    state.taskRunsError = getErrorMessage(error, '加载任务记录失败')
    loaded.taskRuns = false
    if (!handleAdminAccessError(error)) setFeedback('error', state.taskRunsError)
    return false
  } finally {
    if (isCurrent()) loading.taskRuns = false
  }
}

const fetchSchedulerConfig = async ({ isCurrentRequest = () => true } = {}) => {
  const isCurrent = createRequestGuard('scheduler', isCurrentRequest)
  loading.scheduler = true
  try {
    const response = await adminApi.getSchedulerConfig()
    if (!isCurrent()) return loaded.scheduler === true
    applySchedulerConfig(response.data || {})
    state.schedulerConfigError = ''
    loaded.scheduler = true
    return true
  } catch (error) {
    if (!isCurrent()) return loaded.scheduler === true
    state.schedulerConfigError = getErrorMessage(error, '加载定时抓取配置失败')
    loaded.scheduler = false
    if (!handleAdminAccessError(error)) setFeedback('error', state.schedulerConfigError)
    return false
  } finally {
    if (isCurrent()) loading.scheduler = false
  }
}

const saveSchedulerConfig = async () => {
  if (!loaded.scheduler) {
    setFeedback('warning', '定时抓取配置尚未成功加载，请先刷新配置后再保存。')
    return
  }
  loading.schedulerSaving = true
  try {
    const payload = removeUndefinedFields({
      enabled: forms.scheduler.enabled,
      interval_seconds: toMinimumNumber(forms.scheduler.intervalSeconds, 7200, 60),
      default_source_id: toOptionalSourceIdForPayload(forms.scheduler.defaultSourceId),
      default_max_pages: toMinimumNumber(forms.scheduler.defaultMaxPages, 5, 1)
    })
    const response = await adminApi.updateSchedulerConfig(payload)
    applySchedulerConfig(response.data?.config || payload)
    state.schedulerConfigError = ''
    loaded.scheduler = true
    setFeedback('success', response.data?.message || '定时抓取配置已更新')
  } catch (error) {
    if (!handleAdminAccessError(error)) setFeedback('error', getErrorMessage(error, '保存定时抓取配置失败'))
  } finally {
    loading.schedulerSaving = false
  }
}
```

把失败态透传到 section model：

```javascript
export function buildSystemSectionModel({
  schedulerForm,
  schedulerLoaded,
  schedulerLoading,
  schedulerSaving,
  schedulerConfigError,
  sourceOptions
} = {}) {
  const noticeClass = schedulerLoaded
    ? (schedulerForm?.enabled ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-gray-200 bg-gray-50 text-gray-700')
    : 'border-slate-200 bg-slate-50 text-slate-700'
  const statusBadgeLabel = showBoolean(schedulerLoaded, schedulerForm?.enabled, '自动抓取已启用', '自动抓取已关闭')
  const summaryCards = [
    {
      label: '当前状态',
      value: showBoolean(schedulerLoaded, schedulerForm?.enabled, '已启用', '已关闭'),
      meta: schedulerLoaded ? `间隔 ${formatAdminInterval(schedulerForm?.intervalSeconds)}` : LOADING_LABEL
    },
    {
      label: '下次运行',
      value: showText(
        schedulerLoaded,
        schedulerForm?.nextRunAt ? formatAdminDateTime(schedulerForm.nextRunAt) : '',
        NOT_FETCHED_LABEL
      ),
      meta: schedulerLoaded ? '如需立即处理，可直接去“处理任务”手动运行。' : LOADING_LABEL
    },
    {
      label: '默认范围',
      value: schedulerLoaded
        ? `${getSourceLabel(sourceOptions, schedulerForm?.defaultSourceId)} · ${showCount(true, schedulerForm?.defaultMaxPages)} 页`
        : LOADING_LABEL,
      meta: '新的默认设置会用于后续自动抓取。'
    }
  ]
  const helperNotice = {
    tone: schedulerForm?.enabled ? 'info' : 'warning',
    description: schedulerForm?.enabled
      ? '保存后会在下一次自动抓取时生效；手动运行任务不受影响。'
      : '当前已关闭自动抓取；保存后会更新后台设置，手动运行任务不受影响。'
  }
  const saveDisabled = !schedulerLoaded || schedulerLoading || schedulerSaving
  const saveBlockedReason = schedulerLoaded
    ? ''
    : (schedulerConfigError || '配置尚未加载成功，请先刷新配置。')

  return {
    schedulerForm,
    schedulerLoaded,
    schedulerLoading,
    schedulerSaving,
    schedulerConfigError,
    saveDisabled,
    saveBlockedReason,
    sourceOptions,
    noticeClass,
    statusBadgeLabel,
    summaryCards,
    helperNotice,
    statusLine: `当前状态：${showBoolean(schedulerLoaded, schedulerForm?.enabled, '已启用定时抓取', '已停用定时抓取')}；间隔 ${schedulerLoaded ? formatAdminInterval(schedulerForm?.intervalSeconds) : LOADING_LABEL}；默认抓 ${showCount(schedulerLoaded, schedulerForm?.defaultMaxPages)} 页。`,
    nextRunLine: `下次预计运行：${showText(schedulerLoaded, schedulerForm?.nextRunAt ? formatAdminDateTime(schedulerForm.nextRunAt) : '', NOT_FETCHED_LABEL)}`,
  }
}

export const buildTaskRunsSectionModel = ({
  taskRuns,
  taskRunsLoaded,
  taskRunsError,
  loadingRuns,
  retryingTaskId,
  retryingTaskActionKey,
  cancelingTaskId,
  expandedTaskIds,
  nowTs,
  sourceOptions,
  heartbeatStaleMs,
  syncStatus,
} = {}) => ({
  taskRuns,
  taskRunsLoaded,
  taskRunsError,
  loadingRuns,
  retryingTaskId,
  retryingTaskActionKey,
  cancelingTaskId,
  expandedTaskIds,
  nowTs,
  sourceOptions,
  heartbeatStaleMs,
  syncStatus,
})
```

`useAdminDashboardState.js` 对应透传：

```javascript
const syncStatus = taskSyncStatus.value

const systemSection = computed(() => buildSystemSectionModel({
  schedulerForm: forms.scheduler,
  schedulerLoaded: loaded.scheduler,
  schedulerLoading: loading.scheduler,
  schedulerSaving: loading.schedulerSaving,
  schedulerConfigError: state.schedulerConfigError,
  sourceOptions: sourceOptions.value,
}))

return buildTaskRunsSectionModel({
  taskRuns: state.taskRuns,
  taskRunsLoaded: loaded.taskRuns,
  taskRunsError: state.taskRunsError,
  loadingRuns: loading.taskRuns,
  retryingTaskId: state.retryingTaskId,
  retryingTaskActionKey: state.retryingTaskActionKey,
  cancelingTaskId: state.cancelingTaskId,
  expandedTaskIds: state.expandedTaskIds,
  nowTs: state.nowTs,
  sourceOptions: sourceOptions.value,
  heartbeatStaleMs: TASK_HEARTBEAT_STALE_MS,
  syncStatus,
})
```

- [ ] **Step 4: 用 AppNotice live region 和可关联 labels 收口组件层**

`frontend/src/components/ui/AppNotice.vue` 做成“可选择进入 live region”的基础组件，而不是所有 notice 都强播报：

```vue
<template>
  <section
    class="app-notice"
    :class="panelClass"
    :role="resolvedRole"
    :aria-live="resolvedAriaLive"
    :aria-atomic="announce ? 'true' : undefined"
  >
    <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div>
        <div v-if="title" class="text-sm font-semibold">
          {{ title }}
        </div>
        <p class="text-sm leading-6" :class="bodyClass">
          {{ description }}
        </p>
      </div>
      <div v-if="$slots.actions" class="shrink-0">
        <slot name="actions" />
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  tone: { type: String, default: 'info' },
  title: { type: String, default: '' },
  description: { type: String, required: true },
  announce: { type: Boolean, default: false },
  live: { type: String, default: '' }
})

const resolvedRole = computed(() => {
  if (!props.announce) return undefined
  if (props.live === 'assertive' || ['danger', 'warning'].includes(props.tone)) return 'alert'
  return 'status'
})

const resolvedAriaLive = computed(() => {
  if (!props.announce) return undefined
  if (props.live) return props.live
  return ['danger', 'warning'].includes(props.tone) ? 'assertive' : 'polite'
})
</script>
```

`frontend/src/views/AdminDashboard.vue` 的动态反馈 notice 改为显式播报：

```vue
<AppNotice
  v-if="dashboard.feedback.message"
  :tone="dashboard.feedback.type === 'success' ? 'success' : (dashboard.feedback.type === 'warning' ? 'warning' : 'danger')"
  title="后台反馈"
  :description="dashboard.feedback.message"
  :announce="true"
/>
```

`frontend/src/views/admin/sections/AdminSystemSection.vue` 用 `saveDisabled/saveBlockedReason`，并补齐 label 关联：

```vue
<label for="scheduler-default-source" class="mb-2 block text-sm font-medium text-gray-700">默认数据源</label>
<select id="scheduler-default-source" v-model.number="schedulerForm.defaultSourceId" class="app-select">
  <option v-for="source in sourceOptions" :key="`scheduler-${source.value}`" :value="source.value">
    {{ source.label }}
  </option>
</select>

<label for="scheduler-interval-seconds" class="mb-2 block text-sm font-medium text-gray-700">抓取间隔（秒）</label>
<input id="scheduler-interval-seconds" v-model.number="schedulerForm.intervalSeconds" type="number" min="60" max="86400" class="app-input">

<label for="scheduler-default-max-pages" class="mb-2 block text-sm font-medium text-gray-700">默认抓取页数</label>
<input id="scheduler-default-max-pages" v-model.number="schedulerForm.defaultMaxPages" type="number" min="1" max="50" class="app-input">

<input id="scheduler-enabled" v-model="schedulerForm.enabled" type="checkbox" class="app-checkbox">
<label for="scheduler-enabled" class="ml-2">启用定时抓取</label>

<AppNotice
  v-if="saveBlockedReason"
  class="mt-4"
  tone="warning"
  title="暂时不能保存"
  :description="saveBlockedReason"
  :announce="true"
/>

<AppActionButton
  label="保存配置"
  busy-label="保存中..."
  :busy="schedulerSaving"
  :disabled="saveDisabled"
  variant="primary"
  @click="saveSchedulerConfig"
/>
```

`frontend/src/views/admin/sections/AdminTaskRunsSection.vue` 把失败态放在空态前，并提供恢复动作：

```vue
<div v-if="loadingRuns && !taskRunsLoaded" class="py-10 text-center text-sm text-gray-500">正在加载任务记录...</div>
<AppNotice
  v-else-if="taskRunsError"
  tone="danger"
  title="任务记录暂时不可用"
  :description="taskRunsError"
  :announce="true"
>
  <template #actions>
    <AppActionButton
      label="重新加载"
      busy-label="刷新中..."
      :busy="loadingRuns"
      variant="amber"
      size="sm"
      @click="refreshTaskStatus"
    />
  </template>
</AppNotice>
<AppEmptyState
  v-else-if="taskRuns.length === 0"
  title="还没有任务记录"
  description="先运行一次任务，这里会按当前记录展示进度和结果。"
/>
```

- [ ] **Step 5: 再跑管理台定向测试并提交 UI 收口**

Run:

```bash
cd frontend && node --test tests/adminDashboardDataService.test.mjs tests/adminDashboardStateBindings.test.mjs tests/adminDashboardSharedUi.test.mjs tests/adminDashboardTaskCardsUi.test.mjs
```

Expected:
- PASS
- `useAdminDashboardState.js` 活跃任务路径不再有真实运行时缺失 import
- scheduler 配置加载失败时，保存按钮被禁用，且文案说明要先刷新
- task runs 失败态与空态彻底分开
- `AppNotice` 只对动态反馈进入 live region，静态说明不被强播报
- 管理台表单具备程序化 label 关联

提交：

```bash
git add frontend/src/views/admin/useAdminDashboardState.js frontend/src/views/admin/adminDashboardDataService.js frontend/src/views/admin/adminDashboardSectionAdapters.js frontend/src/views/admin/sections/AdminSystemSection.vue frontend/src/views/admin/sections/AdminTaskRunsSection.vue frontend/src/views/AdminDashboard.vue frontend/src/components/ui/AppNotice.vue frontend/tests/adminDashboardDataService.test.mjs frontend/tests/adminDashboardStateBindings.test.mjs frontend/tests/adminDashboardSharedUi.test.mjs frontend/tests/adminDashboardTaskCardsUi.test.mjs
git commit -m "fix: 收口管理台失败态与动态反馈可访问性"
```

### Task 4: 收口公开列表/详情页的恢复路径并解除公告类型筛选自锁

**Files:**
- Modify: `frontend/src/utils/postFilters.js`
- Modify: `frontend/src/views/post-list/usePostListState.js`
- Modify: `frontend/src/views/post-detail/usePostDetailState.js`
- Modify: `frontend/src/views/PostList.vue`
- Modify: `frontend/src/views/PostDetail.vue`
- Test: `frontend/tests/postFilters.test.mjs`
- Test: `frontend/tests/postListCopy.test.mjs`
- Test: `frontend/tests/postDetailPresentation.test.mjs`

- [ ] **Step 1: 先补公开页恢复与筛选解锁测试**

在 `frontend/tests/postFilters.test.mjs` 中补“生成公告类型选项请求时不带当前 event_type”：

```javascript
import {
  buildStatsParams,
  buildEventTypeOptionParams,
  DEFAULT_COUNSELOR_SCOPE
} from '../src/utils/postFilters.js'

test('buildEventTypeOptionParams should omit current event_type while preserving other filters', () => {
  const params = buildEventTypeOptionParams({
    days: 7,
    searchQuery: '南京大学',
    filters: {
      gender: '',
      education: '',
      location: '南京',
      eventType: '招聘公告',
      counselorScope: 'dedicated',
      hasContent: true
    },
    defaultCounselorScope: DEFAULT_COUNSELOR_SCOPE
  })

  assert.equal(params.days, 7)
  assert.equal(params.search, '南京大学')
  assert.equal(params.location, '南京')
  assert.equal(params.has_content, true)
  assert.equal(params.counselor_scope, 'dedicated')
  assert.equal(params.is_counselor, true)
  assert.equal('event_type' in params, false)
})
```

在 `frontend/tests/postListCopy.test.mjs` 中补错误恢复动作的 source test：

```javascript
test('PostList error notice should provide recovery actions beyond reload', () => {
  const source = readSource('views/PostList.vue')

  assert.match(source, /title="招聘列表暂时无法显示"/)
  assert.match(source, /返回上一页/)
  assert.match(source, /回到第一页/)
  assert.match(source, /清空条件/)
  assert.match(source, /重新加载/)
})
```

在 `frontend/tests/postDetailPresentation.test.mjs` 中补详情页确定性返回：

```javascript
test('PostDetail should return to the list route deterministically instead of using browser history length', () => {
  const source = readSource('views/PostDetail.vue')

  assert.match(source, /router\.push\(\s*\{\s*name: 'PostList'/)
  assert.doesNotMatch(source, /window\.history\.length/)
  assert.match(source, /返回列表/)
})
```

- [ ] **Step 2: 跑公开页定向测试，确认新断言先失败**

Run:

```bash
cd frontend && node --test tests/postFilters.test.mjs tests/postListCopy.test.mjs tests/postDetailPresentation.test.mjs
```

Expected:
- FAIL
- `postFilters.js` 还没有不带 `event_type` 的 stats 参数构造
- `PostList.vue` 失败态还只有“重新加载”
- `PostDetail.vue` 仍然依赖 `window.history.length`

- [ ] **Step 3: 先把公告类型统计请求和详情状态改成可恢复的纯逻辑**

在 `frontend/src/utils/postFilters.js` 增加专门给 event type 选项用的参数构造函数，不改现有 `buildStatsParams()` 语义：

```javascript
export const buildEventTypeOptionParams = ({
  days = 7,
  searchQuery = '',
  filters = {},
  defaultCounselorScope = DEFAULT_COUNSELOR_SCOPE
} = {}) => {
  return buildStatsParams({
    days,
    searchQuery,
    filters: {
      ...filters,
      eventType: ''
    },
    defaultCounselorScope
  })
}
```

在 `frontend/src/views/post-list/usePostListState.js` 里把 stats 请求改成不带当前 event type，并把当前选择补回 option 列表，防止 select 瞬间掉值：

```javascript
import {
  DEFAULT_COUNSELOR_SCOPE,
  buildPostParams as buildPostRequestParams,
  buildStatsParams as buildStatsRequestParams,
  buildEventTypeOptionParams
} from '../../utils/postFilters.js'

const mergeEventTypeOptions = (items = [], selectedValue = '') => {
  const normalizedSelected = String(selectedValue || '').trim()
  const normalizedItems = Array.isArray(items) ? items : []
  if (!normalizedSelected) return normalizedItems
  if (normalizedItems.some((item) => item?.event_type === normalizedSelected)) return normalizedItems
  return [{ event_type: normalizedSelected, count: 0 }, ...normalizedItems]
}

const fetchStatsSummary = async () => {
  const requestId = ++statsRequestSeq

  try {
    const response = await postsApi.getStatsSummary(buildEventTypeOptionParams({
      days: 7,
      searchQuery: searchQuery.value,
      filters: filters.value,
      defaultCounselorScope: DEFAULT_COUNSELOR_SCOPE
    }))
    if (requestId !== statsRequestSeq) return
    eventTypeOptions.value = mergeEventTypeOptions(
      response?.data?.event_type_distribution || [],
      filters.value.eventType
    )
  } catch (requestError) {
    if (requestId !== statsRequestSeq) return
    console.warn('获取筛选项摘要失败:', requestError)
  }
}
```

在 `frontend/src/views/post-detail/usePostDetailState.js` 里补 `errorStatus`，让组件按 404/非 404 分开恢复动作：

```javascript
const errorStatus = ref(0)

async function fetchPostDetail() {
  const requestId = ++detailRequestSeq
  loading.value = true
  error.value = ''
  errorStatus.value = 0

  try {
    const response = await postsApi.getPostById(route.params.id)
    if (requestId !== detailRequestSeq) return
    post.value = response.data || null
    void fetchLatestSuccessTask(response?.data?.source?.id || null)
  } catch (requestError) {
    if (requestId !== detailRequestSeq) return
    post.value = null
    latestSuccessTask.value = null
    freshnessUnavailable.value = false
    errorStatus.value = requestError?.response?.status || 0
    error.value = getErrorMessage(requestError)
  } finally {
    if (requestId === detailRequestSeq) {
      loading.value = false
    }
  }
}

return {
  post,
  loading,
  error,
  errorStatus,
  latestSuccessTask,
  freshnessLoading,
  freshnessUnavailable,
  fetchPostDetail,
  fetchLatestSuccessTask,
}
```

- [ ] **Step 4: 用 ui-ux-pro-max 的“错误必须给下一步”原则收口列表和详情组件**

`frontend/src/views/PostList.vue` 的错误态改成带恢复动作的 `AppNotice`，并显式播报：

```vue
<AppNotice
  v-else-if="error"
  tone="danger"
  title="招聘列表暂时无法显示"
  :description="error"
  :announce="true"
>
  <template #actions>
    <button
      v-if="currentPage > 1"
      type="button"
      class="app-button app-button--sm app-button--secondary"
      @click="goToPage(currentPage - 1)"
    >
      返回上一页
    </button>
    <button
      v-if="currentPage > 1"
      type="button"
      class="app-button app-button--sm app-button--secondary"
      @click="goToPage(1)"
    >
      回到第一页
    </button>
    <button
      v-if="hasQueryOrFilters"
      type="button"
      class="app-button app-button--sm app-button--secondary"
      @click="clearFilters"
    >
      清空条件
    </button>
    <button
      type="button"
      class="app-button app-button--sm app-button--warning"
      @click="fetchPosts"
    >
      重新加载
    </button>
  </template>
</AppNotice>
```

`frontend/src/views/PostDetail.vue` 去掉历史长度猜测，统一回到列表路由，并把 404 恢复动作单独做出来：

```vue
<AppNotice
  v-else-if="error"
  tone="danger"
  title="招聘详情暂时无法显示"
  :description="error"
  :announce="true"
>
  <template #actions>
    <button
      type="button"
      class="app-button app-button--sm app-button--secondary"
      @click="returnToList"
    >
      返回列表
    </button>
    <button
      v-if="errorStatus !== 404"
      type="button"
      class="app-button app-button--sm app-button--warning"
      @click="fetchPostDetail"
    >
      重新加载
    </button>
  </template>
</AppNotice>
```

脚本部分只保留一个确定性返回函数：

```javascript
const {
  post,
  loading,
  error,
  errorStatus,
  latestSuccessTask,
  freshnessLoading,
  freshnessUnavailable,
  fetchPostDetail
} = usePostDetailState(route)

const returnToList = () => {
  router.push({
    name: 'PostList',
    query: { ...route.query }
  })
}

const goBack = () => {
  returnToList()
}
```

- [ ] **Step 5: 再跑公开页定向测试并提交**

Run:

```bash
cd frontend && node --test tests/postFilters.test.mjs tests/postListCopy.test.mjs tests/postDetailPresentation.test.mjs
```

Expected:
- PASS
- event type 下拉不会再因当前筛选自锁
- 列表错误态不再只给“重新加载”
- 详情页 404 明确提供“返回列表”，返回路径不再依赖浏览器历史长度

提交：

```bash
git add frontend/src/utils/postFilters.js frontend/src/views/post-list/usePostListState.js frontend/src/views/post-detail/usePostDetailState.js frontend/src/views/PostList.vue frontend/src/views/PostDetail.vue frontend/tests/postFilters.test.mjs frontend/tests/postListCopy.test.mjs frontend/tests/postDetailPresentation.test.mjs
git commit -m "fix: 收口公开页恢复路径并解除公告类型筛选自锁"
```

### Task 5: 调整 GHCR 发布顺序并让 smoke 文档自包含

**Files:**
- Modify: `.github/workflows/publish-images.yml`
- Modify: `docs/test-strategy.md`
- Modify: `docs/release-checklist.md`
- Create: `tests/test_release_artifacts.py`

- [ ] **Step 1: 先补 workflow/docs 静态验证**

新建 `tests/test_release_artifacts.py`，用最轻量的静态断言替代本地 Docker smoke：

```python
from pathlib import Path
import unittest


class ReleaseArtifactsTestCase(unittest.TestCase):
    def test_publish_images_should_promote_release_tags_only_after_smoke(self):
        content = Path(".github/workflows/publish-images.yml").read_text(encoding="utf-8")

        smoke_index = content.index("Smoke GHCR compose deployment")
        promote_backend_index = content.index("Promote backend tags after smoke")
        promote_frontend_index = content.index("Promote frontend tags after smoke")
        pre_smoke = content[:smoke_index]

        self.assertIn("IMAGE_TAG: ${{ steps.prep.outputs.sha_tag }}", content)
        self.assertNotIn("value=latest", pre_smoke)
        self.assertLess(smoke_index, promote_backend_index)
        self.assertLess(smoke_index, promote_frontend_index)

    def test_smoke_docs_should_list_required_admin_env_vars(self):
        required_keys = [
            "ADMIN_USERNAME",
            "ADMIN_PASSWORD",
            "ADMIN_SESSION_SECRET",
            "ADMIN_SESSION_SECURE",
            "API_DOCS_ENABLED",
        ]
        for path in ("docs/test-strategy.md", "docs/release-checklist.md"):
            content = Path(path).read_text(encoding="utf-8")
            for key in required_keys:
                self.assertIn(key, content, f"{path} missing {key}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑静态验证，确认先失败**

Run:

```bash
python -m unittest tests.test_release_artifacts -v
```

Expected:
- FAIL
- `publish-images.yml` 现在仍在 smoke 前发布 `latest` / tag
- 文档还没有完整列出 smoke 需要的环境变量

- [ ] **Step 3: 把 workflow 改成“先 sha 候选镜像，smoke 后再 promote 正式标签”**

在 `.github/workflows/publish-images.yml` 中保留 `sha_tag` 作为候选 tag，构建阶段只推这个 tag；smoke 用这个 tag；成功后再 promote：

```yaml
- name: Extract backend image metadata
  id: meta-api
  uses: docker/metadata-action@v5
  with:
    images: ghcr.io/${{ steps.prep.outputs.owner_lc }}/fdy-tracker-api
    tags: |
      type=raw,value=${{ steps.prep.outputs.sha_tag }}

- name: Extract frontend image metadata
  id: meta-web
  uses: docker/metadata-action@v5
  with:
    images: ghcr.io/${{ steps.prep.outputs.owner_lc }}/fdy-tracker-web
    tags: |
      type=raw,value=${{ steps.prep.outputs.sha_tag }}
```

smoke 后增加 promote step：

```yaml
- name: Promote backend tags after smoke
  if: success()
  shell: bash
  run: |
    set -euo pipefail
    backend_ref="ghcr.io/${{ steps.prep.outputs.owner_lc }}/fdy-tracker-api:${{ steps.prep.outputs.sha_tag }}"
    if [[ "${GITHUB_REF}" == "refs/heads/${{ github.event.repository.default_branch }}" ]]; then
      docker buildx imagetools create -t "ghcr.io/${{ steps.prep.outputs.owner_lc }}/fdy-tracker-api:latest" "${backend_ref}"
    fi
    if [[ "${GITHUB_REF}" == refs/tags/* ]]; then
      docker buildx imagetools create -t "ghcr.io/${{ steps.prep.outputs.owner_lc }}/fdy-tracker-api:${GITHUB_REF_NAME}" "${backend_ref}"
    fi

- name: Promote frontend tags after smoke
  if: success()
  shell: bash
  run: |
    set -euo pipefail
    frontend_ref="ghcr.io/${{ steps.prep.outputs.owner_lc }}/fdy-tracker-web:${{ steps.prep.outputs.sha_tag }}"
    if [[ "${GITHUB_REF}" == "refs/heads/${{ github.event.repository.default_branch }}" ]]; then
      docker buildx imagetools create -t "ghcr.io/${{ steps.prep.outputs.owner_lc }}/fdy-tracker-web:latest" "${frontend_ref}"
    fi
    if [[ "${GITHUB_REF}" == refs/tags/* ]]; then
      docker buildx imagetools create -t "ghcr.io/${{ steps.prep.outputs.owner_lc }}/fdy-tracker-web:${GITHUB_REF_NAME}" "${frontend_ref}"
    fi
```

说明：
- 本地没有 Docker，本轮不跑本地 compose smoke。
- 这里的最小门禁是：正式 tag 不得早于 smoke 暴露。

- [ ] **Step 4: 把 smoke 文档改成自包含操作说明**

在 `docs/test-strategy.md` 和 `docs/release-checklist.md` 直接写明 smoke 前提，而不是假设操作者知道 `.env`：

```md
执行 smoke 前，至少确认以下环境变量已通过 `.env` 或 shell 提供：

- `ADMIN_USERNAME=smoke-admin`
- `ADMIN_PASSWORD=smoke-pass`
- `ADMIN_SESSION_SECRET=smoke-session-secret-0123456789abcdefghijkl`
- `ADMIN_SESSION_SECURE=false`（本地 / CI HTTP smoke）
- `API_DOCS_ENABLED=false`

如果是在 VPS 部署后观察：

- 生产公网入口应恢复 `ADMIN_SESSION_SECURE=true`
- `/docs`、`/openapi.json`、`/redoc` 默认保持关闭
```

同时把 release checklist 的 GHCR 条目更新为：

```md
- [ ] `publish-images.yml` 先推送 `sha-*` 候选镜像，再跑 GHCR smoke
- [ ] GHCR smoke 通过后才 promote `latest` / release tag
```

- [ ] **Step 5: 再跑静态验证并提交发布链收口**

Run:

```bash
python -m unittest tests.test_release_artifacts -v
```

Expected:
- PASS
- workflow 不会在 smoke 前暴露正式 tag
- docs 明确列出 smoke 必要环境变量

提交：

```bash
git add .github/workflows/publish-images.yml docs/test-strategy.md docs/release-checklist.md tests/test_release_artifacts.py
git commit -m "fix: 收口镜像发布顺序并补齐 smoke 前置说明"
```

### Task 6: 跑本轮完整验证并确认交付边界

**Files:**
- No code changes expected

- [ ] **Step 1: 跑后端完整回归并导出日志**

Run:

```bash
python -m unittest discover -s tests -v | Tee-Object backend-tests.log
```

Expected:
- PASS
- 新增的 `test_release_artifacts.py`、scheduler readiness、admin cancel/source、health API 回归都通过

- [ ] **Step 2: 扫描后端日志，确保没有危险模式**

Run:

```bash
python scripts/check_ci_logs.py backend-tests.log --label backend-tests
```

Expected:
- PASS
- 不出现 `UNIQUE constraint failed`、`SAWarning`、`Traceback` 等危险模式

- [ ] **Step 3: 跑前端完整测试**

Run:

```bash
cd frontend && npm test
```

Expected:
- PASS
- admin/public 新增定向用例与原有 UI source tests 一起通过

- [ ] **Step 4: 跑前端构建**

Run:

```bash
cd frontend && npm run build
```

Expected:
- PASS
- AppNotice / AdminDashboard / PostList / PostDetail 的改动不影响生产构建

- [ ] **Step 5: 记录本轮明确不做的验证，并输出 VPS 观察项**

本轮不要补做本地 Docker compose smoke，也不要做本地 24h 长跑；在交付说明里显式写：

```md
- 本地未执行 Docker compose smoke：当前机器没有 Docker
- 本地未执行 24h 长跑：按本轮范围延后到 VPS 部署后观察
- VPS 部署后观察项：
  - `/api/health`、首页、`/admin`、后台登录闭环
  - 至少一个定时抓取周期的 `next_run_at`、freshness、任务记录推进
  - GHCR 拉取到的是 smoke 后 promote 的正式 tag
```

## Self-Review Checklist

- Spec coverage:
  - A1 readiness truthfulness -> Task 1
  - A2 fake cancel contract -> Task 2
  - A3 source-scoped validation -> Task 2
  - B1/B2/B3/B4 admin UI reliability + a11y -> Task 3
  - C1/C2/C3 public recovery + filter unlock -> Task 4
  - D1/D2 release/docs closure -> Task 5
  - Final required verification -> Task 6

- Placeholder scan:
  - 无 `TODO` / `TBD` / “自行补充测试”
  - 每个改动步骤都给了具体文件、代码片段和命令

- Type consistency:
  - 后端统一使用 `task_not_cancelable`
  - 前端统一使用 `taskRunsError`、`schedulerConfigError`
  - 详情页统一使用 `errorStatus` 和 `returnToList`
