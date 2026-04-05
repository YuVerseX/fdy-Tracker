# Result Notice Public List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the public list default to `招聘公告`, keep `结果公示` available only through explicit event-type filtering, and ensure result notices never show `岗位待整理`.

**Architecture:** Keep the change narrow. Frontend request builders gain an implicit default `event_type=招聘公告` for list and stats calls, while the event-type option request intentionally omits that implicit default so `结果公示` remains selectable. Backend leaves analysis and classification unchanged, but normalizes `record_completeness.jobs` for `结果公示` away from `pending`; frontend also adds a small defensive guard so list/detail badges never render `岗位待整理` for result notices even if the payload drifts.

**Tech Stack:** FastAPI + SQLAlchemy, Vue 3 Composition API, Node built-in test runner, Python `unittest`

---

## File Map

- Modify: `frontend/src/utils/postFilters.js`
  Responsibility: build public-list request params and encode the implicit default event type without leaking it into the route query.
- Modify: `frontend/tests/postFilters.test.mjs`
  Responsibility: verify list/stats params default to `招聘公告` and option params stay unfiltered.
- Modify: `src/api/posts.py`
  Responsibility: normalize `record_completeness.jobs` for result notices so they no longer look like pending job extraction work.
- Modify: `tests/test_api.py`
  Responsibility: verify list/detail API payloads stop marking result notices as `jobs=pending`.
- Modify: `frontend/src/utils/postDetailPresentation.js`
  Responsibility: centralize the UI guard that suppresses pending-job copy for `结果公示`.
- Modify: `frontend/tests/postListPresentation.test.mjs`
  Responsibility: verify result-notice list cards do not show `岗位待整理` even if completeness drifts.
- Modify: `frontend/tests/postDetailPresentation.test.mjs`
  Responsibility: verify result-notice detail tags and notes do not show pending-job copy even if completeness drifts.

### Task 1: Make Public List Requests Default To `招聘公告`

**Files:**
- Modify: `frontend/src/utils/postFilters.js`
- Test: `frontend/tests/postFilters.test.mjs`

- [ ] **Step 1: Write the failing frontend param tests**

Add these tests to `frontend/tests/postFilters.test.mjs`:

```js
import {
  buildEventTypeOptionParams,
  buildPostParams,
  buildStatsParams,
  DEFAULT_COUNSELOR_SCOPE
} from '../src/utils/postFilters.js'

test('buildPostParams should default to 招聘公告 when eventType is not explicitly selected', () => {
  const params = buildPostParams({
    filters: {
      gender: '',
      education: '',
      location: '',
      eventType: '',
      counselorScope: DEFAULT_COUNSELOR_SCOPE,
      hasContent: false
    },
    defaultCounselorScope: DEFAULT_COUNSELOR_SCOPE
  })

  assert.equal(params.event_type, '招聘公告')
  assert.equal(params.is_counselor, true)
})

test('buildStatsParams should default to 招聘公告 when eventType is not explicitly selected', () => {
  const params = buildStatsParams({
    filters: {
      gender: '',
      education: '',
      location: '',
      eventType: '',
      counselorScope: DEFAULT_COUNSELOR_SCOPE,
      hasContent: false
    },
    defaultCounselorScope: DEFAULT_COUNSELOR_SCOPE
  })

  assert.equal(params.event_type, '招聘公告')
  assert.equal(params.is_counselor, true)
})
```

- [ ] **Step 2: Run the frontend param test to verify it fails**

Run:

```bash
cd frontend
node --test tests/postFilters.test.mjs
```

Expected: FAIL with an assertion similar to `undefined !== '招聘公告'`.

- [ ] **Step 3: Implement the implicit default event-type helper**

Update `frontend/src/utils/postFilters.js` with this structure:

