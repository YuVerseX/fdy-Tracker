# 统一出站代理与管理台只读状态 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让抓取、附件下载、智能摘要整理和智能岗位识别统一走 `OUTBOUND_PROXY_URL` 指定的 HTTP/SOCKS5 代理，并在管理台系统设置区展示脱敏后的代理只读状态。

**Architecture:** 后端先补统一代理配置与校验，再抽一个公共 `httpx/OpenAI` 出站层，最后把抓取和 AI 链路都切到这层上。前端不新增设置页，只扩展现有系统设置区的 summary cards 和 facts，用只读方式展示代理状态、代理出口和影响范围。

**Tech Stack:** FastAPI, Pydantic Settings, httpx, OpenAI Python SDK, unittest, Vue 3, node:test, Vite

---

## File Structure

**Backend config and validation**
- Modify: `src/config.py`
- Modify: `.env.example`
- Modify: `requirements.txt`
- Test: `tests/test_config.py`

**Unified outbound transport**
- Create: `src/services/outbound_http_service.py`
- Modify: `src/scrapers/base.py`
- Test: `tests/test_base_scraper.py`
- Test: `tests/test_ai_analysis_service.py`

**AI integration and runtime status**
- Modify: `src/services/ai_analysis_service.py`
- Modify: `src/services/post_job_service.py`
- Test: `tests/test_ai_analysis_service.py`
- Test: `tests/test_post_job_service.py`

**Admin read-only runtime UI**
- Modify: `frontend/src/views/admin/useAdminDashboardState.js`
- Modify: `frontend/src/views/admin/adminDashboardSectionAdapters.js`
- Modify: `frontend/src/views/admin/sections/AdminSystemSection.vue`
- Modify: `frontend/src/views/AdminDashboard.vue`
- Test: `frontend/tests/adminDashboardSectionAdapters.test.mjs`
- Test: `frontend/tests/adminDashboardTaskCardsUi.test.mjs`

**Docs and release contract**
- Modify: `README.md`
- Modify: `tests/test_release_artifacts.py`

## Task 1: 补统一代理配置与依赖校验

**Files:**
- Modify: `src/config.py`
- Modify: `.env.example`
- Modify: `requirements.txt`
- Test: `tests/test_config.py`

- [ ] **Step 1: 先补配置层失败测试**

在 `tests/test_config.py` 追加三组用例，锁定代理配置契约：

```python
    def test_settings_should_parse_http_outbound_proxy_metadata(self):
        with patch.dict(
            os.environ,
            {
                "OUTBOUND_PROXY_URL": "http://127.0.0.1:7890",
            },
            clear=True,
        ):
            settings = Settings(_env_file=None)

        self.assertTrue(settings.OUTBOUND_PROXY_ENABLED)
        self.assertEqual(settings.OUTBOUND_PROXY_SCHEME, "http")
        self.assertEqual(settings.OUTBOUND_PROXY_DISPLAY, "127.0.0.1:7890")

    def test_settings_should_reject_unsupported_outbound_proxy_scheme(self):
        with patch.dict(
            os.environ,
            {
                "OUTBOUND_PROXY_URL": "ftp://127.0.0.1:21",
            },
            clear=True,
        ):
            with self.assertRaises(ValueError):
                Settings(_env_file=None)

    def test_settings_should_fail_when_socks_proxy_is_configured_without_socksio(self):
        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "socksio":
                raise ModuleNotFoundError("No module named 'socksio'")
            return real_import(name, *args, **kwargs)

        with patch.dict(
            os.environ,
            {
                "OUTBOUND_PROXY_URL": "socks5://127.0.0.1:40000",
            },
            clear=True,
        ), patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaises(ValueError):
                Settings(_env_file=None)
```

- [ ] **Step 2: 跑配置测试，确认新断言先失败**

Run:

```bash
python -m unittest tests.test_config -v
```

Expected:
- FAIL
- `Settings` 目前还没有 `OUTBOUND_PROXY_*` 配置与校验逻辑

- [ ] **Step 3: 在 `Settings` 中实现最小可用代理配置与依赖校验**

