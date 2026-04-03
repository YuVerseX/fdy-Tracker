# 后台任务中心 Phase 2 标准版收口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为后台任务中心落地 Phase 2 标准版收口方案，建立稳定的 `status/stage/live_metrics/final_metrics` 契约，为抓取任务补齐 collecting 阶段可观测指标，并把任务卡收口为“阶段轨迹 + 当前结果 + 收口后的动作优先级”的可信过程界面。

**Architecture:** 后端继续以 `admin_task_runs.json` 作为任务事实源，但把运行态和完成态从 `phase + details.metrics` 迁移到 canonical `status/stage/live_metrics/final_metrics`；`src/api/admin.py` 与 `src/scheduler/jobs.py` 只负责把服务层 progress payload 写回 canonical 任务结构。前端继续复用现有任务中心三段式布局，但在 `ui-ux-pro-max` 约束下新增语义化阶段轨迹组件、按 canonical stage 渲染结果区，并将任务动作收口为“运行态单主动作，终态保留少量高价值后续动作”。

**Tech Stack:** FastAPI, SQLAlchemy, APScheduler, asyncio, Vue 3, Vite, Tailwind, node:test, unittest, ui-ux-pro-max

---

## File Structure

**Backend contract and progress plumbing**
- Modify: `src/services/task_progress.py`
- Modify: `src/services/admin_task_service.py`
- Modify: `src/api/admin.py`
- Modify: `src/scheduler/jobs.py`
- Test: `tests/test_admin_task_service.py`
- Test: `tests/test_admin_api.py`

**Scrape collecting metrics**
- Modify: `src/scrapers/base.py`
- Modify: `src/scrapers/jiangsu_hrss.py`
- Modify: `src/services/scraper_service.py`
- Test: `tests/test_scraper_service.py`

**Frontend task card and actions**
- Create: `frontend/src/views/admin/sections/AdminTaskStageTimeline.vue`
- Modify: `frontend/src/views/admin/adminTaskRunPresentation.js`
- Modify: `frontend/src/views/admin/adminDashboardTaskActions.js`
- Modify: `frontend/src/views/admin/sections/AdminTaskRunCard.vue`
- Test: `frontend/tests/adminTaskRunPresentation.test.mjs`
- Test: `frontend/tests/adminDashboardTaskActions.test.mjs`
- Test: `frontend/tests/adminDashboardTaskCardsUi.test.mjs`

**Docs and release gate**
- Modify: `docs/release-checklist.md`

### UI Constraint

Task 3 and any follow-up UI review must explicitly use `ui-ux-pro-max`.

Use the current site design system and keep the visual direction aligned with the existing admin shell, but apply the `ui-ux-pro-max` output that is relevant here:

- Pattern: compact data-dense dashboard, not hero marketing layout
- Interaction: semantic elements first, dynamic ARIA bindings, visible focus states
- Visual hierarchy: compact cards, reduced explanation copy, one primary CTA, no fake realtime effects

---

### Task 1: 收口后台 canonical 任务阶段契约

**Files:**
- Modify: `src/services/task_progress.py`
- Modify: `src/services/admin_task_service.py`
- Modify: `src/api/admin.py`
- Modify: `src/scheduler/jobs.py`
- Test: `tests/test_admin_task_service.py`
- Test: `tests/test_admin_api.py`

- [ ] **Step 1: 先补后端契约测试**

在 `tests/test_admin_task_service.py` 中新增 canonical 字段用例，确认序列化输出的主路径不再只靠 `phase/details.metrics`：

