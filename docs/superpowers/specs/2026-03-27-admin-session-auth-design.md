# 管理台会话鉴权设计

## 背景

当前管理台后端直接对 `/api/admin/*` 使用 HTTP Basic Auth。

这套实现有 3 个直接问题：

- 浏览器收到 `401 + WWW-Authenticate: Basic` 后会弹原生登录窗口，和页面内登录表单冲突。
- 前端把 `Basic username:password` 编码后放进 `sessionStorage`，本质上还是把可用凭证放在浏览器侧。
- 前台列表页和详情页为了显示“最近后台成功任务”，也会请求 `/api/admin/*`，导致未登录访问会持续撞后台鉴权。

这次不是做完整用户系统，而是在保持“单管理员账号 + 环境变量配置”前提下，把后台登录改成显式会话登录，去掉浏览器原生 Basic 弹窗，并把前台对后台鉴权的耦合拆开。

## 目标

- 去掉浏览器原生 Basic Auth 弹窗。
- 管理台改成显式登录接口 + 签名会话 cookie + `HttpOnly`。
- 前端不再保存可直接使用的账号口令或 Bearer token。
- 保留现有 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 作为后台唯一账号来源。
- 前台公开页面不再依赖 `/api/admin/*`，未登录时也不产生后台鉴权噪音。
- 保持当前 `/admin` 单页入口，不新增独立登录路由。

## 非目标

- 不做多账号体系。
- 不做角色、权限、审计后台。
- 不做数据库持久化 session 存储。
- 不做跨域后台登录能力。
- 不做 JWT、refresh token、SSO。
- 不在这期引入复杂限流或账号锁定机制。

## 前提约束

- 部署前提为同域访问，或本地开发通过 Vite 代理把 `/api` 转发到后端。
- 管理台仍然只有 1 组后台账号密码，由环境变量控制。
- 当前阶段允许浏览器多标签页共享后台登录态，这是从前端 `sessionStorage` 切到 cookie 后的预期变化。

## 方案比较

### 方案 A：显式登录 + Bearer token 存 `sessionStorage`

优点：

- 后端改造面小。
- 前端交互改造相对直接。

缺点：

- 仍然把可用凭证放在前端。
- 只是把 Basic 头换成 Bearer，本质风险没有根治。

### 方案 B：显式登录 + 签名会话 cookie + `HttpOnly`

优点：

- 前端不再持有可直接复用的后台凭证。
- 浏览器不会再触发 Basic 原生登录窗口。
- 同域场景下实现简单，和当前部署方式匹配。
- 登出、过期、凭证轮换后的失效语义更清楚。

缺点：

- 后端要补会话配置和测试。
- cookie 会话需要重新梳理管理接口的状态码和公开摘要边界。

### 方案 C：JWT + 刷新机制

优点：

- 扩展性最好。

缺点：

- 对当前项目明显过度设计。
- 会引入额外刷新、吊销、存储和测试复杂度。

结论：本期采用方案 B。

## 总体方案

整体思路：

1. 后端新增独立的后台会话接口，负责登录、检查当前登录态、退出登录。
2. 后端使用签名会话 cookie 保存后台登录状态，不再使用 `HTTPBasic`。
3. `/api/admin/*` 业务接口统一改成“读会话 cookie 判定是否已登录”。
4. 前端管理页改成显式调用登录接口，不再向请求头注入 `Authorization`。
5. 前台列表页和详情页改读公开只读摘要接口，不再访问 `/api/admin/*`。

## 后端设计

### 配置项

保留现有：

- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`

新增：

- `ADMIN_SESSION_SECRET`
  - 用于签名 session cookie。
  - 生产环境必须显式配置。
- `ADMIN_SESSION_MAX_AGE_SECONDS`
  - 默认 `28800`，即 8 小时。

说明：

- 如果后台账号密码未配置，后台会话接口和管理接口继续返回 `503`。
- 如果 `ADMIN_SESSION_SECRET` 未配置，也返回 `503`，并明确提示后台会话鉴权未完成配置。

### 会话载荷

本期不落数据库 session 表，使用签名 cookie 保存最小会话信息：

- `username`
- `issued_at`
- `credential_fingerprint`

其中 `credential_fingerprint` 为当前 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD` 的派生指纹。