在 `src/config.py` 中加入新的配置项和只读属性，保持校验集中在配置层：

```python
from urllib.parse import urlsplit

OUTBOUND_PROXY_SUPPORTED_SCHEMES = {"http", "https", "socks5"}


class Settings(BaseSettings):
    OUTBOUND_PROXY_URL: str = ""

    @property
    def OUTBOUND_PROXY_ENABLED(self) -> bool:
        return bool((self.OUTBOUND_PROXY_URL or "").strip())

    @property
    def OUTBOUND_PROXY_SCHEME(self) -> str:
        proxy_url = (self.OUTBOUND_PROXY_URL or "").strip()
        if not proxy_url:
            return ""
        parsed = urlsplit(proxy_url)
        return parsed.scheme.lower()

    @property
    def OUTBOUND_PROXY_DISPLAY(self) -> str:
        proxy_url = (self.OUTBOUND_PROXY_URL or "").strip()
        if not proxy_url:
            return ""
        parsed = urlsplit(proxy_url)
        host = parsed.hostname or ""
        port = parsed.port
        return f"{host}:{port}" if host and port else host

    @field_validator("OUTBOUND_PROXY_URL", mode="before")
    @classmethod
    def validate_outbound_proxy_url(cls, value):
        proxy_url = str(value or "").strip()
        if not proxy_url:
            return ""

        parsed = urlsplit(proxy_url)
        scheme = parsed.scheme.lower()
        if scheme not in OUTBOUND_PROXY_SUPPORTED_SCHEMES:
            raise ValueError("OUTBOUND_PROXY_URL scheme 不受支持")
        if not parsed.hostname or not parsed.port:
            raise ValueError("OUTBOUND_PROXY_URL 必须包含 hostname 和 port")
        if scheme == "socks5":
            try:
                import socksio  # noqa: F401
            except ModuleNotFoundError as exc:
                raise ValueError("OUTBOUND_PROXY_URL 使用 SOCKS5 时必须安装 socksio") from exc
        return proxy_url
```

同时更新：

```text
# .env.example
OUTBOUND_PROXY_URL=
```

```text
# requirements.txt
socksio==1.0.0
```

- [ ] **Step 4: 重新跑配置测试，确认配置契约成立**

Run:

```bash
python -m unittest tests.test_config -v
```

Expected:
- PASS
- HTTP 代理元信息解析正确
- 非法 scheme 与缺失 `socksio` 的 SOCKS5 配置会明确失败

- [ ] **Step 5: 提交配置与依赖基础**

Run:

```bash
git add src/config.py .env.example requirements.txt tests/test_config.py
git commit -m "build: 增加统一出站代理配置基础"
```

Expected:
- Commit created with config, env sample, dependency, and tests together

## Task 2: 抽统一出站 transport 并接入抓取层

**Files:**
- Create: `src/services/outbound_http_service.py`
- Modify: `src/scrapers/base.py`
- Test: `tests/test_base_scraper.py`

- [ ] **Step 1: 先补抓取层 transport 测试**

在 `tests/test_base_scraper.py` 中新增用例，锁定抓取层必须复用统一 client 工厂，而不是直接 new `httpx.AsyncClient`：

```python
    async def test_fetch_should_use_shared_outbound_async_client_factory(self):
        request = httpx.Request("GET", "https://example.com/posts")
        response = httpx.Response(200, request=request, text="ok")
        fake_client = FakeAsyncClient([response], {"requests": []})

        with patch("src.scrapers.base.settings", self.settings), patch(
            "src.scrapers.base.build_outbound_async_client",
            return_value=fake_client,
        ) as mocked_factory:
            scraper = DummyScraper()
            result = await scraper.fetch("https://example.com/posts")

        self.assertEqual(result.status_code, 200)
        mocked_factory.assert_called_once()
```

再补一条工厂自身测试，建议直接写到 `tests/test_base_scraper.py`，先锁定 `trust_env=False` 和 `proxy` 透传：

