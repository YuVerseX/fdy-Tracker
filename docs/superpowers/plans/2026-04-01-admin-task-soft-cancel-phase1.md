# 后台任务软取消 Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为后台内容处理类长任务增加协作式软取消能力，让运行中任务可提交“提前终止”，并在安全检查点停止后续处理、保留已完成结果、最终记为 `cancelled`。

**Architecture:** 后端继续以 `admin_task_runs.json` 作为任务事实源，在 `admin_task_service.py` 增加取消请求写入与取消状态序列化；`src/api/admin.py` 增加取消接口、取消检查器和统一的 `cancelled` 落库逻辑；各业务服务只接收 `cancel_check` 并在循环边界调用，不直接依赖任务文件。前端沿用现有任务中心和任务卡结构，只补 `cancel` 动作、取消中的提示和 `cancelled` 状态展示。

**Tech Stack:** FastAPI, SQLAlchemy, asyncio, Vue 3, Axios, unittest, pytest, node:test, Vite

**Status (2026-04-01):** Phase 1 已实现并验证通过。实际覆盖 `attachment_backfill`、`base_analysis_backfill`、`ai_analysis`、`job_extraction`、`duplicate_backfill`；`manual_scrape` / `scheduled_scrape` 仍留待下一轮单独评估。

---

### Task 1: 任务记录层增加取消请求与取消状态

**Files:**
- Modify: `src/services/admin_task_service.py`
- Test: `tests/test_admin_task_service.py`

- [ ] **Step 1: 先补任务记录取消语义测试**

在 `tests/test_admin_task_service.py` 里新增以下失败用例：

```python
def test_request_task_run_cancel_should_mark_running_task(self):
    created = admin_task_service.start_task_run(
        task_type="ai_analysis",
        summary="AI 分析进行中",
        params={"limit": 100},
    )

    cancelled = admin_task_service.request_task_run_cancel(
        task_id=created["id"],
        cancel_reason="user_requested",
        cancel_requested_by="admin",
    )

    self.assertEqual(cancelled["status"], "running")
    self.assertEqual(cancelled["details"]["cancel_reason"], "user_requested")
    self.assertEqual(cancelled["details"]["cancel_requested_by"], "admin")
    self.assertTrue(cancelled["details"]["cancel_requested_at"])

def test_request_task_run_cancel_should_reject_finished_task(self):
    finished = admin_task_service.record_task_run(
        task_type="ai_analysis",
        status="success",
        summary="AI 分析完成",
        details={"progress_mode": "stage_only"},
        params={"limit": 100},
        phase="AI 分析完成",
        progress=100,
    )

    with self.assertRaises(ValueError):
        admin_task_service.request_task_run_cancel(task_id=finished["id"])

def test_serialize_task_run_should_expose_cancelled_status_and_cancel_request_flag(self):
    task_run = admin_task_service.record_task_run(
        task_type="job_extraction",
        status="cancelled",
        summary="用户已提前终止，已处理 4 条，已写入 12 条岗位",
        details={
            "progress_mode": "stage_only",
            "metrics": {"posts_scanned": 4, "jobs_saved": 12},
            "cancel_requested_at": "2026-04-01T10:00:00+00:00",
            "cancel_reason": "user_requested",
        },
        params={"limit": 100, "only_unindexed": True, "use_ai": True},
        phase="已终止",
        progress=100,
    )

    serialized = admin_task_service.serialize_task_run_for_admin(task_run)

    self.assertEqual(serialized["status"], "cancelled")
    self.assertEqual(serialized["status_label"], "已终止")
    self.assertEqual(serialized["details"]["cancel_reason"], "user_requested")
    self.assertEqual(serialized["metrics"]["jobs_saved"], 12)
    self.assertEqual(serialized["actions"][0]["key"], "retry")
```

- [ ] **Step 2: 跑任务记录测试，确认新增用例先失败**

Run: `python -m pytest tests/test_admin_task_service.py`

