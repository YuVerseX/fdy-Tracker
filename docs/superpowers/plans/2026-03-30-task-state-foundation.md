# 任务状态真实性与任务中心基础 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让后台任务 API、任务记录和现有任务卡片都改成“语义真实”的状态表达，补上实时 metrics、`rerun_of_task_id` 和区分 `按原条件重试 / 再次运行` 的最小语义基础。

**Architecture:** 后端继续以 `admin_task_runs.json` 作为原始运行记录，但在 `admin_task_service.py` 增加序列化层，把原始记录转换成面向前端的 `display_name / status_label / progress_mode / stage_label / metrics / actions` 契约。长任务服务通过统一的 `progress_callback` 上报实时 metrics，`src/api/admin.py` 和 `src/scheduler/jobs.py` 负责把这些进度写进任务记录。前端当前的任务卡片不做大改版，只先切到真实状态模型，不再把缺失指标显示成 `0`，也不再把固定阶段值伪装成真实百分比。

**Tech Stack:** FastAPI, SQLAlchemy, asyncio, Vue 3, Axios, unittest, node:test, Vite

---

### Task 1: 后端任务展示契约

**Files:**
- Modify: `src/services/admin_task_service.py`
- Modify: `src/api/admin.py`
- Test: `tests/test_admin_task_service.py`
- Test: `tests/test_admin_api.py`

- [ ] **Step 1: 先补任务展示契约测试**

在 `tests/test_admin_task_service.py` 里补“原始记录 -> 展示契约”的失败用例，至少覆盖：

```python
def test_serialize_task_run_should_expose_labels_and_stage_only_mode(self):
    task_run = admin_task_service.record_task_run(
        task_type="manual_scrape",
        status="success",
        summary="手动抓取完成，新增或更新 12 条记录",
        details={
            "progress_mode": "stage_only",
            "metrics": {
                "posts_seen": 18,
                "posts_created": 8,
                "posts_updated": 4,
            },
        },
        params={"source_id": 1, "max_pages": 3},
        phase="抓取完成",
        progress=100,
    )

    serialized = admin_task_service.serialize_task_run_for_admin(task_run)

    self.assertEqual(serialized["display_name"], "手动抓取最新数据")
    self.assertEqual(serialized["status_label"], "完成")
    self.assertEqual(serialized["progress_mode"], "stage_only")
    self.assertEqual(serialized["stage_label"], "抓取完成")
    self.assertEqual(serialized["metrics"]["posts_seen"], 18)
    self.assertIn("rerun", serialized["actions"])

def test_serialize_task_run_should_distinguish_retry_and_rerun(self):
    failed_run = admin_task_service.record_task_run(
        task_type="attachment_backfill",
        status="failed",
        summary="历史附件补处理失败",
        details={"failure_reason": "network timeout"},
        params={"limit": 50},
        phase="附件补处理失败",
        progress=100,
    )
    success_run = admin_task_service.record_task_run(
        task_type="attachment_backfill",
        status="success",
        summary="历史附件补处理完成",
        details={"progress_mode": "stage_only"},
        params={"limit": 50},
        phase="附件补处理完成",
        progress=100,
    )

    failed_view = admin_task_service.serialize_task_run_for_admin(failed_run)
    success_view = admin_task_service.serialize_task_run_for_admin(success_run)

    self.assertEqual(failed_view["actions"][0]["key"], "retry")
    self.assertEqual(success_view["actions"][0]["key"], "rerun")
```

在 `tests/test_admin_api.py` 里补接口用例，确认 `/api/admin/task-runs` 返回的是序列化后的展示字段，而不是裸 JSON：

```python
def test_get_task_runs_should_return_display_contract(self):
    with patch(
        "src.api.admin.load_task_runs_for_admin",
        return_value=[{
            "id": "run-1",
            "task_type": "manual_scrape",
            "display_name": "手动抓取最新数据",
            "status": "running",
            "status_label": "执行中",
            "progress_mode": "stage_only",
            "stage_label": "正在抓取源站并写入数据库",
            "actions": [],
        }],
    ):
        self._login()
        response = self.client.get("/api/admin/task-runs")

    self.assertEqual(response.status_code, 200)
    payload = response.json()["items"][0]
    self.assertEqual(payload["display_name"], "手动抓取最新数据")
    self.assertEqual(payload["progress_mode"], "stage_only")
    self.assertIn("stage_label", payload)
```

- [ ] **Step 2: 跑后端任务记录测试，确认现状失败**

Run: `python -m unittest -v tests.test_admin_task_service tests.test_admin_api`