```python
    def test_build_outbound_async_client_should_disable_trust_env_and_forward_proxy(self):
        with patch("src.services.outbound_http_service.settings.OUTBOUND_PROXY_URL", "http://127.0.0.1:7890"), patch(
            "src.services.outbound_http_service.httpx.AsyncClient"
        ) as mocked_async_client:
            build_outbound_async_client(timeout=12.0, follow_redirects=True)

        mocked_async_client.assert_called_once_with(
            timeout=12.0,
            follow_redirects=True,
            verify=True,
            proxy="http://127.0.0.1:7890",
            trust_env=False,
        )
```

- [ ] **Step 2: 跑抓取层测试，确认工厂缺失导致失败**

Run:

```bash
python -m unittest tests.test_base_scraper -v
```

Expected:
- FAIL
- `build_outbound_async_client` 尚不存在
- `BaseScraper.fetch()` 仍然直接调用 `httpx.AsyncClient`

- [ ] **Step 3: 新建统一出站工厂并切抓取层到新工厂**

创建 `src/services/outbound_http_service.py`，先实现够用的同步 / 异步工厂：

```python
import httpx

from src.config import settings


def build_outbound_http_client(
    *,
    timeout: float | httpx.Timeout | None = None,
    follow_redirects: bool = False,
    verify: bool = True,
) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=follow_redirects,
        verify=verify,
        proxy=(settings.OUTBOUND_PROXY_URL or "").strip() or None,
        trust_env=False,
    )


def build_outbound_async_client(
    *,
    timeout: float | httpx.Timeout | None = None,
    follow_redirects: bool = False,
    verify: bool = True,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=follow_redirects,
        verify=verify,
        proxy=(settings.OUTBOUND_PROXY_URL or "").strip() or None,
        trust_env=False,
    )
```

把 `src/scrapers/base.py` 的 `fetch()` 改成：

```python
from src.services.outbound_http_service import build_outbound_async_client

    async def fetch(self, url: str, method: str = "GET", **kwargs) -> httpx.Response:
        headers = self._build_request_headers(url, kwargs.pop("headers", {}))
        total_attempts = self.retry_count + 1

        for attempt in range(1, total_attempts + 1):
            try:
                async with build_outbound_async_client(
                    timeout=self.timeout,
                    follow_redirects=True,
                    verify=True,
                ) as client:
                    response = await client.request(method, url, headers=headers, **kwargs)
                response.raise_for_status()
                return response
```

- [ ] **Step 4: 重新跑抓取层测试，确认 transport 已统一**

Run:

```bash
python -m unittest tests.test_base_scraper -v
```

Expected:
- PASS
- `BaseScraper.fetch()` 通过共享工厂构建 client
- client 明确使用 `trust_env=False`

- [ ] **Step 5: 提交统一 transport 基础层**

Run:

```bash
git add src/services/outbound_http_service.py src/scrapers/base.py tests/test_base_scraper.py
git commit -m "feat: 抽取统一出站传输层并接入抓取请求"
```

Expected:
- Commit created with new service, scraper integration, and tests

## Task 3: 接入 AI 分析、岗位抽取与运行时状态

**Files:**
- Modify: `src/services/ai_analysis_service.py`
- Modify: `src/services/post_job_service.py`
- Test: `tests/test_ai_analysis_service.py`
- Test: `tests/test_post_job_service.py`

- [ ] **Step 1: 先补 AI 链路失败测试**

在 `tests/test_ai_analysis_service.py` 中追加两条用例：

```python
    def test_get_analysis_runtime_status_should_include_proxy_metadata(self):
        with patch("src.services.ai_analysis_service.OpenAI", object), \
             patch("src.services.ai_analysis_service.settings.AI_ANALYSIS_ENABLED", True), \
             patch("src.services.ai_analysis_service.settings.OPENAI_API_KEY", "test-key"), \
             patch("src.services.ai_analysis_service.settings.OPENAI_BASE_URL", ""), \
             patch("src.services.ai_analysis_service.settings.OUTBOUND_PROXY_URL", "socks5://127.0.0.1:40000"):
            runtime = get_analysis_runtime_status()

        self.assertTrue(runtime["proxy_enabled"])
        self.assertEqual(runtime["proxy_scheme"], "SOCKS5")
        self.assertEqual(runtime["proxy_display"], "127.0.0.1:40000")

    def test_get_openai_client_should_forward_shared_http_client(self):
        fake_http_client = MagicMock()
        fake_openai = MagicMock()

        with patch("src.services.ai_analysis_service.OpenAI", return_value=fake_openai) as mocked_openai, \
             patch("src.services.ai_analysis_service.build_openai_http_client", return_value=fake_http_client), \
             patch("src.services.ai_analysis_service.settings.OPENAI_API_KEY", "test-key"), \
             patch("src.services.ai_analysis_service.settings.OPENAI_BASE_URL", ""):
            client = get_openai_client()

        self.assertIs(client, fake_openai)
        self.assertIs(mocked_openai.call_args.kwargs["http_client"], fake_http_client)
```