```python
def test_serialize_task_run_should_expose_canonical_runtime_contract(self):
    created = admin_task_service.start_task_run(
        task_type="manual_scrape",
        summary="手动抓取已提交",
        params={"source_id": 1, "max_pages": 3},
    )

    updated = admin_task_service.update_task_run(
        task_id=created["id"],
        status="running",
        phase="正在写入抓取结果",
        details={
            "stage": "persisting",
            "stage_label": "正在写入抓取结果",
            "stage_started_at": "2026-04-02T09:00:00+00:00",
            "live_metrics": {"posts_seen": 5, "posts_total": 18},
            "progress_mode": "stage_only",
            "metrics": {"posts_seen": 5, "posts_total": 18},
        },
    )

    serialized = admin_task_service.serialize_task_run_for_admin(updated)

    self.assertEqual(serialized["status"], "running")
    self.assertEqual(serialized["stage"], "persisting")
    self.assertEqual(serialized["stage_label"], "正在写入抓取结果")
    self.assertEqual(serialized["stage_started_at"], "2026-04-02T09:00:00+00:00")
    self.assertEqual(serialized["live_metrics"]["posts_seen"], 5)
    self.assertEqual(serialized["final_metrics"], {})
    self.assertEqual(serialized["details"]["stage"], "persisting")

def test_request_task_run_cancel_should_mark_cancel_requested_status(self):
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

    serialized = admin_task_service.serialize_task_run_for_admin(cancelled)

    self.assertEqual(cancelled["status"], "cancel_requested")
    self.assertEqual(serialized["status_label"], "正在终止")
    self.assertEqual(serialized["stage"], "finalizing")
    self.assertEqual(serialized["details"]["cancel_reason"], "user_requested")

def test_record_task_run_should_promote_live_metrics_to_final_metrics(self):
    task_run = admin_task_service.record_task_run(
        task_type="manual_scrape",
        status="success",
        summary="手动抓取完成，新增或更新 12 条记录",
        details={
            "stage": "finalizing",
            "stage_label": "正在整理抓取结果",
            "live_metrics": {"posts_seen": 18, "posts_created": 8, "posts_updated": 4},
            "progress_mode": "stage_only",
        },
        params={"source_id": 1, "max_pages": 3},
        phase="抓取完成",
        progress=100,
    )

    serialized = admin_task_service.serialize_task_run_for_admin(task_run)

    self.assertEqual(serialized["stage"], "")
    self.assertEqual(serialized["final_summary"], "手动抓取完成，新增或更新 12 条记录")
    self.assertEqual(serialized["final_metrics"]["posts_seen"], 18)
    self.assertEqual(serialized["live_metrics"], {})
```

在 `tests/test_admin_api.py` 中新增 progress callback 用例，确认 API 层把 canonical `stage/live_metrics` 写回任务：

```python
def test_build_admin_progress_callback_should_forward_canonical_stage_contract(self):
    callback = admin_api.build_admin_progress_callback("run-scrape-1")

    with patch("src.api.admin.update_task_run") as update_mock:
        callback({
            "stage": "collecting",
            "stage_key": "collect-pages",
            "stage_label": "正在采集源站页面",
            "progress_mode": "stage_only",
            "metrics": {"pages_fetched": 2, "raw_items_collected": 11},
        })

    kwargs = update_mock.call_args.kwargs
    self.assertEqual(kwargs["status"], "running")
    self.assertEqual(kwargs["details"]["stage"], "collecting")
    self.assertEqual(kwargs["details"]["stage_label"], "正在采集源站页面")
    self.assertEqual(kwargs["details"]["live_metrics"]["pages_fetched"], 2)
```

- [ ] **Step 2: 跑后端契约测试，确认新增用例先失败**

Run: `python -m pytest tests/test_admin_task_service.py tests/test_admin_api.py -k "canonical or cancel_requested or progress_callback_should_forward_canonical_stage_contract" -v`

Expected:
- FAIL
- `serialize_task_run_for_admin()` 还没有 `stage/live_metrics/final_metrics/final_summary`
- `request_task_run_cancel()` 仍写 `status="running"`
- `build_admin_progress_callback()` 还没有写入 `details["stage"]` 和 `details["live_metrics"]`

- [ ] **Step 3: 在进度事件和任务记录层补 canonical 契约**

先在 `src/services/task_progress.py` 扩展 progress payload，让所有调用方都能传 canonical `stage`：

```python
ProgressCallback = Callable[[dict[str, Any]], None]

def emit_progress(
    progress_callback: ProgressCallback | None,
    *,
    stage: str,
    stage_key: str,
    stage_label: str,
    progress_mode: str,
    metrics: dict[str, Any] | None = None,
) -> None:
    if not progress_callback:
        return

    progress_callback({
        "stage": stage,
        "stage_key": stage_key,
        "stage_label": stage_label,
        "progress_mode": progress_mode,
        "metrics": metrics or {},
    })
```

然后在 `src/services/admin_task_service.py` 中增加 canonical 状态和序列化辅助：

```python
TASK_STATUS_LABELS = {
    "queued": "排队中",
    "pending": "排队中",
    "running": "运行中",
    "processing": "运行中",
    "cancel_requested": "正在终止",
    "success": "完成",
    "failed": "失败",
    "cancelled": "已终止",
}

FINAL_STATUSES = {"success", "failed", "cancelled"}

def build_runtime_task_details(
    *,
    stage: str,
    stage_label: str,
    progress_mode: str = "stage_only",
    stage_key: str | None = None,
    live_metrics: Dict[str, Any] | None = None,
    stage_started_at: str | None = None,
) -> Dict[str, Any]:
    details: Dict[str, Any] = {
        "stage": stage,
        "stage_label": stage_label,
        "progress_mode": progress_mode,
        "live_metrics": dict(live_metrics or {}),
        "metrics": dict(live_metrics or {}),
    }
    if stage_key:
        details["stage_key"] = stage_key
    if stage_started_at:
        details["stage_started_at"] = stage_started_at
    return details

def _build_canonical_metrics(details: Dict[str, Any], status: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    live_metrics = dict(details.get("live_metrics") or details.get("metrics") or {})
    final_metrics = dict(details.get("final_metrics") or {})
    if status in FINAL_STATUSES:
        if not final_metrics:
            final_metrics = dict(live_metrics or details.get("metrics") or {})
        live_metrics = {}
    return live_metrics, final_metrics
```

