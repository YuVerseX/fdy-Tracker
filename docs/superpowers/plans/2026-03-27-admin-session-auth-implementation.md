# 管理台会话鉴权 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把管理台从 HTTP Basic Auth 迁移到显式登录 + 签名会话 cookie，并把前台“最近后台成功任务”改成公开只读摘要，彻底去掉浏览器原生登录弹窗和前台的后台鉴权噪音。

**Architecture:** 后端在应用级加 `SessionMiddleware`，后台会话通过 `POST /api/admin/session/login`、`GET /api/admin/session/me`、`POST /api/admin/session/logout` 管理；原 `/api/admin/*` 业务接口统一改成读取 session。前台新增公开 `GET /api/posts/freshness-summary`，让 `PostList.vue` 和 `PostDetail.vue` 不再依赖后台登录态。前端管理页继续保留 `/admin` 单页入口，只替换登录流和状态恢复方式。

**Tech Stack:** FastAPI, Starlette SessionMiddleware, SQLAlchemy, Vue 3, Axios, unittest, Vite

---

### Task 1: 后端会话鉴权基础

**Files:**
- Modify: `src/config.py`
- Modify: `src/main.py`
- Modify: `src/api/admin.py`
- Test: `tests/test_admin_api.py`

- [ ] **Step 1: 先补后台会话契约测试**

在 `tests/test_admin_api.py` 里把 Basic 头断言替换成 session 场景，至少补这 5 个用例：

```python
from starlette.middleware.sessions import SessionMiddleware

def _build_app():
    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key="test-session-secret",
        same_site="lax",
        https_only=False,
        max_age=28800,
    )
    app.include_router(admin_api.router, prefix="/api")
    return app

def test_admin_session_login_sets_cookie_and_returns_username(self):
    response = self.client.post(
        "/api/admin/session/login",
        json={"username": "admin", "password": "secret-pass"},
    )
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()["username"], "admin")
    self.assertIn("session=", response.headers.get("set-cookie", ""))

def test_admin_session_me_requires_login(self):
    response = self.client.get("/api/admin/session/me")
    self.assertEqual(response.status_code, 401)

def test_admin_route_requires_session_instead_of_basic_header(self):
    response = self.client.get("/api/admin/task-runs")
    self.assertEqual(response.status_code, 401)
    self.assertNotIn("www-authenticate", {key.lower(): value for key, value in response.headers.items()})

def test_admin_route_accepts_cookie_after_login(self):
    login_response = self.client.post(
        "/api/admin/session/login",
        json={"username": "admin", "password": "secret-pass"},
    )
    self.assertEqual(login_response.status_code, 200)
    response = self.client.get("/api/admin/task-runs")
    self.assertEqual(response.status_code, 200)

def test_admin_session_logout_clears_access(self):
    self.client.post("/api/admin/session/login", json={"username": "admin", "password": "secret-pass"})
    logout_response = self.client.post("/api/admin/session/logout")
    self.assertEqual(logout_response.status_code, 204)
    response = self.client.get("/api/admin/task-runs")
    self.assertEqual(response.status_code, 401)
```

- [ ] **Step 2: 运行后台鉴权测试，确认现状失败**

Run: `python -m unittest -v tests.test_admin_api`

Expected:
- `/api/admin/session/login` 和 `/api/admin/session/me` 目前是 `404`
- 旧测试里仍然依赖 Basic `Authorization`
- 至少有 1 个用例明确暴露“还没切到 session 鉴权”

- [ ] **Step 3: 增加配置项并把应用切到 SessionMiddleware**

在 `src/config.py` 增加会话和 CORS 配置，在 `src/main.py` 里替换通配符 CORS，并挂 `SessionMiddleware`。

`src/config.py` 目标片段：

```python
ADMIN_SESSION_SECRET: str = ""
ADMIN_SESSION_MAX_AGE_SECONDS: int = 28800
ADMIN_SESSION_SECURE: bool = False
CORS_ALLOWED_ORIGINS: str = "http://127.0.0.1:5173,http://localhost:5173"

@property
def CORS_ALLOWED_ORIGIN_LIST(self) -> list[str]:
    return [
        item.strip()
        for item in self.CORS_ALLOWED_ORIGINS.split(",")
        if item.strip()
    ]
```