在 `tests/test_post_job_service.py` 中补兼容网关路径断言，确认岗位抽取不再直接 `httpx.post(...)`：

```python
    def test_call_base_url_job_extraction_should_use_shared_outbound_http_client(self):
        post = SimpleNamespace(
            id=1,
            title="南京师范大学招聘公告",
            content="详见附件",
            fields=[],
            attachments=[],
            source=SimpleNamespace(name="江苏省人社厅"),
        )
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": '{"jobs": []}'}
                    ],
                }
            ]
        }
        fake_response.raise_for_status.return_value = None
        fake_client = MagicMock()
        fake_client.__enter__.return_value = fake_client
        fake_client.__exit__.return_value = False
        fake_client.post.return_value = fake_response

        with patch("src.services.post_job_service.build_outbound_http_client", return_value=fake_client):
            result = call_base_url_job_extraction(post, [])

        self.assertEqual(result, [])
        fake_client.post.assert_called_once()
```

- [ ] **Step 2: 跑 AI / 岗位抽取测试，确认现状还没复用统一 transport**

Run:

```bash
python -m unittest tests.test_ai_analysis_service tests.test_post_job_service -v
```

Expected:
- FAIL
- `get_analysis_runtime_status()` 目前没有代理元信息
- `get_openai_client()` 与岗位抽取兼容网关路径还没复用共享 transport

- [ ] **Step 3: 把 AI 与岗位抽取全部切到统一 transport**

先扩展 `src/services/outbound_http_service.py`，补 OpenAI SDK 专用工厂：

```python
def build_openai_http_client(
    *,
    timeout: float | httpx.Timeout | None = None,
) -> httpx.Client:
    return build_outbound_http_client(
        timeout=timeout,
        follow_redirects=False,
        verify=True,
    )
```

在 `src/services/ai_analysis_service.py` 中：

```python
from src.services.outbound_http_service import (
    build_openai_http_client,
    build_outbound_http_client,
)

def get_openai_client() -> OpenAI | None:
    if not settings.OPENAI_API_KEY or OpenAI is None:
        return None

    client_kwargs = {
        "api_key": settings.OPENAI_API_KEY,
        "http_client": build_openai_http_client(timeout=90.0),
    }
    if settings.OPENAI_BASE_URL:
        client_kwargs["base_url"] = settings.OPENAI_BASE_URL
    return OpenAI(**client_kwargs)
```

把兼容网关模式下的分析与 insight 改成：

```python
    with build_outbound_http_client(timeout=90.0) as client:
        response = client.post(
            f"{base_url}/v1/responses",
            headers={...},
            json={...},
        )
```

并扩展 runtime 返回：

```python
    return {
        "mode": mode,
        "analysis_enabled": analysis_enabled,
        "provider": ...,
        "model_name": ...,
        "openai_ready": openai_ready,
        "openai_configured": bool((settings.OPENAI_API_KEY or "").strip()),
        "openai_sdk_available": OpenAI is not None,
        "base_url_configured": bool(base_url),
        "base_url": base_url,
        "transport": "base_url_http" if base_url else "sdk_parse",
        "proxy_enabled": settings.OUTBOUND_PROXY_ENABLED,
        "proxy_scheme": (settings.OUTBOUND_PROXY_SCHEME or "").upper(),
        "proxy_display": settings.OUTBOUND_PROXY_DISPLAY,
        "proxy_scope": (
            "抓取、附件下载、智能摘要整理、智能岗位识别统一复用"
            if settings.OUTBOUND_PROXY_ENABLED else "未启用应用级代理"
        ),
    }
```