再改 `serialize_task_run_for_admin()` 和 `record_task_run()`，让 canonical 字段成为主路径：

```python
def serialize_task_run_for_admin(task_run: Dict[str, Any]) -> Dict[str, Any]:
    normalized_task_run = dict(task_run or {})
    details = dict(normalized_task_run.get("details") or {})
    status = normalized_task_run.get("status") or ""
    stage = details.get("stage") or ""
    stage_label = details.get("stage_label") or normalized_task_run.get("phase") or ""
    live_metrics, final_metrics = _build_canonical_metrics(details, status)
    final_summary = details.get("final_summary") or (
        normalized_task_run.get("summary") if status in FINAL_STATUSES else ""
    )

    return {
        "id": normalized_task_run.get("id"),
        "task_type": normalized_task_run.get("task_type"),
        "display_name": get_task_type_label(normalized_task_run.get("task_type") or ""),
        "status": status,
        "status_label": TASK_STATUS_LABELS.get(status, "未知"),
        "stage": "" if status in FINAL_STATUSES else stage,
        "stage_label": stage_label,
        "stage_started_at": details.get("stage_started_at") or "",
        "live_metrics": live_metrics,
        "final_metrics": final_metrics,
        "final_summary": final_summary,
        "progress_mode": _normalize_admin_progress_mode(details),
        "stage_key": details.get("stage_key"),
        "metrics": live_metrics if live_metrics else final_metrics,
        "details": _build_admin_compatibility_details(
            raw_details=details,
            progress_mode=_normalize_admin_progress_mode(details),
            metrics=live_metrics if live_metrics else final_metrics,
            failure_reason=normalized_task_run.get("failure_reason"),
        ),
        "summary": normalized_task_run.get("summary"),
        "phase": stage_label,
        "started_at": normalized_task_run.get("started_at"),
        "heartbeat_at": normalized_task_run.get("heartbeat_at"),
        "finished_at": normalized_task_run.get("finished_at"),
        "duration_ms": normalized_task_run.get("duration_ms"),
        "params": normalized_task_run.get("params"),
        "progress": normalized_task_run.get("progress"),
        "failure_reason": normalized_task_run.get("failure_reason"),
        "actions": build_task_actions(normalized_task_run),
        "rerun_of_task_id": normalized_task_run.get("rerun_of_task_id"),
    }
```

把 `start_task_run()` 与 `request_task_run_cancel()` 同步到新语义：

```python
def start_task_run(...):
    started_at_value = datetime.now(timezone.utc).isoformat()
    task_run = {
        "id": uuid4().hex,
        "task_type": task_type,
        "status": "queued",
        "summary": summary,
        "phase": "任务已提交，等待后台执行",
        "progress": 0,
        "params": normalized_params,
        "details": build_runtime_task_details(
            stage="submitted",
            stage_label="任务已提交，等待后台执行",
            progress_mode="stage_only",
            stage_started_at=started_at_value,
        ) | normalized_details,
        "started_at": started_at_value,
        "heartbeat_at": started_at_value,
        "finished_at": None,
        "rerun_of_task_id": rerun_of_task_id,
    }

def request_task_run_cancel(...):
    merged_details = dict(task_run.get("details") or {})
    merged_details.update({
        "stage": "finalizing",
        "stage_label": "当前处理单元结束后会停止",
        "cancel_requested_at": datetime.now(timezone.utc).isoformat(),
        "cancel_reason": cancel_reason,
    })
    updated_run = {
        **task_run,
        "status": "cancel_requested",
        "details": merged_details,
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
    }
```

最后在 `src/api/admin.py` 和 `src/scheduler/jobs.py` 里更新 progress callback builder，把 canonical `stage/live_metrics` 透传回任务记录：