Expected:
- `serialize_task_run_for_admin` / `load_task_runs_for_admin` 还不存在
- `/api/admin/task-runs` 仍返回原始结构，不含 `display_name`、`status_label`、`actions`

- [ ] **Step 3: 在 `admin_task_service.py` 增加序列化层和动作语义**

在 `src/services/admin_task_service.py` 增加面向前端的序列化函数，不直接把原始任务记录扔给页面。

目标片段：

```python
TASK_STATUS_LABELS = {
    "queued": "排队中",
    "pending": "排队中",
    "running": "执行中",
    "processing": "执行中",
    "success": "完成",
    "failed": "失败",
}

def build_task_actions(task_run: Dict[str, Any]) -> list[dict[str, str]]:
    status = task_run.get("status")
    task_type = task_run.get("task_type")
    if task_type not in CONTENT_MUTATION_TASK_TYPES:
        return []
    if status == "failed":
        return [{"key": "retry", "label": "按原条件重试"}]
    if status == "success":
        return [{"key": "rerun", "label": "再次运行"}]
    return []

def serialize_task_run_for_admin(task_run: Dict[str, Any]) -> Dict[str, Any]:
    details = dict(task_run.get("details") or {})
    progress_mode = details.get("progress_mode") or "stage_only"
    return {
        **task_run,
        "display_name": get_task_type_label(task_run.get("task_type") or ""),
        "status_label": TASK_STATUS_LABELS.get(task_run.get("status"), "未知"),
        "progress_mode": progress_mode,
        "stage_label": task_run.get("phase") or "",
        "metrics": details.get("metrics") or {},
        "actions": build_task_actions(task_run),
        "rerun_of_task_id": task_run.get("rerun_of_task_id"),
    }

def load_task_runs_for_admin(limit: int = 20) -> List[Dict[str, Any]]:
    return [serialize_task_run_for_admin(run) for run in load_task_runs(limit=limit)]
```

- [ ] **Step 4: 把 `rerun_of_task_id` 和序列化结果接进 API**

在 `src/api/admin.py` 里把任务读取接口改成走新序列化层，同时给所有任务请求模型补 `rerun_of_task_id: str | None = None`，让前端“再次运行”能被后端记录下来。

目标片段：

```python
class TaskRetryMixin(BaseModel):
    rerun_of_task_id: str | None = None

class RunScrapeRequest(TaskRetryMixin):
    source_id: int = Field(default=1, ge=1)
    max_pages: int = Field(default=5, ge=1, le=20)

@protected_router.get("/task-runs")
async def get_task_runs(limit: int = Query(20, ge=1, le=50)):
    return {"items": load_task_runs_for_admin(limit=limit)}

@protected_router.get("/task-runs/summary")
async def get_task_runs_summary():
    return get_task_summary_for_admin()
```

同时在 `_start_task_or_raise_conflict()` 透传 `rerun_of_task_id`：

```python
return start_task_run(
    task_type=task_type,
    summary=summary,
    params=params,
    details={"rerun_of_task_id": params.get("rerun_of_task_id")},
    conflict_task_types=resolve_conflict_task_types(task_type, conflict_task_types),
)
```

并把 `start_task_run()` / `record_task_run()` 改成把这个值写到顶层：

```python
"rerun_of_task_id": details.get("rerun_of_task_id") or params.get("rerun_of_task_id")
```

- [ ] **Step 5: 再跑后端任务记录回归**

Run: `python -m unittest -v tests.test_admin_task_service tests.test_admin_api`

Expected:
- PASS
- `/api/admin/task-runs` 响应里出现 `display_name`、`status_label`、`progress_mode`、`stage_label`、`actions`

### Task 2: 长任务实时 metrics 上报

**Files:**
- Create: `src/services/task_progress.py`
- Modify: `src/services/scraper_service.py`
- Modify: `src/services/ai_analysis_service.py`
- Modify: `src/services/post_job_service.py`
- Modify: `src/api/admin.py`
- Modify: `src/scheduler/jobs.py`
- Test: `tests/test_scraper_service.py`
- Test: `tests/test_ai_analysis_service.py`
- Test: `tests/test_post_job_service.py`

- [ ] **Step 1: 先补服务层 progress callback 失败测试**

在 3 个服务测试文件里补“运行中应持续回调 metrics”的用例。

`tests/test_scraper_service.py` 目标片段：