Expected:
- 新测试失败
- 当前没有 `request_task_run_cancel`
- `cancelled` 还不是合法展示状态

- [ ] **Step 3: 在任务记录服务里补取消能力**

在 `src/services/admin_task_service.py` 中补以下结构：

```python
TASK_STATUS_LABELS = {
    "queued": "排队中",
    "pending": "排队中",
    "running": "执行中",
    "processing": "执行中",
    "success": "完成",
    "failed": "失败",
    "cancelled": "已终止",
}

def request_task_run_cancel(
    task_id: str,
    *,
    cancel_reason: str = "user_requested",
    cancel_requested_by: str | None = None,
) -> Dict[str, Any]:
    with TASK_RUNS_LOCK:
        current_runs = _load_task_runs_with_cleanup()
        next_runs: list[dict[str, Any]] = []
        updated_run: dict[str, Any] | None = None

        for task_run in current_runs:
            if task_run.get("id") != task_id or updated_run is not None:
                next_runs.append(task_run)
                continue

            if task_run.get("status") not in RUNNING_STATUSES:
                raise ValueError("task_not_running")

            merged_details = dict(task_run.get("details") or {})
            merged_details["cancel_requested_at"] = datetime.now(timezone.utc).isoformat()
            merged_details["cancel_reason"] = cancel_reason
            if cancel_requested_by:
                merged_details["cancel_requested_by"] = cancel_requested_by

            updated_run = {
                **task_run,
                "details": merged_details,
                "heartbeat_at": datetime.now(timezone.utc).isoformat(),
            }
            next_runs.append(updated_run)

        if updated_run is None:
            raise ValueError("task_not_found")

        _write_task_runs(next_runs)
        return updated_run

def is_task_run_cancel_requested(task_id: str) -> bool:
    task_run = find_running_task()
    if not task_run or task_run.get("id") != task_id:
        current_runs = load_task_runs(limit=MAX_TASK_RUNS)
        task_run = next((item for item in current_runs if item.get("id") == task_id), None)
    return bool((task_run or {}).get("details", {}).get("cancel_requested_at"))
```

并在 `serialize_task_run_for_admin()` 中兼容取消字段：

```python
compatibility_details["cancel_requested_at"] = raw_details.get("cancel_requested_at")
compatibility_details["cancel_reason"] = raw_details.get("cancel_reason")
compatibility_details["cancel_requested_by"] = raw_details.get("cancel_requested_by")
```

并调整 `build_task_actions()`：

```python
if status in {"failed", "cancelled"}:
    return [{"key": "retry", "label": "按原条件重试"}]
if status == "success":
    return [{"key": "rerun", "label": "再次运行"}]
```

- [ ] **Step 4: 再跑任务记录测试**

Run: `python -m pytest tests/test_admin_task_service.py`

Expected:
- PASS
- `cancelled` 状态能正常序列化
- 运行中任务能写入取消请求

### Task 2: API 层增加取消接口与统一取消异常

**Files:**
- Modify: `src/services/task_progress.py`
- Modify: `src/api/admin.py`
- Test: `tests/test_admin_api.py`

- [ ] **Step 1: 先补 API 取消测试**

在 `tests/test_admin_api.py` 新增以下失败用例：

```python
def test_cancel_task_run_should_return_202_for_running_task(self):
    self._login()
    with patch(
        "src.api.admin.request_task_run_cancel",
        return_value={
            "id": "run-ai-1",
            "task_type": "ai_analysis",
            "status": "running",
            "details": {"cancel_requested_at": "2026-04-01T10:00:00+00:00"},
        },
    ), patch(
        "src.api.admin.serialize_task_run_for_admin",
        return_value={
            "id": "run-ai-1",
            "task_type": "ai_analysis",
            "status": "running",
            "status_label": "执行中",
            "details": {"cancel_requested_at": "2026-04-01T10:00:00+00:00"},
        },
    ):
        response = self.client.post("/api/admin/task-runs/run-ai-1/cancel")

    self.assertEqual(response.status_code, 202)
    self.assertIn("终止请求已提交", response.json()["message"])

def test_cancel_task_run_should_return_409_for_finished_task(self):
    self._login()
    with patch(
        "src.api.admin.request_task_run_cancel",
        side_effect=ValueError("task_not_running"),
    ):
        response = self.client.post("/api/admin/task-runs/run-ai-1/cancel")

    self.assertEqual(response.status_code, 409)
```