```python
def build_admin_progress_callback(task_id: str) -> ProgressCallback:
    def _callback(payload: dict) -> None:
        metrics = dict(payload.get("metrics") or {})
        update_task_run(
            task_id=task_id,
            status="running",
            phase=payload.get("stage_label") or "",
            progress=None,
            details=build_runtime_task_details(
                stage=payload.get("stage") or "submitted",
                stage_label=payload.get("stage_label") or "",
                progress_mode=payload.get("progress_mode") or "stage_only",
                stage_key=payload.get("stage_key") or "",
                live_metrics=metrics,
                stage_started_at=datetime.now(timezone.utc).isoformat(),
            ),
        )
    return _callback
```

- [ ] **Step 4: 再跑后端契约测试**

Run: `python -m pytest tests/test_admin_task_service.py tests/test_admin_api.py -k "canonical or cancel_requested or progress_callback_should_forward_canonical_stage_contract" -v`

Expected:
- PASS
- `serialize_task_run_for_admin()` 暴露 canonical `stage/live_metrics/final_metrics/final_summary`
- 取消请求被记录为 `cancel_requested`
- API 和 scheduler callback 都透传 canonical stage

- [ ] **Step 5: 提交后端契约改动**

```bash
git add src/services/task_progress.py src/services/admin_task_service.py src/api/admin.py src/scheduler/jobs.py tests/test_admin_task_service.py tests/test_admin_api.py
git commit -m "refactor: 收口后台任务阶段契约并补齐取消状态" -m "主要变更：
- 建立任务中心 canonical status/stage/live_metrics/final_metrics 契约
- 将取消请求提升为 cancel_requested 显式状态并统一 API 与调度回写
- 补齐后台契约序列化与进度事件回写测试"
```

### Task 2: 为抓取任务补充 collecting 阶段真实可观测指标

**Files:**
- Modify: `src/scrapers/base.py`
- Modify: `src/scrapers/jiangsu_hrss.py`
- Modify: `src/services/scraper_service.py`
- Test: `tests/test_scraper_service.py`

- [ ] **Step 1: 先补抓取阶段序列测试**

在 `tests/test_scraper_service.py` 中先把 `FakeScraper` 改为支持 collecting progress callback，并新增阶段序列用例：

```python
class FakeScraper:
    def __init__(self):
        self.attachment_bytes = build_excel_bytes([
            ["岗位名称", "招聘人数", "学历要求", "工作地点"],
            ["专职辅导员", "2", "硕士", "南京"]
        ])

    async def scrape(self, max_pages=10, progress_callback=None):
        if progress_callback:
            progress_callback({
                "stage": "collecting",
                "stage_key": "collect-pages",
                "stage_label": "正在采集源站页面",
                "progress_mode": "stage_only",
                "metrics": {
                    "pages_fetched": 1,
                    "detail_pages_fetched": 3,
                    "raw_items_collected": 3,
                },
            })
        return [
            {
                "title": "第一条专职辅导员公告",
                "url": "https://example.com/posts/1",
                "publish_date": datetime(2026, 3, 1, tzinfo=timezone.utc),
                "content": "专职辅导员，性别要求：男",
                "attachments": [],
            },
            {
                "title": None,
                "url": "https://example.com/posts/2",
                "publish_date": datetime(2026, 3, 2, tzinfo=timezone.utc),
                "content": "这是一条会失败的数据",
                "attachments": [],
            },
            {
                "title": "第三条专职辅导员公告",
                "url": "https://example.com/posts/3",
                "publish_date": datetime(2026, 3, 3, tzinfo=timezone.utc),
                "content": "辅导员，工作地点：南京市",
                "attachments": [],
            },
        ]

async def test_scrape_and_save_should_emit_collecting_then_persisting_progress(self):
    updates = []

    with patch("src.services.scraper_service.create_scraper", return_value=FakeScraper()):
        result = await scrape_and_save(
            self.db,
            source_id=1,
            max_pages=1,
            progress_callback=updates.append,
        )

    self.assertEqual(updates[0]["stage"], "collecting")
    self.assertEqual(updates[0]["metrics"]["pages_fetched"], 1)
    self.assertEqual(updates[0]["metrics"]["raw_items_collected"], 3)
    self.assertTrue(all(update["stage"] == "persisting" for update in updates[1:]))
    self.assertEqual(updates[-1]["metrics"]["posts_total"], 3)
    self.assertEqual(result["posts_created"], 2)
```

- [ ] **Step 2: 跑抓取阶段测试，确认 collecting 相关断言先失败**

Run: `python -m pytest tests/test_scraper_service.py -k "collecting_then_persisting_progress or emit_progress_metrics" -v`

Expected:
- FAIL
- `BaseScraper.scrape()` 还不接受 `progress_callback`
- `scrape_and_save()` 还没有透传 collecting progress
- 更新事件只有 `persist-posts`