用途：

- 每次请求校验会话时，重新基于当前环境变量计算指纹。
- 如果管理员修改了后台账号或密码，旧会话立即失效，不需要等 cookie 自然过期。

### 中间件与依赖

在应用级增加 `SessionMiddleware`。

管理接口鉴权依赖从现在的 `require_admin_access(credentials=Depends(HTTPBasic(...)))` 改为：

- 从 `request.session` 读取后台会话。
- 校验 `username`、`issued_at`、`credential_fingerprint` 是否完整且有效。
- 失败时返回 `401`，不再返回 `WWW-Authenticate`。

状态码约定：

- `401`：未登录、会话过期、会话被篡改、后台凭证已轮换
- `503`：后台账号密码或会话密钥未配置

本期不引入 `403`。

### 新增接口

#### `POST /api/admin/session/login`

请求体：

```json
{
  "username": "string",
  "password": "string"
}
```

行为：

- 校验账号密码是否与环境变量一致。
- 成功时写入会话 cookie。
- 失败时返回 `401`。

响应：

```json
{
  "username": "yucheng",
  "expires_in_seconds": 28800
}
```

#### `GET /api/admin/session/me`

行为：

- 读取当前会话。
- 已登录返回当前账号名和剩余会话信息。
- 未登录返回 `401`。

响应：

```json
{
  "username": "yucheng",
  "authenticated": true
}
```

#### `POST /api/admin/session/logout`

行为：

- 清空后台会话 cookie。
- 幂等返回 `204`。

### cookie 策略

- `HttpOnly=true`
- `SameSite=Lax`
- `Path=/`
- `Max-Age=ADMIN_SESSION_MAX_AGE_SECONDS`
- `Secure`
  - 生产环境默认开启
  - 本地开发可在非 HTTPS 下关闭

说明：

- 由于本期明确不支持跨域后台登录，不为 cookie 会话开放跨域凭证能力。
- CORS 不能继续使用 `allow_origins=["*"] + allow_credentials=True` 这组配置；需要收敛成明确 origin 列表，至少覆盖本地开发地址和生产同域。

### 管理接口边界

`/api/admin/*` 继续承载后台操作，但拆成两组：

- 会话接口：`/api/admin/session/*`
  - 不挂全局后台鉴权依赖
- 管理业务接口：现有 `/api/admin/task-runs`、`/api/admin/scheduler-config` 等
  - 统一挂后台会话鉴权依赖

### 前台公开摘要接口

新增公开只读接口：

- `GET /api/posts/freshness-summary`

用途：

- 给前台列表页和详情页展示“最近后台成功任务”。
- 只返回公开展示所需的最小信息，不暴露后台运行中任务、调度配置和管理操作入口。

建议响应：

```json
{
  "latest_success_at": "2026-03-27T10:00:00+08:00",
  "latest_success_run": {
    "task_type": "scheduled_scrape",
    "task_label": "定时抓取"
  }
}
```

这部分数据可以复用现有任务摘要服务，但要在 API 层单独裁剪输出。

## 前端设计

### 管理页登录流

保留 `/admin` 单路由，不新增 `/admin/login`。

页面流程调整为：

1. 初次进入 `/admin` 时先请求 `GET /api/admin/session/me`。
2. 若返回 `200`，进入已登录态并拉取后台概览数据。
3. 若返回 `401`，显示现有后台登录表单。
4. 用户提交表单时调用 `POST /api/admin/session/login`。
5. 登录成功后清空密码输入框，刷新后台概览数据。
6. 点击退出时调用 `POST /api/admin/session/logout`，然后回到未登录态。

### 前端状态管理

`frontend/src/api/posts.js` 里的以下逻辑删除或重写：

- `encodeBasicToken`
- `readAdminAuth`
- `setCredentials`
- `hasCredentials`
- 通过 interceptor 给 `/api/admin/*` 注入 `Authorization`

替换为：

- `login(username, password)`
- `logout()`
- `getSession()`