`src/main.py` 目标片段：

```python
from starlette.middleware.sessions import SessionMiddleware

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.ADMIN_SESSION_SECRET or "dev-session-secret",
    same_site="lax",
    https_only=settings.ADMIN_SESSION_SECURE,
    max_age=settings.ADMIN_SESSION_MAX_AGE_SECONDS,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGIN_LIST,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 4: 在 `src/api/admin.py` 落会话接口和会话依赖**

把 `HTTPBasic` 相关代码替换成“检查配置 + 读写 `request.session`”。

目标结构：

```python
import hashlib

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status

router = APIRouter()
session_router = APIRouter(prefix="/admin/session", tags=["后台会话"])
protected_router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin_access)])
router.include_router(session_router)
router.include_router(protected_router)

class AdminSessionLoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)

def _build_admin_credential_fingerprint() -> str:
    expected_username = (settings.ADMIN_USERNAME or "").strip()
    expected_password = (settings.ADMIN_PASSWORD or "").strip()
    session_secret = (settings.ADMIN_SESSION_SECRET or "").strip()
    payload = f"{expected_username}\n{expected_password}\n{session_secret}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

def _ensure_admin_auth_configured() -> tuple[str, str]:
    expected_username = (settings.ADMIN_USERNAME or "").strip()
    expected_password = (settings.ADMIN_PASSWORD or "").strip()
    session_secret = (settings.ADMIN_SESSION_SECRET or "").strip()
    if not expected_username or not expected_password:
        raise HTTPException(status_code=503, detail="后台鉴权还没配置，请先设置 ADMIN_USERNAME 和 ADMIN_PASSWORD。")
    if not session_secret:
        raise HTTPException(status_code=503, detail="后台会话鉴权还没配置，请先设置 ADMIN_SESSION_SECRET。")
    return expected_username, expected_password

def require_admin_access(request: Request) -> str:
    expected_username, _ = _ensure_admin_auth_configured()
    admin_session = request.session.get("admin_auth") or {}
    if admin_session.get("username") != expected_username:
        raise HTTPException(status_code=401, detail="后台登录状态已失效，请重新登录。")
    if admin_session.get("credential_fingerprint") != _build_admin_credential_fingerprint():
        request.session.pop("admin_auth", None)
        raise HTTPException(status_code=401, detail="后台登录状态已失效，请重新登录。")
    return expected_username

@session_router.post("/login")
def login_admin_session(payload: AdminSessionLoginRequest, request: Request):
    expected_username, expected_password = _ensure_admin_auth_configured()
    if not _secure_compare_text(payload.username, expected_username) or not _secure_compare_text(payload.password, expected_password):
        raise HTTPException(status_code=401, detail="后台登录失败，请检查账号或密码。")
    request.session["admin_auth"] = {
        "username": expected_username,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "credential_fingerprint": _build_admin_credential_fingerprint(),
    }
    return {"username": expected_username, "authenticated": True, "expires_in_seconds": settings.ADMIN_SESSION_MAX_AGE_SECONDS}

@session_router.get("/me")
def get_admin_session(request: Request):
    username = require_admin_access(request)
    return {"username": username, "authenticated": True}

@session_router.post("/logout", status_code=204)
def logout_admin_session(request: Request, response: Response):
    request.session.pop("admin_auth", None)
    response.status_code = status.HTTP_204_NO_CONTENT
```

- [ ] **Step 5: 补齐缺失的配置异常与口令轮换测试**

在 `tests/test_admin_api.py` 再补这 2 组场景：

```python
def test_admin_session_login_returns_503_when_secret_missing(self):
    with patch.multiple("src.api.admin.settings", ADMIN_SESSION_SECRET=""):
        response = self.client.post(
            "/api/admin/session/login",
            json={"username": "admin", "password": "secret-pass"},
        )
    self.assertEqual(response.status_code, 503)

def test_admin_session_becomes_invalid_after_password_rotation(self):
    self.client.post("/api/admin/session/login", json={"username": "admin", "password": "secret-pass"})
    with patch.multiple("src.api.admin.settings", ADMIN_PASSWORD="new-secret-pass"):
        response = self.client.get("/api/admin/task-runs")
    self.assertEqual(response.status_code, 401)