- [ ] **Step 3: 把 collecting 指标从爬虫透传到抓取服务**

先在 `src/scrapers/base.py` 改抽象签名：

```python
from src.services.task_progress import ProgressCallback

class BaseScraper(ABC):
    @abstractmethod
    async def scrape(
        self,
        max_pages: int = 10,
        progress_callback: ProgressCallback | None = None,
    ) -> List[Dict[str, Any]]:
        """抓取数据（子类必须实现）"""
        raise NotImplementedError
```

然后在 `src/scrapers/jiangsu_hrss.py` 中维护 collecting 阶段计数器：

```python
def _emit_collecting_progress(
    self,
    progress_callback,
    *,
    pages_fetched: int,
    detail_pages_fetched: int,
    raw_items_collected: int,
) -> None:
    emit_progress(
        progress_callback,
        stage="collecting",
        stage_key="collect-pages",
        stage_label="正在采集源站页面",
        progress_mode="stage_only",
        metrics={
            "pages_fetched": pages_fetched,
            "detail_pages_fetched": detail_pages_fetched,
            "raw_items_collected": raw_items_collected,
        },
    )

async def scrape(self, max_pages: int = 10, progress_callback=None) -> List[Dict[str, Any]]:
    all_results = []
    pages_fetched = 0
    detail_pages_fetched = 0

    first_page_results = await self.scrape_first_page()
    pages_fetched += 1
    detail_pages_fetched += len(first_page_results)
    all_results.extend(first_page_results)
    self._emit_collecting_progress(
        progress_callback,
        pages_fetched=pages_fetched,
        detail_pages_fetched=detail_pages_fetched,
        raw_items_collected=len(all_results),
    )

    await self.delay()

    for page_num in range(2, max_pages + 1):
        page_results = await self.scrape_page(page_num)
        if not page_results:
            break
        pages_fetched += 1
        detail_pages_fetched += len(page_results)
        all_results.extend(page_results)
        self._emit_collecting_progress(
            progress_callback,
            pages_fetched=pages_fetched,
            detail_pages_fetched=detail_pages_fetched,
            raw_items_collected=len(all_results),
        )
        await self.delay()

    return all_results
```

最后在 `src/services/scraper_service.py` 中透传 callback，并把写库阶段 emit 改成 canonical `stage="persisting"`：

```python
results = await scraper.scrape(
    max_pages=max_pages,
    progress_callback=progress_callback,
)

emit_progress(
    progress_callback,
    stage="persisting",
    stage_key="persist-posts",
    stage_label="正在写入抓取结果",
    progress_mode="stage_only",
    metrics={
        "posts_seen": index,
        "posts_total": total_results,
        "posts_created": new_count,
        "posts_updated": updated_count,
        "failures": failure_count,
    },
)
```

- [ ] **Step 4: 再跑抓取阶段测试**

Run: `python -m pytest tests/test_scraper_service.py -k "collecting_then_persisting_progress or emit_progress_metrics" -v`

Expected:
- PASS
- `scrape_and_save()` 先产出 collecting，再产出 persisting
- collecting 指标只包含采集事实，不混入结果数
- persisting 指标继续暴露结果计数

- [ ] **Step 5: 提交抓取阶段改动**

```bash
git add src/scrapers/base.py src/scrapers/jiangsu_hrss.py src/services/scraper_service.py tests/test_scraper_service.py
git commit -m "feat: 为抓取任务补充 collecting 阶段可观测指标" -m "主要变更：
- 为爬虫抓取链路增加 collecting 阶段进度透传
- 区分 collecting 与 persisting 两段任务指标，避免抓取前半段伪结果
- 补齐抓取阶段序列测试和 persisting 回归测试"
```

### Task 3: 在 ui-ux-pro-max 约束下收口任务卡阶段轨迹与动作优先级

**Files:**
- Create: `frontend/src/views/admin/sections/AdminTaskStageTimeline.vue`
- Modify: `frontend/src/views/admin/adminTaskRunPresentation.js`
- Modify: `frontend/src/views/admin/adminDashboardTaskActions.js`
- Modify: `frontend/src/views/admin/sections/AdminTaskRunCard.vue`
- Test: `frontend/tests/adminTaskRunPresentation.test.mjs`
- Test: `frontend/tests/adminDashboardTaskActions.test.mjs`
- Test: `frontend/tests/adminDashboardTaskCardsUi.test.mjs`

- [ ] **Step 1: 先补前端呈现与动作优先级测试**

在 `frontend/tests/adminTaskRunPresentation.test.mjs` 中新增 canonical stage timeline 与结果区切换测试：

