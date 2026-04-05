# 统一出站代理与管理台只读状态设计

## 背景

当前项目已经具备第一源抓取、基础整理、智能摘要整理和智能岗位识别的主链路，但所有外部请求仍然各走各的实现路径：

- 抓取层通过 `httpx.AsyncClient` 直接访问目标站点
- AI 分析与统计洞察在兼容网关模式下通过 `httpx.post` 直接访问外部接口
- AI 分析与岗位抽取在 SDK 模式下通过 `OpenAI(...)` 默认网络出口访问外部接口

用户当前的部署环境已经在 VPS 上提供本地 HTTP / SOCKS5 代理端口，希望让**整个服务的所有外部请求**统一走该代理出口，同时在管理台中看到当前代理是否启用、启用后走的是什么类型与出口，但**不需要**在项目里管理 `warp-cli` 或宿主机网络本身。

本轮目标不是做完整的“代理管理后台”，而是为当前单实例、第一源稳定版补上统一出站层与可核对的只读运行信息。

## 目标

本轮完成后，项目应满足以下目标：

1. 抓取、附件下载、智能摘要整理、智能岗位识别等所有外部请求统一复用一套代理配置。
2. 代理配置通过环境变量完成，不引入数据库配置和后台在线编辑。
3. 兼容 HTTP 代理与 SOCKS5 代理；当配置为 SOCKS5 时，依赖能力必须明确满足。
4. 管理台“系统设置”区展示代理是否启用、代理类型和脱敏后的代理出口，便于部署后核对。
5. 未配置代理时保持当前行为；已配置但非法时不允许悄悄回退为直连。

## 非目标

以下内容明确不在本轮范围内：

- 在项目内控制 `warp-cli`、宿主机路由或 Docker 网络
- 后台在线编辑代理地址、凭证、开关
- 后台联通性测试按钮、代理测速、代理健康探针
- 按域名、按任务类型或按数据源做多策略分流
- 多实例热更新代理配置

说明：

- 本轮只解决“应用如何统一走现成代理端口”，不解决“代理服务本身如何部署或运维”。
- 由于用户已明确希望“整个服务所有外部请求都走代理”，本轮不额外设计 target-level bypass 策略。

## 设计原则

### 1. 先做统一出口，再谈局部优化

不能继续在 AI、抓取、岗位抽取里分别塞代理参数。应先抽出统一出站层，再让各链路复用，避免后续多源扩展时重复散改。

### 2. 配置应显式、可预期

代理是否启用必须由项目配置显式决定，而不是隐式依赖宿主机的 `HTTP_PROXY`、`HTTPS_PROXY` 等环境变量。这样部署行为才可复现、可核对。

设计决策：

- 统一出站 client 默认使用 `trust_env=False`
- 仅当项目内显式配置 `OUTBOUND_PROXY_URL` 时，才使用应用级代理
- 若宿主机本身通过 WARP 改写默认出口路由，该行为仍可生效，因为这不依赖应用读取环境变量代理

### 3. 非法代理配置必须 fail fast

如果用户明确配置了代理，但配置值非法、协议不支持，或者 SOCKS5 缺少依赖，不应悄悄回退为直连。否则管理台会显示“已启用代理”，实际却没有经过代理，风险更高。

### 4. 管理台只展示运行事实，不暴露敏感信息

代理状态仅做只读展示，用于部署核对；不显示完整 URL、账号、密码、token，也不提供在线修改入口。

### 5. 保持现有后台信息语言

UI 延续当前后台“状态卡 + 事实列表 + 辅助说明”的信息组织方式，不新增重页面，不改变整体视觉语言，不把系统设置区变成网络配置台。

## 工作包

## 工作包 A：统一出站代理配置与校验

### A1. 新增统一出站配置项

在 `Settings` 中新增以下配置：

- `OUTBOUND_PROXY_URL`：默认空字符串，表示不启用应用级代理

衍生只读属性：

- `OUTBOUND_PROXY_ENABLED`
- `OUTBOUND_PROXY_SCHEME`
- `OUTBOUND_PROXY_DISPLAY`

约束：

- 支持的协议限定为 `http`、`https`、`socks5`
- `OUTBOUND_PROXY_DISPLAY` 仅返回 `host:port` 或可安全展示的最小必要信息
- 不向前端返回用户名、密码、query string 或完整 URL

### A2. 代理配置校验