并补后台包装取消测试：

```python
async def test_run_ai_analysis_in_background_should_record_cancelled_when_cancel_requested(self):
    params = {"source_id": 1, "limit": 20, "only_unanalyzed": True}

    async def _raise_cancelled(*args, **kwargs):
        raise admin_api.TaskCancellationRequested("user_requested")

    with patch("src.api.admin.run_ai_analysis", side_effect=_raise_cancelled), patch(
        "src.api.admin.record_task_run"
    ) as record_mock:
        await admin_api._run_ai_analysis_in_background("run-ai-1", "2026-04-01T10:00:00+00:00", params)

    self.assertEqual(record_mock.call_args.kwargs["status"], "cancelled")
```

- [ ] **Step 2: 跑 API 测试，确认新增用例先失败**

Run: `python -m pytest tests/test_admin_api.py -k "cancel_task_run or record_cancelled"`

Expected:
- 新增路由不存在
- `TaskCancellationRequested` 不存在

- [ ] **Step 3: 增加统一取消异常和取消接口**

在 `src/services/task_progress.py` 中新增：

```python
CancelCheck = Callable[[], bool]

class TaskCancellationRequested(RuntimeError):
    """协作式取消：在安全检查点停止后续处理。"""

def raise_if_cancel_requested(cancel_check: CancelCheck | None) -> None:
    if cancel_check and cancel_check():
        raise TaskCancellationRequested("user_requested")
```

在 `src/api/admin.py` 中接入：

```python
from src.services.task_progress import TaskCancellationRequested, raise_if_cancel_requested
from src.services.admin_task_service import request_task_run_cancel, serialize_task_run_for_admin, is_task_run_cancel_requested

def build_admin_cancel_check(task_id: str):
    return lambda: is_task_run_cancel_requested(task_id)

@protected_router.post("/task-runs/{task_id}/cancel", status_code=202)
async def cancel_task_run(task_id: str):
    try:
        task_run = request_task_run_cancel(task_id, cancel_reason="user_requested", cancel_requested_by="admin")
    except ValueError as exc:
        detail = "当前任务已经结束，不能再终止。"
        if str(exc) == "task_not_found":
            raise HTTPException(status_code=404, detail="未找到对应任务。") from exc
        raise HTTPException(status_code=409, detail=detail) from exc

    return {
        "message": "终止请求已提交，正在等待当前处理单元结束。",
        "task_run": serialize_task_run_for_admin(task_run),
    }
```

并新增统一取消落库 helper：

```python
def _record_cancelled_task_run(*, task_type: str, task_id: str, started_at: str | None, params: dict, result: dict | None = None):
    metrics = result or {}
    record_task_run(
        task_type=task_type,
        status="cancelled",
        summary="用户已提前终止，本次已保留已处理结果",
        details={
            **params,
            **metrics,
            "cancel_reason": "user_requested",
            **build_progress_details("stage_only", metrics=metrics),
        },
        params=params,
        task_id=task_id,
        started_at=started_at,
        phase="已终止",
        progress=100,
    )
```

- [ ] **Step 4: 在后台包装函数里捕获取消异常**

以 `_run_ai_analysis_in_background()` 和 `_run_job_extraction_in_background()` 为模板，改为：