```javascript
test('buildTaskRunCardPresentation should expose canonical stage timeline items', () => {
  const card = buildTaskRunCardPresentation({
    task_type: 'manual_scrape',
    status: 'running',
    stage: 'persisting',
    stage_label: '正在写入抓取结果',
    stage_started_at: '2026-04-02T09:00:00Z',
    live_metrics: {
      posts_seen: 8,
      posts_total: 18,
      posts_created: 4,
      posts_updated: 1
    }
  })

  assert.deepEqual(
    card.stageTimelineItems.map((item) => [item.key, item.state]),
    [
      ['submitted', 'done'],
      ['collecting', 'done'],
      ['persisting', 'current'],
      ['finalizing', 'upcoming']
    ]
  )
  assert.equal(card.resultTitle, '当前结果')
})

test('buildTaskRunCardPresentation should use final metrics for finished runs', () => {
  const card = buildTaskRunCardPresentation({
    task_type: 'manual_scrape',
    status: 'success',
    stage: '',
    final_summary: '手动抓取完成，新增或更新 12 条记录',
    final_metrics: {
      posts_seen: 18,
      posts_created: 8,
      posts_updated: 4
    }
  })

  assert.equal(card.resultTitle, '本次结果')
  assert.deepEqual(card.resultItems.map((item) => item.label), ['发现公告', '新增公告', '更新公告'])
})
```

在 `frontend/tests/adminDashboardTaskActions.test.mjs` 中把动作收口到“运行态单主动作，终态保留有限后续动作”：

```javascript
test('getTaskActionDefinitions should expose follow-up actions for each task status', () => {
  const runningActions = getTaskActionDefinitions({
    task_type: 'ai_analysis',
    status: 'running',
    details: {}
  })
  const successActions = getTaskActionDefinitions({
    task_type: 'ai_analysis',
    status: 'success',
    params: { limit: 50, only_unanalyzed: false }
  })
  const cancelledActions = getTaskActionDefinitions({
    task_type: 'ai_analysis',
    status: 'cancelled',
    params: { limit: 50, only_unanalyzed: true }
  })

  assert.deepEqual(runningActions.map((item) => item.key), ['cancel'])
  assert.deepEqual(successActions.map((item) => item.key), ['rerun', 'incremental'])
  assert.deepEqual(cancelledActions.map((item) => item.key), ['retry', 'incremental'])
})
```

在 `frontend/tests/adminDashboardTaskCardsUi.test.mjs` 中新增语义化阶段轨迹和单一 CTA 的 source test：

```javascript
test('admin task stage timeline should use semantic ordered list and dynamic aria-current', () => {
  const source = readSource('views/admin/sections/AdminTaskStageTimeline.vue')

  assert.match(source, /<ol/)
  assert.match(source, /<li/)
  assert.match(source, /:aria-current=/)
})

test('admin task run card should render prioritized task actions plus detail toggle', () => {
  const source = readSource('views/admin/sections/AdminTaskRunCard.vue')

  assert.match(source, /actionDefinitions/)
  assert.match(source, /v-for="action in actionDefinitions"/)
  assert.doesNotMatch(source, /cardPresentation\\.actionSummary/)
})
```

- [ ] **Step 2: 跑前端相关测试，确认新增用例先失败**

Run (from `frontend/`): `node --test tests/adminTaskRunPresentation.test.mjs tests/adminDashboardTaskActions.test.mjs tests/adminDashboardTaskCardsUi.test.mjs`

Expected:
- FAIL
- `buildTaskRunCardPresentation()` 还没有 `stageTimelineItems`
- `getTaskActionDefinitions()` 仍返回多个动作
- `AdminTaskStageTimeline.vue` 文件不存在

- [ ] **Step 3: 用 ui-ux-pro-max 约束实现阶段轨迹与动作优先级**

先新建语义化阶段轨迹组件 `frontend/src/views/admin/sections/AdminTaskStageTimeline.vue`。保持现有 admin shell 的视觉语言，不换站点字体，只落 `ui-ux-pro-max` 要求的紧凑信息层级、语义元素和动态 ARIA：

```vue
<template>
  <ol class="grid grid-cols-2 gap-2 lg:grid-cols-4" aria-label="任务阶段">
    <li
      v-for="item in items"
      :key="item.key"
      class="rounded-2xl border px-3 py-2 text-sm"
      :class="item.state === 'current'
        ? 'border-sky-300 bg-sky-50 text-sky-900'
        : item.state === 'done'
        ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
        : 'border-slate-200 bg-slate-50 text-slate-500'"
      :aria-current="item.state === 'current' ? 'step' : undefined"
    >
      <span class="block text-xs font-medium uppercase tracking-[0.12em]">{{ item.label }}</span>
      <span class="mt-1 block text-xs">{{ item.caption }}</span>
    </li>
  </ol>
</template>

<script setup>
defineProps({
  items: { type: Array, required: true }
})
</script>
```