本轮要求在启动时完成基础校验：

- `OUTBOUND_PROXY_URL` 为空时视为未启用，正常启动
- 非空时必须是可解析的 URL，且 scheme 在允许列表内
- 当 scheme 为 `socks5` 时，运行环境必须具备 `socksio`

设计决策：

- 若配置非法，`Settings` 初始化直接失败
- 若用户要走 SOCKS5，则将 `socksio` 作为明确依赖补入 `requirements.txt`

原因：

- 这是“全服务统一出站”的底座配置，不能容忍静默失效
- 对第一源稳定版来说，部署失败比“以为走了代理，实际没走”更容易定位和修复

涉及文件：

- `src/config.py`
- `requirements.txt`
- `.env.example`

## 工作包 B：统一 HTTP / SDK 出站层

### B1. 新增统一出站 client 工厂

新增单独模块，负责构建统一出站 client，避免在业务模块里重复拼接代理参数。

建议职责：

- 构建同步 `httpx.Client`
- 构建异步 `httpx.AsyncClient`
- 构建供 OpenAI SDK 复用的同步 `httpx.Client`
- 统一应用 timeout、follow redirects、verify、proxy、trust_env 等基础策略

设计决策：

- 所有工厂函数都从 `settings.OUTBOUND_PROXY_URL` 读取代理配置
- 默认 `trust_env=False`
- 未配置代理时返回“直连但仍受统一参数控制”的 client

建议文件：

- `src/services/outbound_http_service.py`

### B2. 收口抓取与附件下载链路

当前抓取层已经有统一入口 `BaseScraper.fetch()`，附件下载复用抓取器的 `fetcher` 能力，因此只需在抓取基类上收口即可覆盖：

- 列表抓取
- 详情抓取
- 附件下载

本轮要求：

- `BaseScraper.fetch()` 改为复用统一异步 client 工厂
- 不再在抓取基类里直接 new `httpx.AsyncClient(...)`

涉及文件：

- `src/scrapers/base.py`

### B3. 收口 AI 分析、洞察和岗位抽取链路

本轮要求统一覆盖以下三类路径：

1. `OPENAI_BASE_URL` 兼容网关模式下的 `httpx.post`
2. 直连 OpenAI SDK 模式下的 `OpenAI(...)`
3. 岗位级 AI 抽取链路

设计决策：

- 兼容网关模式下，改为使用统一同步 `httpx.Client`
- SDK 模式下，通过 `OpenAI(http_client=...)` 注入统一同步 client
- `OPENAI_BASE_URL` 与 `OUTBOUND_PROXY_URL` 相互独立：
  - `OPENAI_BASE_URL` 决定“请求发往哪个 AI endpoint”
  - `OUTBOUND_PROXY_URL` 决定“请求通过哪个代理出口出去”

这样无论是：

- 直连 `api.openai.com`
- 直连第三方兼容网关
- 本地反向代理到远端兼容网关

都能统一复用同一出站代理层。

涉及文件：

- `src/services/ai_analysis_service.py`
- `src/services/post_job_service.py`

## 工作包 C：运行时状态与管理台只读展示

### C1. 扩展运行时状态返回

当前 `analysis-summary.runtime` 已经承载“智能整理是否就绪、走 SDK 还是兼容网关”的运行时信息。本轮继续复用这一结构，新增代理只读状态，而不是额外再开独立接口。

新增字段建议：

- `proxy_enabled`
- `proxy_scheme`
- `proxy_display`
- `proxy_scope`

字段语义：

- `proxy_enabled`：当前应用级代理是否启用
- `proxy_scheme`：`HTTP` / `HTTPS` / `SOCKS5`
- `proxy_display`：脱敏后的出口标识，例如 `127.0.0.1:40000`
- `proxy_scope`：固定文案，表示“抓取、附件下载、智能摘要整理、智能岗位识别统一复用”

约束：

- 不返回完整代理 URL
- 不返回任何凭证信息
- 当代理未启用时，`proxy_display` 为空，`proxy_scope` 可留空或返回“未启用应用级代理”

涉及文件：

- `src/services/ai_analysis_service.py`

### C2. 管理台只读展示位置

代理状态不新增重页面，直接补到“系统设置”区 summary cards，原因如下：

- 这是部署级运行信息，和定时抓取配置同属于“系统默认行为”
- 当前系统设置区已有状态卡结构，适合补一到两张只读卡
- 不会把 AI 区和系统区的信息边界打乱