```python
result: dict[str, Any] | None = None
cancel_check = build_admin_cancel_check(task_id)

try:
    result = await _run_with_heartbeat(
        task_id=task_id,
        phase="正在批量执行 AI 分析",
        details=build_progress_details("stage_only"),
        awaitable=run_ai_analysis(
            db,
            source_id=params["source_id"],
            limit=params["limit"],
            only_unanalyzed=params["only_unanalyzed"],
            progress_callback=build_admin_progress_callback(task_id),
            cancel_check=cancel_check,
        ),
    )
except TaskCancellationRequested:
    _record_cancelled_task_run(
        task_type="ai_analysis",
        task_id=task_id,
        started_at=started_at,
        params=params,
        result=result,
    )
    return
```

- [ ] **Step 5: 再跑 API 测试**

Run: `python -m pytest tests/test_admin_api.py -k "cancel_task_run or record_cancelled"`

Expected:
- PASS
- 取消路由存在
- 包装层能把取消落成 `cancelled`

### Task 3: 业务服务增加协作式取消检查点

**Files:**
- Modify: `src/services/ai_analysis_service.py`
- Modify: `src/services/post_job_service.py`
- Modify: `src/services/duplicate_service.py`
- Modify: `src/services/scraper_service.py`
- Test: `tests/test_ai_analysis_service.py`
- Test: `tests/test_post_job_service.py`
- Test: `tests/test_duplicate_service.py`
- Test: `tests/test_scraper_service.py`

- [ ] **Step 1: 先补服务层取消测试**

在 `tests/test_ai_analysis_service.py` 和 `tests/test_post_job_service.py` 里先补两条关键失败用例：

```python
async def test_run_ai_analysis_should_stop_before_next_post_when_cancel_requested(self):
    cancel_state = {"count": 0}

    def cancel_check():
        cancel_state["count"] += 1
        return cancel_state["count"] > 1

    with self.assertRaises(TaskCancellationRequested):
        await run_ai_analysis(
            self.db,
            limit=10,
            only_unanalyzed=True,
            cancel_check=cancel_check,
        )

async def test_backfill_post_jobs_should_stop_before_next_post_when_cancel_requested(self):
    cancel_state = {"count": 0}

    def cancel_check():
        cancel_state["count"] += 1
        return cancel_state["count"] > 1

    with self.assertRaises(TaskCancellationRequested):
        await backfill_post_jobs(
            self.db,
            limit=10,
            only_unindexed=True,
            use_ai=True,
            cancel_check=cancel_check,
        )
```

在 `tests/test_duplicate_service.py` 和 `tests/test_scraper_service.py` 里补“进入下一组/下一条前触发取消”的同类测试。

- [ ] **Step 2: 跑服务层取消测试，确认新增用例先失败**

Run: `python -m pytest tests/test_ai_analysis_service.py tests/test_post_job_service.py tests/test_duplicate_service.py tests/test_scraper_service.py -k "cancel_requested"`

Expected:
- 新签名里的 `cancel_check` 还不存在
- 或未触发取消异常

- [ ] **Step 3: 给各服务函数补 cancel_check 并在循环边界检查**

把以下函数签名统一加上 `cancel_check`：

```python
async def run_ai_analysis(..., progress_callback: ProgressCallback | None = None, cancel_check: CancelCheck | None = None) -> dict[str, Any]:
async def backfill_post_jobs(..., progress_callback: ProgressCallback | None = None, cancel_check: CancelCheck | None = None) -> dict[str, Any]:
async def backfill_existing_attachments(..., progress_callback: ProgressCallback | None = None, cancel_check: CancelCheck | None = None) -> dict:
def run_duplicate_backfill(..., progress_callback: ProgressCallback | None = None, cancel_check: CancelCheck | None = None) -> dict[str, Any]:
def backfill_base_analysis(..., cancel_check: CancelCheck | None = None) -> dict[str, Any]:
```

在循环边界调用：

```python
for index, post in enumerate(posts, start=1):
    raise_if_cancel_requested(cancel_check)
    try:
        with db.begin_nested():
            ...
```

`duplicate_service.py` 的关键片段：