```js
export const DEFAULT_COUNSELOR_SCOPE = 'any'
export const DEFAULT_PUBLIC_EVENT_TYPE = '招聘公告'

const normalizeSearchQuery = (searchQuery = '') => String(searchQuery || '').trim()

const resolveEventTypeFilter = (filters = {}, { includeImplicitDefault = true } = {}) => {
  const explicitEventType = String(filters.eventType || '').trim()
  if (explicitEventType) {
    return explicitEventType
  }
  return includeImplicitDefault ? DEFAULT_PUBLIC_EVENT_TYPE : ''
}

const applySharedFilters = (
  params,
  filters = {},
  searchQuery = '',
  { includeImplicitDefaultEventType = true } = {}
) => {
  const normalizedSearch = normalizeSearchQuery(searchQuery)

  if (normalizedSearch) {
    params.search = normalizedSearch
  }

  if (filters.gender) {
    params.gender = filters.gender
  }

  if (filters.education) {
    params.education = filters.education
  }

  if (filters.location) {
    params.location = filters.location
  }

  const eventType = resolveEventTypeFilter(filters, {
    includeImplicitDefault: includeImplicitDefaultEventType
  })
  if (eventType) {
    params.event_type = eventType
  }

  if (filters.hasContent) {
    params.has_content = true
  }

  return params
}

export const buildEventTypeOptionParams = ({
  days = 7,
  searchQuery = '',
  filters = {},
  defaultCounselorScope = DEFAULT_COUNSELOR_SCOPE
} = {}) => {
  const params = { days }
  applySharedFilters(
    params,
    { ...filters, eventType: '' },
    searchQuery,
    { includeImplicitDefaultEventType: false }
  )
  applyCounselorScopeFilter(
    params,
    filters.counselorScope || defaultCounselorScope,
    defaultCounselorScope
  )
  return params
}
```

- [ ] **Step 4: Run the frontend param test again**

Run:

```bash
cd frontend
node --test tests/postFilters.test.mjs
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/postFilters.js frontend/tests/postFilters.test.mjs
git commit -m "fix: 默认列表按招聘公告口径请求"
```

### Task 2: Stop Marking Result Notices As Pending Job Extraction In API Payloads

**Files:**
- Modify: `src/api/posts.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing API contract tests**

Add these tests to `tests/test_api.py` inside `PostsApiTestCase`:

```python
def test_get_posts_should_not_mark_result_notice_jobs_as_pending(self):
    response = self.client.get("/api/posts", params={"search": "拟聘用人员名单公示"})

    self.assertEqual(response.status_code, 200)
    payload = response.json()
    item = payload["items"][0]
    self.assertEqual(item["analysis"]["event_type"], "结果公示")
    self.assertEqual(item["record_completeness"]["jobs"], "missing")

def test_get_post_detail_should_not_mark_result_notice_jobs_as_pending(self):
    response = self.client.get("/api/posts/5")

    self.assertEqual(response.status_code, 200)
    payload = response.json()
    self.assertEqual(payload["analysis"]["event_type"], "结果公示")
    self.assertEqual(payload["record_completeness"]["jobs"], "missing")
```

- [ ] **Step 2: Run the targeted API tests to verify they fail**

Run:

```bash
python -m unittest -v tests.test_api.PostsApiTestCase.test_get_posts_should_not_mark_result_notice_jobs_as_pending tests.test_api.PostsApiTestCase.test_get_post_detail_should_not_mark_result_notice_jobs_as_pending
```

Expected: FAIL with an assertion similar to `'pending' != 'missing'`.

- [ ] **Step 3: Special-case result notices in `build_record_completeness`**

Update `src/api/posts.py` like this:

```python
def build_record_completeness(post: Post, *, attachments_loaded: bool) -> dict[str, str]:
    """显式告诉前端当前记录完整到什么程度。"""
    job_index_state = get_post_job_index_state(post)
    if job_index_state["has_displayable_jobs"]:
        jobs_status = "available"
    elif is_result_notice_post(post):
        jobs_status = "missing"
    elif job_index_state["pending_extraction"]:
        jobs_status = "pending"
    else:
        jobs_status = "missing"

    return {
        "content": "available" if bool((post.content or "").strip()) else "missing",
        "summary": "available" if has_record_summary(post) else "missing",
        "jobs": jobs_status,
        "attachments": (
            "available" if bool(getattr(post, "attachments", None)) else "missing"
        ) if attachments_loaded else "unknown",
    }