然后在 `frontend/src/views/admin/adminTaskRunPresentation.js` 里基于 canonical `stage/live_metrics/final_metrics` 构建卡片数据：

```javascript
const STAGE_TIMELINE = [
  { key: 'submitted', label: '已提交', caption: '等待后台开始' },
  { key: 'collecting', label: '正在采集', caption: '采集源站页面与详情' },
  { key: 'persisting', label: '正在写入', caption: '写入数据库并生成结果' },
  { key: 'finalizing', label: '正在收尾', caption: '整理本次结果' }
]

const getCanonicalStage = (run = {}) => (
  String(run?.stage || run?.details?.stage || '').trim()
)

const getCanonicalMetrics = (run = {}) => {
  if (['success', 'failed', 'cancelled'].includes(run?.status)) {
    return run?.final_metrics || run?.details?.final_metrics || run?.metrics || {}
  }
  return run?.live_metrics || run?.details?.live_metrics || run?.metrics || {}
}

const buildStageTimelineItems = (run = {}) => {
  const currentStage = getCanonicalStage(run)
  const currentIndex = STAGE_TIMELINE.findIndex((item) => item.key === currentStage)

  return STAGE_TIMELINE.map((item, index) => ({
    ...item,
    state: currentIndex === -1
      ? 'upcoming'
      : index < currentIndex
      ? 'done'
      : index === currentIndex
      ? 'current'
      : 'upcoming'
  }))
}
```

同时把结果区、首屏事实和动作收窄：

```javascript
export function buildTaskRunCardPresentation(run = {}, options = {}) {
  const metrics = getCanonicalMetrics(run)
  const actionItems = getTaskActionDefinitions(run)

  return {
    title: run?.display_name || getTaskTypeLabel(run?.task_type || run?.taskType),
    statusLabel: getTaskStatusLabel(run, options),
    statusTone: getTaskStatusTone(run, options),
    surfaceTone: getTaskSurfaceTone(run, options),
    stageTimelineItems: buildStageTimelineItems(run),
    stageFacts: [
      { label: '最近更新', value: formatAdminDateTime(run?.finished_at || getTaskHeartbeatAt(run)) },
      { label: isRunningTaskStatus(run?.status) ? '已运行' : '耗时', value: formatAdminDurationMs(getTaskElapsedMs(run, options.nowTs)) }
    ].filter((item) => item.value && item.value !== '--'),
    resultTitle: getTaskResultTitle(run, buildTaskHeadlineResultItems({ ...run, metrics })),
    resultHint: getTaskResultHint({ ...run, metrics }, buildTaskHeadlineResultItems({ ...run, metrics }), { isStuck: false }),
    resultItems: buildTaskHeadlineResultItems({ ...run, metrics }),
    actionItems,
    actionSummary: null,
    detailSections: buildTaskDetailSections({ ...run, metrics }, options),
  }
}
```

最后在 `frontend/src/views/admin/adminDashboardTaskActions.js` 中把动作收口到“运行态单主动作，终态保留少量后续动作”：

```javascript
export const getTaskActionDefinitions = (run = {}) => {
  const taskType = run?.task_type || run?.taskType
  if (!canRetryTask(taskType)) return []

  if (
    CANCELABLE_TASK_TYPES.has(taskType)
    && ['queued', 'pending', 'running', 'processing'].includes(run?.status)
    && !run?.details?.cancel_requested_at
  ) {
    return [resolveActionDefinition(taskType, 'cancel')].filter(Boolean)
  }

  if (run?.status === 'failed') {
    return [resolveActionDefinition(taskType, 'retry')].filter(Boolean)
  }

  if (run?.status === 'success') {
    const actions = [resolveActionDefinition(taskType, 'rerun')].filter(Boolean)
    if (INCREMENTAL_ACTION_TASK_TYPES.has(taskType)) {
      actions.push(resolveActionDefinition(taskType, 'incremental'))
    }
    return actions
  }

  if (run?.status === 'cancelled') {
    const actions = [resolveActionDefinition(taskType, 'retry')].filter(Boolean)
    if (INCREMENTAL_ACTION_TASK_TYPES.has(taskType)) {
      actions.push(resolveActionDefinition(taskType, 'incremental'))
    }
    return actions
  }

  return []
}
```

在 `frontend/src/views/admin/sections/AdminTaskRunCard.vue` 中挂载阶段轨迹，删除 `actionSummary` notice，并把按钮区域改成“一个主按钮 + 详情切换”：