```python
for index, group in enumerate(selected_groups, start=1):
    raise_if_cancel_requested(cancel_check)
    ...
```

`scraper_service.py` 的关键片段：

```python
for index, post in enumerate(posts, start=1):
    raise_if_cancel_requested(cancel_check)
    ...
```

`backfill_base_analysis()` 中如果已存在内部循环，也在进入下一条前调用 `raise_if_cancel_requested(cancel_check)`。

- [ ] **Step 4: 把 cancel_check 透传到后台包装调用点**

在 `src/api/admin.py` 的调用点统一加上：

```python
cancel_check=build_admin_cancel_check(task_id)
```

例如：

```python
result = await backfill_post_jobs(
    db,
    source_id=params["source_id"],
    limit=params["limit"],
    only_unindexed=params["only_unindexed"],
    use_ai=params["use_ai"],
    progress_callback=build_admin_progress_callback(task_id),
    cancel_check=cancel_check,
)
```

- [ ] **Step 5: 再跑服务层与后台取消回归**

Run: `python -m pytest tests/test_ai_analysis_service.py tests/test_post_job_service.py tests/test_duplicate_service.py tests/test_scraper_service.py tests/test_admin_api.py -k "cancel_requested or cancel_task_run or record_cancelled"`

Expected:
- PASS
- 服务层在进入下一处理单元前可停止
- 包装层最终把任务记为 `cancelled`

### Task 4: 前端任务中心增加“提前终止”动作和取消态展示

**Files:**
- Modify: `frontend/src/api/posts.js`
- Modify: `frontend/src/views/admin/adminDashboardTaskActions.js`
- Modify: `frontend/src/views/admin/adminDashboardDataService.js`
- Modify: `frontend/src/views/admin/adminTaskRunPresentation.js`
- Modify: `frontend/src/views/admin/sections/AdminTaskRunCard.vue`
- Test: `frontend/tests/adminDashboardTaskActions.test.mjs`
- Test: `frontend/tests/adminDashboardDataService.test.mjs`
- Test: `frontend/tests/adminTaskRunPresentation.test.mjs`

- [ ] **Step 1: 先补前端取消动作测试**

在 `frontend/tests/adminDashboardTaskActions.test.mjs` 中新增：

```javascript
test('getTaskActionDefinitions should expose cancel for running task without cancel request', () => {
  const actions = getTaskActionDefinitions({
    task_type: 'ai_analysis',
    status: 'running',
    details: {}
  })

  assert.equal(actions.some((item) => item.key === 'cancel'), true)
})

test('getTaskActionDefinitions should keep retry and incremental for cancelled incremental task', () => {
  const actions = getTaskActionDefinitions({
    task_type: 'ai_analysis',
    status: 'cancelled',
    details: {},
    params: { limit: 100, only_unanalyzed: true }
  })

  assert.deepEqual(
    actions.map((item) => item.key),
    ['retry', 'incremental']
  )
})
```

在 `frontend/tests/adminDashboardDataService.test.mjs` 中新增：

```javascript
test('cancelTaskRun should submit cancel request and clear canceling state after completion', async () => {
  let cancelledTaskId = ''
  const { service, state } = createHarness({
    adminApiOverrides: {
      cancelTaskRun: async (taskId) => {
        cancelledTaskId = taskId
        return { data: { message: '终止请求已提交' } }
      }
    }
  })

  await service.cancelTaskRun({ id: 'run-ai-1' })

  assert.equal(cancelledTaskId, 'run-ai-1')
  assert.equal(state.cancelingTaskId, '')
})
```

在 `frontend/tests/adminTaskRunPresentation.test.mjs` 中新增：