```

- [ ] **Step 6: 再跑后台鉴权回归**

Run: `python -m unittest -v tests.test_admin_api`

Expected:
- 新增 session 登录/恢复/登出测试全部 PASS
- 旧的管理接口 happy path 继续 PASS
- 响应头里不再出现 `WWW-Authenticate: Basic`

- [ ] **Step 7: 提交这一阶段**

```bash
git add src/config.py src/main.py src/api/admin.py tests/test_admin_api.py
git commit -m "feat: add admin session auth flow"
```

### Task 2: 公开任务新鲜度摘要接口

**Files:**
- Modify: `src/services/admin_task_service.py`
- Modify: `src/api/posts.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: 先补公开摘要接口测试**

在 `tests/test_api.py` 里补 2 个接口测试，直接 patch 任务摘要服务，避免把这组测试绑到文件系统任务记录上：

```python
from unittest.mock import patch

@patch(
    "src.api.posts.get_task_summary",
    return_value={
        "latest_success_run": {
            "task_type": "scheduled_scrape",
            "status": "success",
            "finished_at": "2026-03-27T10:00:00+00:00",
        },
        "latest_success_at": "2026-03-27T10:00:00+00:00",
        "running_tasks": [{"task_type": "ai_analysis"}],
        "total_runs": 12,
    },
)
def test_get_freshness_summary_returns_public_latest_success(self, _mock_summary):
    response = self.client.get("/api/posts/freshness-summary")
    self.assertEqual(response.status_code, 200)
    payload = response.json()
    self.assertEqual(payload["latest_success_run"]["task_type"], "scheduled_scrape")
    self.assertEqual(payload["latest_success_run"]["task_label"], "定时抓取")
    self.assertNotIn("running_tasks", payload)
    self.assertNotIn("total_runs", payload)

@patch("src.api.posts.get_task_summary", return_value={"latest_success_run": None, "latest_success_at": None})
def test_get_freshness_summary_returns_empty_payload_when_no_success(self, _mock_summary):
    response = self.client.get("/api/posts/freshness-summary")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()["latest_success_run"], None)
```

- [ ] **Step 2: 运行 posts API 测试，确认现状失败**

Run: `python -m unittest -v tests.test_api`

Expected:
- `/api/posts/freshness-summary` 目前是 `404`
- 新用例失败，明确暴露公开摘要接口还不存在

- [ ] **Step 3: 在任务服务层抽公共序列化 helper**

在 `src/services/admin_task_service.py` 里把任务类型标签和公开摘要序列化收进服务层，避免 `posts.py` 依赖 `admin.py` 造成循环引用。

目标片段：

```python
TASK_TYPE_LABELS = {
    "manual_scrape": "手动抓取最新数据",
    "scheduled_scrape": "定时抓取",
    "attachment_backfill": "历史附件补处理",
    "duplicate_backfill": "历史去重补齐",
    "ai_analysis": "OpenAI 分析",
    "job_extraction": "岗位级抽取",
    "ai_job_extraction": "岗位级抽取",
}

def get_task_type_label(task_type: str) -> str:
    return TASK_TYPE_LABELS.get(task_type, task_type)

def serialize_public_task_freshness(summary: Dict[str, Any]) -> Dict[str, Any]:
    latest_success_run = summary.get("latest_success_run")
    if not latest_success_run:
        return {
            "latest_success_at": None,
            "latest_success_run": None,
        }
    return {
        "latest_success_at": summary.get("latest_success_at"),
        "latest_success_run": {
            "task_type": latest_success_run.get("task_type"),
            "task_label": get_task_type_label(latest_success_run.get("task_type") or ""),
            "finished_at": latest_success_run.get("finished_at"),
        },
    }
```

- [ ] **Step 4: 在 `src/api/posts.py` 暴露公开只读接口**

目标片段：

```python
from src.services.admin_task_service import get_task_summary, serialize_public_task_freshness

@router.get("/posts/freshness-summary")
def get_posts_freshness_summary():
    summary = get_task_summary()
    return serialize_public_task_freshness(summary)
```

- [ ] **Step 5: 跑 posts API 回归**

Run: `python -m unittest -v tests.test_api`