在 `src/services/post_job_service.py` 中同样改成复用 `build_outbound_http_client()` 和 `get_openai_client()`。

- [ ] **Step 4: 重新跑 AI / 岗位抽取测试**

Run:

```bash
python -m unittest tests.test_ai_analysis_service tests.test_post_job_service -v
```

Expected:
- PASS
- SDK 模式和兼容网关模式都复用统一 transport
- runtime 已携带代理只读状态

- [ ] **Step 5: 提交 AI 与 runtime 集成**

Run:

```bash
git add src/services/outbound_http_service.py src/services/ai_analysis_service.py src/services/post_job_service.py tests/test_ai_analysis_service.py tests/test_post_job_service.py
git commit -m "feat: 统一智能服务与岗位抽取的代理出口"
```

Expected:
- Commit created with AI integration, runtime metadata, and tests

## Task 4: 在系统设置区展示代理只读状态

**Files:**
- Modify: `frontend/src/views/admin/useAdminDashboardState.js`
- Modify: `frontend/src/views/admin/adminDashboardSectionAdapters.js`
- Modify: `frontend/src/views/admin/sections/AdminSystemSection.vue`
- Modify: `frontend/src/views/AdminDashboard.vue`
- Test: `frontend/tests/adminDashboardSectionAdapters.test.mjs`
- Test: `frontend/tests/adminDashboardTaskCardsUi.test.mjs`

- [ ] **Step 1: 先补前端状态展示测试**

在 `frontend/tests/adminDashboardSectionAdapters.test.mjs` 中补一条 section model 测试：

```javascript
test('buildSystemSectionModel should surface proxy status, exit, and scope in system settings', () => {
  const section = buildSystemSectionModel({
    schedulerForm: {
      enabled: true,
      intervalSeconds: 7200,
      defaultSourceId: 1,
      defaultMaxPages: 5,
      nextRunAt: '2026-03-31T10:00:00Z'
    },
    schedulerLoaded: true,
    schedulerLoading: false,
    schedulerSaving: false,
    sourceOptions: [
      { label: '江苏省人社厅', value: 1 }
    ],
    analysisRuntime: {
      proxy_enabled: true,
      proxy_scheme: 'SOCKS5',
      proxy_display: '127.0.0.1:40000',
      proxy_scope: '抓取、附件下载、智能摘要整理、智能岗位识别统一复用'
    }
  })

  assert.deepEqual(
    section.summaryCards.map((item) => item.label),
    ['当前状态', '下次运行', '默认范围', '代理状态', '代理出口']
  )
  assert.equal(section.summaryCards[3].value, '已启用')
  assert.equal(section.summaryCards[4].value, 'SOCKS5 · 127.0.0.1:40000')
  assert.ok(section.runtimeFacts.some((item) => item.label === '代理范围'))
})
```

在 `frontend/tests/adminDashboardTaskCardsUi.test.mjs` 中补静态源码断言，确保系统设置区实际消费这些字段：

```javascript
test('admin system section should render proxy runtime facts alongside scheduler facts', () => {
  const systemSectionSource = readSource('views/admin/sections/AdminSystemSection.vue')
  const dashboardSource = readSource('views/AdminDashboard.vue')

  assert.match(systemSectionSource, /runtimeFacts/)
  assert.match(dashboardSource, /:runtime-facts="dashboard\.systemSection\.runtimeFacts"/)
})
```

- [ ] **Step 2: 跑前端定向测试，确认系统设置区还没接代理状态**

Run:

```bash
cd frontend
node --test tests/adminDashboardSectionAdapters.test.mjs tests/adminDashboardTaskCardsUi.test.mjs
```

Expected:
- FAIL
- `buildSystemSectionModel()` 还未接收 `analysisRuntime`
- `AdminSystemSection.vue` 还没有渲染代理运行事实

- [ ] **Step 3: 把 runtime 代理状态接到系统设置区**