本轮 UI 要求：

- 保持现有浅色信息卡风格
- 新增两张 summary card：
  - `代理状态`：`已启用` / `未启用`
  - `代理出口`：`SOCKS5 · 127.0.0.1:40000` 或 `HTTP · 127.0.0.1:7890`
- 在 facts 区补一条：
  - `代理范围`：`抓取、附件下载、智能摘要整理、智能岗位识别`

展示原则：

- 文案直白，优先回答“是否启用、走什么、影响哪些链路”
- 不新增复杂 hover、设置弹窗、编辑表单
- 与当前后台“系统状态信息卡”视觉保持一致

涉及文件：

- `frontend/src/views/admin/useAdminDashboardState.js`
- `frontend/src/views/admin/adminDashboardSectionAdapters.js`
- `frontend/src/views/admin/sections/AdminSystemSection.vue`

## 工作包 D：文档与部署口径

### D1. 环境变量文档

本轮要求在 `.env.example` 和 README / 部署说明中明确：

- `OUTBOUND_PROXY_URL` 的用途
- 示例写法：
  - `OUTBOUND_PROXY_URL=http://127.0.0.1:7890`
  - `OUTBOUND_PROXY_URL=socks5://127.0.0.1:40000`
- 当使用 `socks5` 时，需要 `socksio`

### D2. 部署行为口径

本轮文档需明确区分：

- 宿主机级 WARP：项目无需配置 `OUTBOUND_PROXY_URL`，但仍可能经宿主机默认出口走 WARP
- 项目级代理：通过 `OUTBOUND_PROXY_URL` 强制服务所有外连统一走指定代理端口

这样可以避免后续把“宿主机网络出口”和“应用级显式代理”混为一谈。

## 错误处理与降级策略

### 1. 未配置代理

- 服务正常启动
- 保持当前直连行为
- 管理台显示“代理未启用”

### 2. 代理配置非法

- 服务启动失败
- 错误应指向具体配置项与非法原因

### 3. SOCKS5 依赖缺失

- 当且仅当配置了 `socks5` 时，若缺少 `socksio`，服务启动失败
- 不允许静默降级为直连或 HTTP 代理

### 4. 代理可用但远端请求失败

- 仍按各业务链路原有错误处理逻辑处理：
  - 抓取按现有 retry / error 路径
  - AI 分析继续按现有 fallback / warning 路径
- 本轮不额外实现代理级重试提示 UI

## 验证策略

本轮验收至少应覆盖以下验证：

1. 配置 `OUTBOUND_PROXY_URL` 为空时，现有抓取、AI 分析、AI 岗位抽取行为不回归。
2. 配置 HTTP 代理时，抓取链路与 AI 链路都能通过代理正常访问外部目标。
3. 配置 SOCKS5 代理时，若已安装 `socksio`，链路可正常工作。
4. 配置 SOCKS5 代理但缺失 `socksio` 时，启动应明确失败。
5. 管理台系统设置区能展示代理状态、代理出口和代理范围。
6. 管理台只展示脱敏值，不展示完整代理 URL 或凭证。

建议测试类型：

- 后端配置与运行时状态单元测试
- 抓取层 client 工厂定向测试
- 管理台 section adapter / 组件定向测试
- 必要时增加一条部署静态测试，确保 `.env.example` / 文档口径不漂移

## 验收标准

本轮完成后，应满足以下验收标准：

1. 所有外部请求统一复用同一套出站代理配置。
2. `OUTBOUND_PROXY_URL` 可显式控制是否启用应用级代理。
3. `http` / `https` / `socks5` 配置行为明确，依赖要求明确。
4. 管理台能准确反映代理是否启用、出口类型及适用范围。
5. 没有任何链路在“用户显式配置代理但代理失效”时悄悄回退为直连。

## 实施顺序建议

建议按以下顺序实现：

1. 补配置项、校验逻辑和依赖声明
2. 落统一出站 client 工厂
3. 收口抓取层
4. 收口 AI 分析 / 洞察 / 岗位抽取
5. 扩展 runtime 返回
6. 接入管理台系统设置区只读展示
7. 补定向测试与部署文档

原因：

- 先把底层配置与 transport 收口，能减少后续链路改造的返工
- UI 展示依赖 runtime 事实，放在后面更稳