```javascript
test('buildTaskRunCardPresentation should surface cancelling notice while request is pending', () => {
  const card = buildTaskRunCardPresentation({
    task_type: 'ai_analysis',
    status: 'running',
    summary: 'AI 分析进行中',
    details: { cancel_requested_at: '2026-04-01T10:00:00Z' }
  })

  assert.equal(card.statusLabel, '正在终止')
  assert.equal(card.cancellationNotice.title, '终止请求已提交')
})

test('buildTaskRunCardPresentation should treat cancelled run as non-failure final state', () => {
  const card = buildTaskRunCardPresentation({
    task_type: 'job_extraction',
    status: 'cancelled',
    summary: '用户已提前终止，已处理 4 条，已写入 12 条岗位',
    metrics: { posts_scanned: 4, jobs_saved: 12 }
  })

  assert.equal(card.statusLabel, '已终止')
  assert.equal(card.failureNotice, null)
})
```

- [ ] **Step 2: 跑前端取消测试，确认新增用例先失败**

Run: `node --test frontend/tests/adminDashboardTaskActions.test.mjs frontend/tests/adminDashboardDataService.test.mjs frontend/tests/adminTaskRunPresentation.test.mjs`

Expected:
- 还没有 `cancel` 动作
- 还没有 `cancelTaskRun`
- 展示层还不知道 `cancelled`

- [ ] **Step 3: 接入前端 API 与数据服务**

在 `frontend/src/api/posts.js` 增加：

```javascript
cancelTaskRun(taskId) {
  return client.post(`/api/admin/task-runs/${taskId}/cancel`)
}
```

在 `frontend/src/views/admin/adminDashboardDataService.js` 里增加状态与方法：

```javascript
state.cancelingTaskId = ''

const cancelTaskRun = async (run) => {
  if (!run?.id) return
  state.cancelingTaskId = run.id
  try {
    const response = await adminApi.cancelTaskRun(run.id)
    setFeedback('success', normalizeAdminUiText(response?.data?.message || '终止请求已提交', '终止请求已提交'))
    await refreshTaskStatus()
  } catch (error) {
    if (!handleAdminAccessError(error)) setFeedback('error', getErrorMessage(error, '提交终止请求失败'))
  } finally {
    state.cancelingTaskId = ''
  }
}
```

- [ ] **Step 4: 扩展动作定义和任务卡展示**

在 `frontend/src/views/admin/adminDashboardTaskActions.js` 中新增：

```javascript
cancel: {
  key: 'cancel',
  label: '提前终止',
  busyLabel: '提交中...',
  description: '停止后续未开始的处理内容，已完成结果会保留。',
  scopeLabel: '当前任务'
}
```

并在 `getTaskActionDefinitions()` 中追加运行中 cancel 规则：

```javascript
if (['queued', 'pending', 'running', 'processing'].includes(run?.status) && !run?.details?.cancel_requested_at) {
  actions.push(resolveActionDefinition(taskType, 'cancel'))
}
```

同时让 `cancelled` 保留后续动作：

```javascript
if (run?.status === 'failed' || run?.status === 'cancelled') {
  return [resolveActionDefinition(taskType, 'retry')].filter(Boolean)
}
if (run?.status === 'success') {
  return [resolveActionDefinition(taskType, 'rerun')].filter(Boolean)
}
```

并保持：

```javascript
if (['success', 'cancelled'].includes(run?.status) && INCREMENTAL_ACTION_TASK_TYPES.has(taskType) && !actionKeys.has('incremental')) {
  actions.push(resolveActionDefinition(taskType, 'incremental'))
}
```

在 `adminTaskRunPresentation.js` 中扩展状态展示：

```javascript
if (run?.status === 'cancelled') return '已终止'
if (isRunningTaskStatus(run?.status) && run?.details?.cancel_requested_at) return '正在终止'
```

并增加：

```javascript
cancellationNotice: isRunningTaskStatus(run?.status) && run?.details?.cancel_requested_at
  ? {
      title: '终止请求已提交',
      description: '当前处理单元结束后会停止，已完成结果会保留。'
    }
  : run?.status === 'cancelled'
    ? {
        title: '这次处理已终止',
        description: '已完成的结果已保留，可继续补剩余内容或重新运行。'
      }
    : null
```