在 `frontend/src/views/admin/useAdminDashboardState.js` 中给系统设置区传 `analysisRuntime`：

```javascript
  const systemSection = computed(() => buildSystemSectionModel({
    schedulerForm: forms.scheduler,
    schedulerLoaded: loaded.scheduler,
    schedulerLoading: loading.scheduler,
    schedulerSaving: loading.schedulerSaving,
    schedulerConfigError: state.schedulerConfigError,
    sourceOptions: sourceOptions.value,
    analysisRuntime: analysisRuntime.value
  }))
```

在 `frontend/src/views/admin/adminDashboardSectionAdapters.js` 中扩展 section model：

```javascript
export function buildSystemSectionModel({
  schedulerForm,
  schedulerLoaded,
  schedulerLoading,
  schedulerSaving,
  schedulerConfigError,
  sourceOptions,
  analysisRuntime
} = {}) {
  const proxyEnabled = Boolean(analysisRuntime?.proxy_enabled)
  const proxyScheme = String(analysisRuntime?.proxy_scheme || '').trim()
  const proxyDisplay = String(analysisRuntime?.proxy_display || '').trim()
  const proxyScope = String(analysisRuntime?.proxy_scope || '').trim()

  const summaryCards = [
    ...existingCards,
    {
      label: '代理状态',
      value: proxyEnabled ? '已启用' : '未启用',
      meta: proxyEnabled ? '整个服务的外部请求统一复用当前代理。' : '当前仍按默认出口访问外部服务。'
    },
    {
      label: '代理出口',
      value: proxyEnabled && proxyDisplay
        ? `${proxyScheme || 'HTTP'} · ${proxyDisplay}`
        : '未启用',
      meta: proxyEnabled ? '展示的是脱敏后的代理出口。' : '配置 OUTBOUND_PROXY_URL 后会在这里显示。'
    }
  ]

  const runtimeFacts = proxyScope
    ? [{ label: '代理范围', value: proxyScope }]
    : []

  return {
    ...existingState,
    summaryCards,
    runtimeFacts
  }
}
```

在 `frontend/src/views/admin/sections/AdminSystemSection.vue` 中把事实列表改成 `scheduleFacts + runtimeFacts`：

```vue
const props = defineProps({
  // ...
  summaryCards: { type: Array, required: true },
  runtimeFacts: { type: Array, default: () => [] },
})

const scheduleFacts = computed(() => [
  {
    label: '默认数据源',
    value: props.sourceOptions.find((source) => Number(source.value) === Number(props.schedulerForm.defaultSourceId))?.label || '默认数据源'
  },
  {
    label: '抓取间隔',
    value: props.schedulerLoaded ? `${props.schedulerForm.intervalSeconds || '--'} 秒` : '加载中'
  },
  {
    label: '默认抓取页数',
    value: props.schedulerLoaded ? `${props.schedulerForm.defaultMaxPages || '--'} 页` : '加载中'
  },
  {
    label: '下次预计运行',
    value: props.schedulerLoaded ? getSummaryCardValue('下次运行') : '加载中'
  },
  ...props.runtimeFacts
])
```

在 `frontend/src/views/AdminDashboard.vue` 中把新 prop 往下传：

```vue
        <AdminSystemSection
          :scheduler-form="dashboard.systemSection.schedulerForm"
          :scheduler-loaded="dashboard.systemSection.schedulerLoaded"
          :scheduler-loading="dashboard.systemSection.schedulerLoading"
          :scheduler-saving="dashboard.systemSection.schedulerSaving"
          :source-options="dashboard.systemSection.sourceOptions"
          :status-badge-label="dashboard.systemSection.statusBadgeLabel"
          :summary-cards="dashboard.systemSection.summaryCards"
          :runtime-facts="dashboard.systemSection.runtimeFacts"
          :helper-notice="dashboard.systemSection.helperNotice"
```

- [ ] **Step 4: 重新跑前端定向测试并做一次构建**

Run:

```bash
cd frontend
node --test tests/adminDashboardSectionAdapters.test.mjs tests/adminDashboardTaskCardsUi.test.mjs
npm run build
```