```

- [ ] **Step 4: Run the targeted API tests again**

Run:

```bash
python -m unittest -v tests.test_api.PostsApiTestCase.test_get_posts_should_not_mark_result_notice_jobs_as_pending tests.test_api.PostsApiTestCase.test_get_post_detail_should_not_mark_result_notice_jobs_as_pending
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/api/posts.py tests/test_api.py
git commit -m "fix: 结果公示不再标记岗位待整理"
```

### Task 3: Add A Frontend Guard So Result Notices Never Render Pending-Job Copy

**Files:**
- Modify: `frontend/src/utils/postDetailPresentation.js`
- Test: `frontend/tests/postListPresentation.test.mjs`
- Test: `frontend/tests/postDetailPresentation.test.mjs`

- [ ] **Step 1: Write the failing presentation regression tests**

Add this test to `frontend/tests/postListPresentation.test.mjs`:

```js
test('buildPostCardView should suppress 岗位待整理 for result notices when completeness drifts', () => {
  const view = buildPostCardView({
    title: '某高校拟聘用人员名单公示',
    publish_date: '2026-04-02',
    source: { name: '江苏省人力资源和社会保障厅' },
    is_counselor: true,
    counselor_scope: 'dedicated',
    has_content: true,
    record_completeness: {
      content: 'available',
      summary: 'available',
      jobs: 'pending',
      attachments: 'unknown'
    },
    record_provenance: {
      summary_source: 'ai',
      job_sources: []
    },
    analysis: {
      event_type: '结果公示'
    }
  })

  assert.ok(view.badges.some((item) => item.label === 'AI 整理'))
  assert.ok(view.badges.some((item) => item.label === '结果公示'))
  assert.ok(view.badges.every((item) => item.label !== '岗位待整理'))
})
```

Add this test to `frontend/tests/postDetailPresentation.test.mjs`:

```js
test('buildHeroTags and buildSourceNotes should suppress pending-job copy for result notices when completeness drifts', () => {
  const postData = {
    analysis: {
      event_type: '结果公示'
    },
    record_completeness: {
      content: 'available',
      summary: 'available',
      jobs: 'pending',
      attachments: 'unknown'
    },
    record_provenance: {
      summary_source: 'ai',
      job_sources: []
    }
  }

  const tags = buildHeroTags(postData, [])
  const notes = buildSourceNotes(postData, [])

  assert.ok(tags.every((item) => item.label !== '岗位待整理'))
  assert.ok(notes.every((item) => !/岗位信息仍在整理中/.test(item)))
})
```

- [ ] **Step 2: Run the presentation tests to verify they fail**

Run:

```bash
cd frontend
node --test tests/postListPresentation.test.mjs tests/postDetailPresentation.test.mjs
```

Expected: FAIL because `getRecordCompletenessFlags()` currently treats any `jobs === 'pending'` as pending, regardless of `event_type`.

- [ ] **Step 3: Implement the result-notice guard in the shared completeness helper**

Update `frontend/src/utils/postDetailPresentation.js`:

```js
export function getRecordCompletenessFlags(postData = {}) {
  const completeness = postData?.record_completeness || {}
  const provenance = postData?.record_provenance || {}
  const contentMissing = completeness.content === 'missing'
  const summaryMissing = completeness.summary === 'missing' || normalizeText(provenance.summary_source) === 'none'
  const eventType = normalizeText(postData?.analysis?.event_type || postData?.event_type)
  const isResultNotice = eventType === '结果公示'

  return {
    contentAvailable: !contentMissing && (
      completeness.content === 'available' ||
      Boolean(postData?.has_content) ||
      Boolean(normalizeText(postData?.content))
    ),
    contentMissing,
    summaryMissing,
    jobsPending: completeness.jobs === 'pending' && !isResultNotice
  }
}
```

- [ ] **Step 4: Run the presentation tests again**

Run:

```bash
cd frontend
node --test tests/postListPresentation.test.mjs tests/postDetailPresentation.test.mjs
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/postDetailPresentation.js frontend/tests/postListPresentation.test.mjs frontend/tests/postDetailPresentation.test.mjs
git commit -m "fix: 前台隐藏结果公示的岗位待整理提示"
```

### Task 4: Run Focused Regression And Build Verification

**Files:**
- Test: `tests/test_api.py`
- Test: `frontend/tests/postFilters.test.mjs`
- Test: `frontend/tests/postListPresentation.test.mjs`
- Test: `frontend/tests/postDetailPresentation.test.mjs`
- Test: `frontend/tests/postListCopy.test.mjs`

- [ ] **Step 1: Run the focused backend regression**

Run:

```bash
python -m unittest -v tests.test_api
```

Expected: PASS.

- [ ] **Step 2: Run the focused frontend regression suite**

Run:

```bash
cd frontend
node --test tests/postFilters.test.mjs tests/postListPresentation.test.mjs tests/postDetailPresentation.test.mjs tests/postListCopy.test.mjs
```

Expected: PASS.

- [ ] **Step 3: Run the frontend production build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS with a completed Vite build and generated `dist/` output.

- [ ] **Step 4: Check the final diff stays within agreed scope**

Run:

```bash
git log -3 --oneline
```

Expected: the latest three commits should correspond to the frontend default event-type helper, the API completeness contract adjustment, and the frontend result-notice presentation guard.

- [ ] **Step 5: Confirm the working tree is clean after the task commits**

```bash
git status --short
```

Expected: no output.