在 `AdminTaskRunCard.vue` 中：

```vue
<AppNotice
  v-if="cardPresentation.cancellationNotice"
  tone="warning"
  :title="cardPresentation.cancellationNotice.title"
  :description="cardPresentation.cancellationNotice.description"
/>
```

并让动作按钮支持 `cancel`：

```vue
@click="handleTaskAction(action.key)"
```

```javascript
const handleTaskAction = (actionKey) => {
  if (actionKey === 'cancel') {
    props.cancelTaskRun(props.run)
    return
  }
  props.retryTaskRun(props.run, actionKey)
}
```

- [ ] **Step 5: 跑前端回归并确认构建通过**

Run:

```bash
cd frontend
node --test tests/adminDashboardTaskActions.test.mjs tests/adminDashboardDataService.test.mjs tests/adminTaskRunPresentation.test.mjs
npm run build
```

Expected:
- PASS
- 运行中任务显示“提前终止”
- 已请求终止显示“正在终止”
- 已终止任务显示最终结果且不误报为失败

### Task 5: 全链路回归与范围确认

**Files:**
- Modify: `docs/superpowers/specs/2026-04-01-admin-task-soft-cancel-design.md`
- Modify: `docs/superpowers/plans/2026-04-01-admin-task-soft-cancel-phase1.md`

- [ ] **Step 1: 跑本期涉及的完整验证集合**

Run:

```bash
python -m pytest tests/test_admin_task_service.py tests/test_admin_api.py tests/test_ai_analysis_service.py tests/test_post_job_service.py tests/test_duplicate_service.py tests/test_scraper_service.py
cd frontend
npm test
npm run build
```

Expected:
- 后端相关测试全部通过
- 前端任务中心相关测试全部通过
- 前端构建通过

- [ ] **Step 2: 做范围回顾，确认未把抓取类取消一起带入**

检查以下点：

- `manual_scrape` / `scheduled_scrape` 没有暴露 cancel 按钮
- API 取消接口不会误接受已结束任务
- 互斥任务只有在最终 `cancelled` 后才会释放

- [ ] **Step 3: 更新文档中的实际实现边界**

如果本轮实现只覆盖：

- `attachment_backfill`
- `base_analysis_backfill`
- `ai_analysis`
- `job_extraction`
- `duplicate_backfill`

则把 spec 和 plan 里的状态改成“Phase 1 已完成，抓取类任务留待下一轮”。

- [ ] **Step 4: 准备提交**

Run:

```bash
git status --short
git diff --stat
```

Commit:

```bash
git add src/services/admin_task_service.py src/services/task_progress.py src/api/admin.py src/services/ai_analysis_service.py src/services/post_job_service.py src/services/duplicate_service.py src/services/scraper_service.py tests/test_admin_task_service.py tests/test_admin_api.py tests/test_ai_analysis_service.py tests/test_post_job_service.py tests/test_duplicate_service.py tests/test_scraper_service.py frontend/src/api/posts.js frontend/src/views/admin/adminDashboardTaskActions.js frontend/src/views/admin/adminDashboardDataService.js frontend/src/views/admin/adminTaskRunPresentation.js frontend/src/views/admin/sections/AdminTaskRunCard.vue frontend/tests/adminDashboardTaskActions.test.mjs frontend/tests/adminDashboardDataService.test.mjs frontend/tests/adminTaskRunPresentation.test.mjs docs/superpowers/specs/2026-04-01-admin-task-soft-cancel-design.md docs/superpowers/plans/2026-04-01-admin-task-soft-cancel-phase1.md
git commit -m "feat: 支持后台任务软取消与终止状态展示" -m "主要变更：
- 新增后台任务取消请求、取消接口与 cancelled 状态序列化
- 为内容处理类长任务补充协作式取消检查点并保留已处理结果
- 后台任务中心新增提前终止动作、终止中提示与已终止状态展示"
```