```python
async def test_scrape_and_save_should_emit_progress_metrics(self):
    updates = []

    def on_progress(payload):
        updates.append(payload)

    result = await scrape_and_save(
        self.db,
        source_id=1,
        max_pages=1,
        progress_callback=on_progress,
    )

    self.assertGreaterEqual(len(updates), 1)
    self.assertEqual(updates[-1]["stage_key"], "persist-posts")
    self.assertIn("posts_seen", updates[-1]["metrics"])
    self.assertGreaterEqual(result, 0)
```

`tests/test_ai_analysis_service.py` 目标片段：

```python
def test_run_ai_analysis_should_emit_progress_metrics(self):
    updates = []

    result = run_ai_analysis(
        self.db,
        source_id=None,
        limit=3,
        only_unanalyzed=True,
        progress_callback=updates.append,
    )

    self.assertGreaterEqual(len(updates), 1)
    self.assertIn("posts_scanned", updates[-1]["metrics"])
```

- [ ] **Step 2: 跑服务层测试，确认现状失败**

Run: `python -m unittest -v tests.test_scraper_service tests.test_ai_analysis_service tests.test_post_job_service`

Expected:
- 现有函数签名还没有 `progress_callback`
- 新测试会因参数不存在或回调未触发而失败

- [ ] **Step 3: 增加统一 progress helper 并给服务函数补回调**

新建 `src/services/task_progress.py`：

```python
from typing import Callable, Any

ProgressCallback = Callable[[dict[str, Any]], None]

def emit_progress(
    progress_callback: ProgressCallback | None,
    *,
    stage_key: str,
    stage_label: str,
    progress_mode: str,
    metrics: dict[str, Any] | None = None,
) -> None:
    if not progress_callback:
        return
    progress_callback({
        "stage_key": stage_key,
        "stage_label": stage_label,
        "progress_mode": progress_mode,
        "metrics": metrics or {},
    })
```

把以下函数签名统一改成可选回调：

```python
async def scrape_and_save(..., progress_callback: ProgressCallback | None = None) -> int:
async def backfill_existing_attachments(..., progress_callback: ProgressCallback | None = None) -> dict:
def run_ai_analysis(..., progress_callback: ProgressCallback | None = None) -> dict:
async def backfill_post_jobs(..., progress_callback: ProgressCallback | None = None) -> dict:
```

在循环里按真实已处理数上报：

```python
emit_progress(
    progress_callback,
    stage_key="scan-posts",
    stage_label="正在抓取源站并写入数据库",
    progress_mode="stage_only",
    metrics={
        "pages_scanned": page_index,
        "posts_seen": len(results),
        "posts_created": new_count,
        "posts_updated": updated_count,
    },
)
```

- [ ] **Step 4: 把服务层 progress callback 接到任务记录更新**

在 `src/api/admin.py` 和 `src/scheduler/jobs.py` 里增加把服务层回调转换成任务记录 details 的适配器。

目标片段：

```python
def build_admin_progress_callback(task_id: str):
    def _callback(payload: dict) -> None:
        metrics = payload.get("metrics") or {}
        update_task_run(
            task_id=task_id,
            status="running",
            phase=payload.get("stage_label") or "",
            progress=None,
            details={
                "progress_mode": payload.get("progress_mode") or "stage_only",
                "stage_key": payload.get("stage_key") or "",
                "metrics": metrics,
            },
        )
    return _callback
```

接线方式：

```python
result = await backfill_existing_attachments(
    db,
    source_id=params["source_id"],
    limit=params["limit"],
    progress_callback=build_admin_progress_callback(task_id),
)
```

保留 `duplicate_backfill` 的 determinate 百分比逻辑，其余任务统一切到 `stage_only`。

- [ ] **Step 5: 再跑服务层与任务接口回归**

Run: `python -m unittest -v tests.test_scraper_service tests.test_ai_analysis_service tests.test_post_job_service tests.test_admin_api`

Expected:
- PASS
- 任务详情里开始出现真实 `metrics`
- 抓取 / 分析 / 岗位任务不再只能靠固定 `55% / 65%`

### Task 3: 前端任务卡片切到真实状态语义

**Files:**
- Create: `frontend/src/utils/adminTaskRunPresentation.js`
- Modify: `frontend/src/views/admin/adminDashboardDataService.js`
- Modify: `frontend/src/views/admin/sections/AdminTaskRunCard.vue`
- Test: `frontend/tests/adminDashboardDataService.test.mjs`
- Test: `frontend/tests/adminDashboardViewModels.test.mjs`
- Test: `frontend/tests/adminTaskRunPresentation.test.mjs`

- [ ] **Step 1: 先补前端任务卡片语义测试**

新增 `frontend/tests/adminTaskRunPresentation.test.mjs`：