Axios 默认开启同源 cookie 发送；若本地代理场景需要显式设置，则统一在实例上配置。

### 管理页交互约束

- 登录失败只在页面内提示“账号或密码错误”，不再出现浏览器原生弹窗。
- `503` 单独解释为“后台鉴权配置未完成”或“后台会话配置未完成”，不直接等同于登录失败。
- 保留“当前账号”回显。
- 登录成功、会话失效、退出登录时都清空密码输入框。

### 前台页面调整

`PostList.vue` 和 `PostDetail.vue` 不再请求 `/api/admin/task-runs/summary` 和 `/api/admin/task-runs`。

改为：

- 只请求 `GET /api/posts/freshness-summary`
- 如果接口不可用或返回空数据，只隐藏“最近后台成功任务”展示，不影响前台浏览流程

这样可以把“前台浏览”与“后台登录态”彻底拆开。

## 安全与错误处理

### 本期安全基线

- 不在前端存储可直接复用的后台凭证。
- 使用 `HttpOnly` cookie 阻止前端脚本直接读取会话值。
- 使用 `credential_fingerprint` 确保后台口令轮换后旧会话自动失效。
- 管理接口统一返回结构化 JSON 错误，不再依赖浏览器内建鉴权流程。

### 本期暂不展开的项

- 登录失败限流
- 登录失败审计日志
- 独立 CSRF token 机制

原因：

- 当前前提是同域部署或本地代理，不支持跨域后台登录。
- 管理 API 为 JSON 接口，不接受浏览器普通表单直发。
- 本期先把 Basic Auth 替换掉，避免一次性把鉴权系统做得过重。

如果后续要开放跨域管理台、嵌入式管理页或更长会话，需要补充：

- CSRF 令牌
- 登录失败限流
- 更细的会话吊销策略

## 测试设计

### 后端单测

至少补以下场景：

- 登录成功后拿到有效会话
- 错误账号或密码返回 `401`
- 未登录访问管理接口返回 `401`
- 已登录访问管理接口返回 `200`
- 退出登录后再次访问管理接口返回 `401`
- `ADMIN_USERNAME` / `ADMIN_PASSWORD` 未配置时返回 `503`
- `ADMIN_SESSION_SECRET` 未配置时返回 `503`
- 修改后台口令后，旧会话因 `credential_fingerprint` 不匹配而失效

### 前端验证

至少覆盖以下流程：

- 管理页初次进入未登录时显示登录表单
- 登录成功后进入管理台并正常拉数据
- 登录失败只显示页面内错误提示
- 退出后回到未登录态
- 前台列表页和详情页正常展示公开摘要，且未登录不触发后台鉴权错误

### 手工回归

- 打开 `/admin`，确认浏览器不再弹原生认证窗口
- 登录成功后刷新 `/admin`，确认登录态仍有效
- 退出登录后刷新 `/admin`，确认回到登录表单
- 打开首页和详情页，确认不会再因为后台未登录而触发后台 `401`

## 影响文件

后端：

- `src/config.py`
- `src/main.py`
- `src/api/admin.py`
- `src/api/posts.py`
- `tests/test_admin_api.py`
- 可能新增管理会话 helper 模块

前端：

- `frontend/src/api/posts.js`
- `frontend/src/views/AdminDashboard.vue`
- `frontend/src/views/PostList.vue`
- `frontend/src/views/PostDetail.vue`

文档：

- `README.md`
- `.env.example`
- 部署文档中关于后台登录的说明

## 实施顺序

推荐按以下顺序落地：

1. 先补后端会话接口与鉴权依赖测试。
2. 再改后端管理接口和公开摘要接口。
3. 再改前端管理页登录流和前台摘要调用。
4. 最后补 README、部署文档和回归验证。

## 决策摘要

- 采用显式登录接口 + `HttpOnly` cookie 会话。
- 不做 JWT，不做多账号，不做跨域后台登录。
- 管理接口继续只认单管理员账号，但鉴权载体从 Basic 头改成会话 cookie。
- 前台公开页不再请求 `/api/admin/*`，改走公开摘要接口。