Expected:
- 新增 `freshness-summary` 用例 PASS
- 原有 `/api/posts`、`/api/posts/stats/summary`、详情页接口测试继续 PASS

- [ ] **Step 6: 提交这一阶段**

```bash
git add src/services/admin_task_service.py src/api/posts.py tests/test_api.py
git commit -m "feat: add public freshness summary api"
```

### Task 3: 前端 API 层切到会话接口

**Files:**
- Modify: `frontend/src/api/posts.js`
- Modify: `frontend/src/views/AdminDashboard.vue`

- [ ] **Step 1: 先把 API 层切换点写清楚**

在 `frontend/src/api/posts.js` 去掉基于 `sessionStorage` 的 Basic 凭证逻辑，只保留基于 cookie 的请求。

目标片段：

```javascript
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json'
  }
})

export const postsApi = {
  getPosts(params = {}) {
    return api.get('/api/posts', { params })
  },
  getStatsSummary(params = {}) {
    return api.get('/api/posts/stats/summary', { params })
  },
  getPostById(id) {
    return api.get(`/api/posts/${id}`)
  },
  getFreshnessSummary() {
    return api.get('/api/posts/freshness-summary')
  },
  healthCheck() {
    return api.get('/api/health')
  }
}

export const adminApi = {
  login(username, password) {
    return api.post('/api/admin/session/login', { username, password })
  },
  getSession() {
    return api.get('/api/admin/session/me')
  },
  logout() {
    return api.post('/api/admin/session/logout')
  },
  getTaskRuns(params = {}) {
    return api.get('/api/admin/task-runs', { params })
  },
  getTaskSummary() {
    return api.get('/api/admin/task-runs/summary')
  },
  getSources() {
    return api.get('/api/admin/sources')
  },
  getSchedulerConfig() {
    return api.get('/api/admin/scheduler-config')
  },
  updateSchedulerConfig(payload = {}) {
    return api.put('/api/admin/scheduler-config', payload)
  },
  runScrape(payload = {}) {
    return api.post('/api/admin/run-scrape', payload, { timeout: LONG_RUNNING_TIMEOUT })
  },
  backfillAttachments(payload = {}) {
    return api.post('/api/admin/backfill-attachments', payload, { timeout: LONG_RUNNING_TIMEOUT })
  },
  getAnalysisSummary() {
    return api.get('/api/admin/analysis-summary')
  },
  getInsightSummary() {
    return api.get('/api/admin/insight-summary')
  },
  getDuplicateSummary() {
    return api.get('/api/admin/duplicate-summary')
  },
  backfillDuplicates(payload = {}) {
    return api.post('/api/admin/backfill-duplicates', payload, { timeout: LONG_RUNNING_TIMEOUT })
  },
  runAiAnalysis(payload = {}) {
    return api.post('/api/admin/run-ai-analysis', payload, { timeout: LONG_RUNNING_TIMEOUT })
  },
  getJobSummary(params = {}) {
    return requestWithFallback([
      () => api.get('/api/admin/job-summary', { params }),
      () => api.get('/api/admin/jobs-summary', { params }),
      () => api.get('/api/admin/job-extraction-summary', { params })
    ])
  },
  runJobExtraction(payload = {}) {
    return requestWithFallback([
      () => api.post('/api/admin/run-job-extraction', payload, { timeout: LONG_RUNNING_TIMEOUT }),
      () => api.post('/api/admin/run-ai-job-extraction', payload, { timeout: LONG_RUNNING_TIMEOUT }),
      () => api.post('/api/admin/run-job-analysis', payload, { timeout: LONG_RUNNING_TIMEOUT })
    ])
  }
}
```

实现时删掉这些函数与常量：

```javascript
ADMIN_AUTH_STORAGE_KEY
getSessionStorage
encodeBasicToken
readAdminAuth
api.interceptors.request.use
setCredentials
clearCredentials
hasCredentials
getSavedUsername
```

- [ ] **Step 2: 改管理页登录、恢复和退出流程**

在 `frontend/src/views/AdminDashboard.vue` 改这 4 段逻辑：