Expected:
- PASS
- 系统设置区同时显示 scheduler 信息和代理只读状态
- 前端构建通过

- [ ] **Step 5: 提交系统设置区 UI 接入**

Run:

```bash
git add frontend/src/views/admin/useAdminDashboardState.js frontend/src/views/admin/adminDashboardSectionAdapters.js frontend/src/views/admin/sections/AdminSystemSection.vue frontend/tests/adminDashboardSectionAdapters.test.mjs frontend/tests/adminDashboardTaskCardsUi.test.mjs
git commit -m "feat: 在系统设置区展示代理运行状态"
```

Expected:
- Commit created with UI state wiring and tests

## Task 5: 补部署文档与最终验证

**Files:**
- Modify: `README.md`
- Modify: `tests/test_release_artifacts.py`

- [ ] **Step 1: 先补文档静态测试**

在 `tests/test_release_artifacts.py` 增加对 README 的静态断言，锁定新环境变量说明不会丢：

```python
README_PATH = REPO_ROOT / "README.md"


    def test_readme_should_document_outbound_proxy_examples(self):
        content = README_PATH.read_text(encoding="utf-8")
        self.assertIn("OUTBOUND_PROXY_URL", content)
        self.assertIn("http://127.0.0.1:7890", content)
        self.assertIn("socks5://127.0.0.1:40000", content)
        self.assertIn("SOCKS5", content)
```

- [ ] **Step 2: 跑文档测试，确认 README 还没写代理说明**

Run:

```bash
python -m unittest tests.test_release_artifacts -v
```

Expected:
- FAIL
- README 还没有统一出站代理说明

- [ ] **Step 3: 在 README 增加部署说明**

在 `README.md` 的环境变量 / VPS 部署部分加入一小节：

```markdown
### 统一出站代理（可选）

如果你的 VPS 已经提供本地 HTTP / SOCKS5 代理端口，可以通过 `OUTBOUND_PROXY_URL` 让抓取、附件下载、智能摘要整理、智能岗位识别统一走该出口：

示例：

    OUTBOUND_PROXY_URL=http://127.0.0.1:7890

或：

    OUTBOUND_PROXY_URL=socks5://127.0.0.1:40000

说明：

- 未配置时，服务保持默认直连行为。
- 当使用 `socks5` 时，运行环境必须安装 `socksio`。
- 管理台“系统设置”区会显示当前代理状态和脱敏后的代理出口。
```

- [ ] **Step 4: 跑最终定向验证**

Run:

```bash
python -m unittest tests.test_config tests.test_base_scraper tests.test_ai_analysis_service tests.test_post_job_service tests.test_release_artifacts -v
cd frontend
node --test tests/adminDashboardSectionAdapters.test.mjs tests/adminDashboardTaskCardsUi.test.mjs
npm run build
```

Expected:
- PASS
- 后端配置、抓取 transport、AI transport、README 文档、前端系统设置区展示全部通过

- [ ] **Step 5: 提交文档与最终验证结果**

Run:

```bash
git add README.md tests/test_release_artifacts.py
git commit -m "docs: 补充统一出站代理部署说明"
```

Expected:
- Commit created with README contract and static coverage

## Self-Review

### Spec coverage

- 配置、依赖、fail fast：Task 1
- 统一 `httpx/OpenAI` transport：Task 2、Task 3
- 抓取 / 附件 / AI / 岗位抽取全链路收口：Task 2、Task 3
- runtime 只读状态：Task 3
- 管理台系统设置区只读展示：Task 4
- README / 部署文档与静态验证：Task 5

### Placeholder scan

- 没有使用 `TODO` / `TBD`
- 每个任务都给出了具体文件、测试命令、预期输出和提交命令
- 所有新名字都在首次出现时定义

### Type consistency

- 统一配置名固定为 `OUTBOUND_PROXY_URL`
- runtime 字段固定为 `proxy_enabled`、`proxy_scheme`、`proxy_display`、`proxy_scope`
- 统一 transport 工厂名固定为 `build_outbound_http_client`、`build_outbound_async_client`、`build_openai_http_client`