```javascript
import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildTaskRunPresentation,
  getRetryActionLabel
} from '../src/utils/adminTaskRunPresentation.js'

test('stage_only mode should show stage label instead of fake percent', () => {
  const presentation = buildTaskRunPresentation({
    status: 'running',
    progress_mode: 'stage_only',
    stage_label: '正在抓取源站并写入数据库',
    metrics: { posts_seen: 18, posts_created: 8, posts_updated: 4 }
  })

  assert.equal(presentation.progressText, '正在抓取源站并写入数据库')
  assert.equal(presentation.percentLabel, '')
  assert.equal(presentation.metricItems.find((item) => item.key === 'posts_seen').value, '18')
})

test('missing metrics should stay hidden instead of rendering 0', () => {
  const presentation = buildTaskRunPresentation({
    status: 'running',
    progress_mode: 'stage_only',
    metrics: { processed_records: 12 }
  })

  assert.equal(presentation.metricItems.some((item) => item.key === 'attachments_downloaded'), false)
})

test('retry label should distinguish failed and successful runs', () => {
  assert.equal(getRetryActionLabel({ status: 'failed' }), '按原条件重试')
  assert.equal(getRetryActionLabel({ status: 'success' }), '再次运行')
})
```

- [ ] **Step 2: 跑前端任务语义测试，确认现状失败**

Run:

```bash
cd frontend
node --test tests/adminDashboardViewModels.test.mjs tests/adminDashboardDataService.test.mjs tests/adminTaskRunPresentation.test.mjs
```

Expected:
- 新文件导入失败或断言失败
- 现有逻辑仍把运行中任务展示成固定百分比或默认 `0`

- [ ] **Step 3: 抽出任务卡片 presentation helper**

新建 `frontend/src/utils/adminTaskRunPresentation.js`，把 `AdminTaskRunCard.vue` 里的语义判断搬出来。

目标片段：

```javascript
const METRIC_LABELS = {
  pages_scanned: '已扫描页数',
  posts_seen: '已发现公告',
  posts_created: '新增公告',
  posts_updated: '更新公告',
  attachments_downloaded: '已下载附件',
  fields_added: '新增字段'
}

export const getRetryActionLabel = (run) => run?.status === 'failed' ? '按原条件重试' : '再次运行'

export function buildTaskRunPresentation(run = {}) {
  const metrics = run.metrics || run.details?.metrics || {}
  const metricItems = Object.entries(METRIC_LABELS)
    .filter(([key]) => metrics[key] !== undefined && metrics[key] !== null)
    .map(([key, label]) => ({ key, label, value: String(metrics[key]) }))

  return {
    progressText: run.progress_mode === 'determinate'
      ? `${metrics.completed || 0} / ${metrics.total || 0}`
      : (run.stage_label || run.phase || ''),
    percentLabel: run.progress_mode === 'determinate' && Number.isFinite(Number(run.progress))
      ? `${Math.round(Number(run.progress))}%`
      : '',
    metricItems,
    retryLabel: getRetryActionLabel(run),
  }
}
```

- [ ] **Step 4: 更新数据服务和卡片模板**

在 `frontend/src/views/admin/adminDashboardDataService.js` 的 `retryTaskRun()` 里把 `rerun_of_task_id` 传回后端：

```javascript
const config = buildTaskRequestConfig(taskType, {
  params: {
    ...(run?.params || {}),
    rerun_of_task_id: run?.id || ''
  },
  forms
})
```

在 `AdminTaskRunCard.vue` 中改成使用 `buildTaskRunPresentation()`：

```vue
<script setup>
import { buildTaskRunPresentation } from '../../../utils/adminTaskRunPresentation.js'

const presentation = computed(() => buildTaskRunPresentation(props.run))
</script>

<template>
  <div class="text-xs text-gray-500">
    {{ presentation.progressText }}
    <span v-if="presentation.percentLabel">{{ presentation.percentLabel }}</span>
  </div>
  <div v-if="presentation.metricItems.length > 0" class="grid grid-cols-2 gap-3">
    <div v-for="item in presentation.metricItems" :key="item.key">
      <div class="text-gray-500">{{ item.label }}</div>
      <div class="font-semibold text-gray-900">{{ item.value }}</div>
    </div>
  </div>
</template>
```

- [ ] **Step 5: 跑前端回归并确认构建通过**

Run:

```bash
cd frontend
npm test
npm run build
```

Expected:
- `adminTaskRunPresentation` 相关测试 PASS
- 任务卡片运行中显示阶段和实时计数
- 不再把缺失指标展示成 `0`