```javascript
const adminSavedUsername = computed(() => adminAuthForm.value.username || '')

const handleAdminAccessError = (error) => {
  const status = error?.response?.status
  if (![401, 503].includes(status)) {
    return false
  }

  adminAuthorized.value = false
  adminAuthForm.value.password = ''
  clearAdminRuntimeState()

  if (status === 401) {
    adminAuthError.value = '后台登录状态已失效，请重新登录。'
  } else {
    adminAuthError.value = error?.response?.data?.detail || '后台会话鉴权暂不可用，请稍后再试。'
  }
  return true
}

const verifyAdminAccess = async () => {
  adminAuthChecking.value = true
  adminAuthError.value = ''
  try {
    const response = await adminApi.getSession()
    adminAuthorized.value = true
    adminAuthForm.value.username = response.data.username || adminAuthForm.value.username
    return true
  } catch (error) {
    if (!handleAdminAccessError(error)) {
      setFeedback('error', getErrorMessage(error, '后台登录验证失败'))
    }
    return false
  } finally {
    adminAuthChecking.value = false
  }
}

const submitAdminLogin = async () => {
  if (!adminAuthForm.value.username || !adminAuthForm.value.password) {
    adminAuthError.value = '请输入后台账号和密码。'
    return
  }

  adminAuthChecking.value = true
  adminAuthError.value = ''
  try {
    const response = await adminApi.login(adminAuthForm.value.username, adminAuthForm.value.password)
    adminAuthorized.value = true
    adminAuthForm.value.username = response.data.username || adminAuthForm.value.username.trim()
    adminAuthForm.value.password = ''
    await fetchSources()
    await refreshOverview()
  } catch (error) {
    if (!handleAdminAccessError(error)) {
      adminAuthError.value = getErrorMessage(error, '后台登录失败')
    }
  } finally {
    adminAuthChecking.value = false
  }
}

const logoutAdmin = async () => {
  try {
    await adminApi.logout()
  } finally {
    adminAuthorized.value = false
    adminAuthForm.value.password = ''
    clearAdminRuntimeState()
    setFeedback('success', '已退出后台登录')
  }
}
```

同时把原来依赖 `adminApi.getSavedUsername()` 的计算属性和初始化逻辑一起删掉，避免构建后还残留旧 API。

- [ ] **Step 3: 编译前端，确认没有旧接口残留**

Run: `npm run build`

Workdir: `F:\code\fdy-Tracker\frontend`

Expected:
- Vite build 成功
- 不再出现 `setCredentials`、`getSavedUsername`、`clearCredentials` 未定义错误

- [ ] **Step 4: 手工验证管理页登录流**

验证顺序：

1. 打开 `/admin`，未登录时只显示页面内登录表单。
2. 输入错误密码，只出现页面内错误提示。
3. 输入正确密码，进入管理台，浏览器不弹原生登录框。
4. 刷新 `/admin`，仍保持已登录态。
5. 点击退出，回到未登录态。

- [ ] **Step 5: 提交这一阶段**

```bash
git add frontend/src/api/posts.js frontend/src/views/AdminDashboard.vue
git commit -m "feat: switch admin ui to session login"
```

### Task 4: 前台改接公开摘要接口

**Files:**
- Modify: `frontend/src/views/PostList.vue`
- Modify: `frontend/src/views/PostDetail.vue`

- [ ] **Step 1: 去掉前台对后台管理接口的依赖**

把 `fetchLatestSuccessTask()` 从“先打 admin summary，再回退 task-runs”改成只打公开摘要接口。

`frontend/src/views/PostList.vue` 与 `frontend/src/views/PostDetail.vue` 都改成下面逻辑：

```javascript
const fetchLatestSuccessTask = async () => {
  freshnessLoading.value = true
  freshnessUnavailable.value = false
  latestSuccessTask.value = null

  try {
    const response = await postsApi.getFreshnessSummary()
    latestSuccessTask.value = normalizeSummaryResponse({
      latest_success_run: response.data?.latest_success_run || null,
      latest_success_at: response.data?.latest_success_at || null,
    })
  } catch (err) {
    freshnessUnavailable.value = true
    if (err?.response?.status && err.response.status !== 404) {
      console.warn('获取公开任务新鲜度失败:', err)
    }
  } finally {
    freshnessLoading.value = false
  }
}
```

同时删掉：