```vue
<script setup>
import AdminTaskStageTimeline from './AdminTaskStageTimeline.vue'

const actionDefinitions = computed(() => cardPresentation.value.actionItems || [])
</script>

<template>
  <section class="task-run-card__panel">
    <h4 class="text-sm font-semibold text-slate-900">当前阶段</h4>
    <AdminTaskStageTimeline class="mt-3" :items="cardPresentation.stageTimelineItems" />
    <AppFactList class="mt-3" :items="cardPresentation.stageFacts" :columns="2" tone="muted" compact />
  </section>

  <div class="flex shrink-0 flex-wrap items-center gap-2 lg:max-w-[220px] lg:justify-end">
    <AppActionButton
      v-for="action in actionDefinitions"
      :key="action.key"
      :label="action.label"
      :busy-label="action.busyLabel"
      :busy="isActionSubmitting(action.key)"
      :disabled="isAnyActionSubmitting"
      :variant="getActionButtonVariant(action.key)"
      size="sm"
      @click="handleTaskAction(action.key)"
    />
    <AppActionButton
      v-if="hasDetailContent"
      :label="isTaskExpanded(run.id) ? '收起详情' : '查看详情'"
      variant="neutral"
      size="sm"
      @click="toggleTaskExpanded(run.id)"
    />
  </div>
</template>
```

- [ ] **Step 4: 再跑前端相关测试**

Run (from `frontend/`): `node --test tests/adminTaskRunPresentation.test.mjs tests/adminDashboardTaskActions.test.mjs tests/adminDashboardTaskCardsUi.test.mjs`

Expected:
- PASS
- 任务卡开始使用 canonical stage timeline
- 运行态只保留一个主动作，终态只保留少量高价值后续动作
- 阶段轨迹组件使用语义化列表和动态 ARIA

- [ ] **Step 5: 提交前端任务卡改动**

```bash
git add frontend/src/views/admin/sections/AdminTaskStageTimeline.vue frontend/src/views/admin/adminTaskRunPresentation.js frontend/src/views/admin/adminDashboardTaskActions.js frontend/src/views/admin/sections/AdminTaskRunCard.vue frontend/tests/adminTaskRunPresentation.test.mjs frontend/tests/adminDashboardTaskActions.test.mjs frontend/tests/adminDashboardTaskCardsUi.test.mjs
git commit -m "refactor: 收口任务卡阶段轨迹与动作优先级层级" -m "主要变更：
- 在 ui-ux-pro-max 约束下新增阶段轨迹组件并按 canonical stage 渲染任务卡
- 将任务卡首屏收口为阶段轨迹、当前结果和受控的动作优先级
- 补齐前端 presentation、动作优先级与 UI 语义测试"
```

### Task 4: 更新交付口径并完成最终验证

**Files:**
- Modify: `docs/release-checklist.md`

- [ ] **Step 1: 先更新交付与发布清单**

把 `docs/release-checklist.md` 中仍然写着 `phase / progress / heartbeat_at` 的口径更新为 Phase 2 契约：

```md
- [ ] 管理页任务中心展示 canonical `status / stage / live_metrics / final_metrics`
- [ ] collecting 阶段只显示采集指标，不伪造结果数
- [ ] 运行态每个可操作状态只保留一个主动作，终态只保留少量高价值后续动作
- [ ] 前台 freshness 仍保持最近一次成功快照语义
```

- [ ] **Step 2: 跑后端完整验证**

Run: `python -m unittest discover -s tests -v`

Expected:
- PASS
- `test_admin_task_service`、`test_admin_api`、`test_scraper_service` 的 Phase 2 用例都通过
- 没有因 canonical stage 契约迁移导致旧测试回归

- [ ] **Step 3: 跑前端完整验证**

Run: `npm --prefix frontend run test`

Expected:
- PASS
- `adminTaskRunPresentation`、`adminDashboardTaskActions`、`adminDashboardTaskCardsUi` 的 Phase 2 用例通过
- 既有 Phase 1 文案与同步状态条测试不回退

- [ ] **Step 4: 跑前端构建验证**

Run: `npm --prefix frontend run build`

Expected:
- PASS
- 新增阶段轨迹组件和任务卡改动可正常构建

- [ ] **Step 5: 提交交付口径与最终收尾**

```bash
git add docs/release-checklist.md
git commit -m "docs: 更新任务中心 Phase 2 交付口径"
```

最终确认：

```bash
git status --short --branch
git log --oneline --decorate -5
```

Expected:
- 工作区干净
- 最近提交包含后端契约、抓取 collecting 指标、前端任务卡、交付口径四类改动