```javascript
import { postsApi, adminApi } from '../api/posts'
const isRestricted = (error) => [401, 403, 503].includes(error?.response?.status)
await adminApi.getTaskSummary()
await adminApi.getTaskRuns({ limit: 20 })
```

并把 import 改成：

```javascript
import { postsApi } from '../api/posts'
```

- [ ] **Step 2: 再跑前端构建**

Run: `npm run build`

Workdir: `F:\code\fdy-Tracker\frontend`

Expected:
- 前端构建继续 PASS
- `PostList.vue` 和 `PostDetail.vue` 不再依赖 `adminApi`

- [ ] **Step 3: 手工验证前台展示**

验证顺序：

1. 未登录后台时打开首页，不出现后台登录错误。
2. 未登录后台时打开详情页，不出现后台登录错误。
3. 公开摘要存在时，首页和详情页都能显示“最近后台成功任务”。
4. 公开摘要为空时，只隐藏该块，不影响主流程。

- [ ] **Step 4: 提交这一阶段**

```bash
git add frontend/src/views/PostList.vue frontend/src/views/PostDetail.vue
git commit -m "feat: use public freshness summary on public pages"
```

### Task 5: 文档收口与总回归

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.ghcr.yml`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/deploy-vps-docker.md`
- Modify: `docs/deploy-1panel-ghcr.md`

- [ ] **Step 1: 更新环境变量和部署文档**

至少补这些文档片段：

`.env.example`：

```env
# 管理台鉴权
ADMIN_USERNAME=
ADMIN_PASSWORD=
ADMIN_SESSION_SECRET=
ADMIN_SESSION_MAX_AGE_SECONDS=28800
ADMIN_SESSION_SECURE=false
CORS_ALLOWED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
```

`docker-compose.yml` / `docker-compose.ghcr.yml`：

```yaml
environment:
  ADMIN_USERNAME: ${ADMIN_USERNAME:-}
  ADMIN_PASSWORD: ${ADMIN_PASSWORD:-}
  ADMIN_SESSION_SECRET: ${ADMIN_SESSION_SECRET:-}
  ADMIN_SESSION_MAX_AGE_SECONDS: ${ADMIN_SESSION_MAX_AGE_SECONDS:-28800}
  ADMIN_SESSION_SECURE: ${ADMIN_SESSION_SECURE:-false}
  CORS_ALLOWED_ORIGINS: ${CORS_ALLOWED_ORIGINS:-http://127.0.0.1:5173,http://localhost:5173}
```

`README.md` / 部署文档：

```md
- 管理页改为页面内登录，不再使用浏览器原生 Basic Auth 弹窗
- 必填环境变量：`ADMIN_USERNAME`、`ADMIN_PASSWORD`、`ADMIN_SESSION_SECRET`
- 前端生产默认同域 `/api`，本地开发通过 Vite 代理
- 首页和详情页读取公开 `freshness-summary`，不需要后台登录
```

- [ ] **Step 2: 跑后端核心回归**

Run:

```bash
python -m unittest -v tests.test_api tests.test_admin_api tests.test_admin_task_service tests.test_scraper_service tests.test_attachment_service tests.test_duplicate_service tests.test_post_job_service tests.test_scheduler_jobs tests.test_parser tests.test_filter_service
```

Expected:
- 所有核心回归 PASS
- 管理台相关改动没有打坏 posts API 和任务服务

- [ ] **Step 3: 跑前端生产构建**

Run: `npm run build`

Workdir: `F:\code\fdy-Tracker\frontend`

Expected:
- 构建 PASS
- 产物正常生成到 `frontend/dist`

- [ ] **Step 4: 做最终手工验收**

验收清单：

1. `/admin` 正确登录、刷新、退出。
2. 浏览器全程不再弹原生认证窗口。
3. 首页与详情页在未登录后台时仍可正常浏览。
4. 首页与详情页可展示公开摘要，不再产生后台 `401` 噪音。
5. 修改 `ADMIN_PASSWORD` 后，旧登录态失效并要求重新登录。

- [ ] **Step 5: 提交最终收口**

```bash
git add docker-compose.yml docker-compose.ghcr.yml .env.example README.md docs/deploy-vps-docker.md docs/deploy-1panel-ghcr.md
git commit -m "docs: document admin session auth rollout"
```
