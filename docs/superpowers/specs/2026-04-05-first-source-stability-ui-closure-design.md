# 第一源稳定性与 UI 收口设计

## 背景

当前版本已经具备“第一源可演示、可本地使用”的主链路，但审查中仍发现几类会影响继续迭代的真实问题：

- 后端部分状态口径不真实，存在“看起来健康/可终止，实际上并非如此”的问题
- 管理台部分失败路径会被渲染成正常或空数据，容易误导判断
- 公开页错误恢复路径不闭环，真实用户在部分异常场景下会被卡住
- 发布与 smoke 口径有缺口，可能把坏版本提前暴露到 GHCR

本轮目标不是把项目改造成多源平台，也不是把部署提升到生产级，而是把“第一源稳定继续迭代”的底座收口。

## 目标

本轮完成后，项目应满足以下目标：

1. 第一源抓取、健康检查、后台任务中心、公开列表/详情页在单实例场景下语义真实、行为可预期。
2. 管理台不能把失败状态伪装成“系统没问题”或“当前无数据”。
3. 公开页在常见错误场景下有明确恢复路径，不依赖用户自行刷新或猜测。
4. 发布与 smoke 口径足以支持继续开发和 VPS 部署更新，不把明显坏版本提前发布到外部镜像仓库。

## 非目标

以下内容明确不在本轮范围内：

- 多数据源平台化改造
- 真实生产级监控、告警、权限体系、HTTPS 终止
- 浏览器级 E2E 测试体系建设
- PR 阶段完整 Docker compose smoke 普及
- 本地 24h 长跑验证

说明：

- 当前环境没有 Docker，因此本轮不把本地 24h 长跑作为验收门槛。
- 24h 长跑改为 VPS 部署更新后的观察项，用于补充运行证据，而不是阻塞当前代码收口。

## 设计原则

### 1. 先修“说假话”的系统行为

优先修复会让系统状态失真的问题，而不是先做样式或结构优化。包括：

- 健康检查误报 ready
- 抓取任务表面支持 cancel，实际无法终止
- 配置加载失败却仍允许保存默认值
- 任务加载失败却显示成“还没有任务记录”

### 2. 只做当前第一源必需的最小充分修正

不借本轮顺手引入多源平台抽象，也不扩展到更重的架构重构。所有修改都围绕当前第一源、单实例、继续迭代的可用性展开。

### 3. 验证优先于表述

没有验证证据，不声称“稳定”。本轮以回归测试、前端构建、定向用例和 VPS 上线后的观察作为证据链。

## 工作包

## 工作包 A：后端运行语义收口

### A1. 修正 scheduler readiness 语义

当前问题：

- `scheduler.running=False` 时仍可能返回 `ready=true`
- 抓取 job 丢失时也可能返回 `status=ok, ready=true`

本轮要求：

- 当调度配置为启用状态时，如果调度器未运行，`scheduler.ready` 必须为 `false`
- 当调度配置为启用状态且抓取 job 未注册时，`scheduler.ready` 必须为 `false`
- 顶层 `/api/health.ready` 继续由 `database.ready && scheduler.ready` 决定
- 仍保留“新部署但尚未首轮成功抓取”时可 `status=degraded, ready=true` 的语义，但前提是调度器本身真的在运行

涉及文件：

- `src/scheduler/jobs.py`
- `src/api/health.py`
- `tests/test_health_api.py`
- `tests/test_scheduler_jobs.py`
- `tests/test_smoke_deployment.py`

### A2. 收口抓取任务的 cancel 契约

当前问题：

- 抓取任务可被提交 cancel 请求
- 但抓取 runner 和 `scrape_and_save()` 实际不支持取消

设计决策：

- 本轮不实现真正的抓取中断
- 本轮改为“撤回对抓取任务的 cancel 暴露”，只保留真正支持取消的任务类型

原因：

- 真正的抓取取消需要在 scraper、详情抓取、写库循环和任务 runner 上统一插入取消检查点，风险和变更范围都明显超出本轮目标
- 对第一源稳定性来说，先让 UI 和 API 不再承诺一个做不到的能力，更稳妥

涉及文件：

- `src/services/admin_task_service.py`
- `src/api/admin.py`
- 相关后端测试
- 管理台任务动作展示逻辑

### A3. 统一 source-scoped 补处理入口校验

当前问题：

- `run-scrape` 会校验 source 是否存在/启用
- 其他带 `source_id` 的补处理任务不会，可能把无效 source 吞成 0-count success

本轮要求：

- `backfill-attachments` 在收到 `source_id` 时，继续复用与抓取同等级别的 readiness 校验
- `backfill-base-analysis`、`run-job-extraction` 在收到 `source_id` 时，至少要校验 source 存在，但允许对已停用 source 的历史记录继续补处理

原因：

- 附件补处理仍属于抓取结果补全，依赖当前 source 处于可用状态
- 基础分析和岗位提取本质上是历史内容再处理，不应因为 source 后续停用就阻断补处理入口

涉及文件：

- `src/api/admin.py`
- 对应测试文件

## 工作包 B：管理台真实可用性收口

### B1. 修复活跃任务状态的运行时错误

当前问题：

- `useAdminDashboardState.js` 中直接使用 `isRunningTaskStatus`
- 但没有导入，存在真实运行时异常

本轮要求：

- 修复导入
- 增加覆盖这条路径的测试，避免再次出现“构建通过但页面真实运行报错”

涉及文件：

- `frontend/src/views/admin/useAdminDashboardState.js`
- 相关前端测试

### B2. 配置读取失败时禁止误保存默认值

当前问题：

- scheduler 配置加载失败后，表单仍保留可提交默认值
- 管理员继续点保存会把默认值误写回后台

本轮要求：

- 在配置尚未成功加载时，系统设置保存按钮不可用
- 或显式进入“配置读取失败，需重新加载后才能保存”的状态
- 前端文案需要清楚告知原因

涉及文件：

- `frontend/src/views/admin/adminDashboardDataService.js`
- `frontend/src/views/admin/useAdminDashboardState.js`
- `frontend/src/views/admin/sections/AdminSystemSection.vue`
- 相关前端测试

### B3. 任务记录加载失败不能再伪装成空态

当前问题：

- task runs 请求失败后，UI 会展示“先运行一次任务”
- 实际上可能是接口失败、鉴权丢失或后端异常

本轮要求：

- 将“加载失败”和“确实为空”分成两个独立状态
- 失败态需提供刷新或重试动作
- 空态只在成功加载且确实为空时展示

涉及文件：

- `frontend/src/views/admin/adminDashboardDataService.js`
- `frontend/src/views/admin/sections/AdminTaskRunsSection.vue`
- 相关前端测试

### B4. 为动态反馈补最低限度可访问性语义

当前问题：

- `AppNotice` 承载了登录失败、保存结果、任务提交反馈、freshness 提示等动态信息
- 但没有 `role` / `aria-live`

本轮要求：

- `AppNotice` 增加可配置的播报语义
- 错误和失败场景至少具备 `alert` 类语义
- 普通状态更新至少具备 `status` 类语义

涉及文件：

- `frontend/src/components/ui/AppNotice.vue`
- 相关使用位置

## 工作包 C：公开页错误恢复闭环

### C1. 列表页异常恢复

本轮要求：

- 列表页异常时，文案与动作一致
- 不再只给“重新加载”但文案暗示“返回上一页”
- 对于非法页码、失效筛选等场景，提供明确回到有效列表状态的动作

### C2. 详情页异常恢复

本轮要求：

- 详情页 404 时提供直接回列表动作
- “返回列表”按钮改为确定性回到列表路由，不依赖浏览器历史长度推断

### C3. 公告类型筛选不自锁

本轮要求：

- 公告类型下拉选项不能因当前已选类型而塌缩
- 统计摘要和筛选选项来源要解耦，保证用户可以切换到其他类型

涉及文件：

- `frontend/src/views/post-list/usePostListState.js`
- `frontend/src/views/PostList.vue`
- `frontend/src/views/PostDetail.vue`
- `frontend/src/utils/postFilters.js`
- 相关前端测试

## 工作包 D：发布与验证口径收口

### D1. 修正 GHCR 发布顺序

当前问题：

- 当前 workflow 先 push 正式标签，再跑 GHCR smoke

本轮要求：

- 先构建并推送候选 tag
- 用候选 tag 跑 GHCR smoke
- smoke 通过后再 promote 到正式 tag

如果当前 workflow 不适合做真正的 tag promote，则至少要确保：

- `latest`
- release tag

不会在 smoke 前对外暴露

### D2. 让本地 smoke 文档自包含

本轮要求：

- `docs/test-strategy.md`
- `docs/release-checklist.md`

明确说明执行 smoke 前需要的 `.env` 或环境变量前置条件，至少包括：

- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `ADMIN_SESSION_SECRET`
- `ADMIN_SESSION_SECURE`
- `API_DOCS_ENABLED`

## 验收标准

本轮完成后，应满足以下验收标准：

1. 后端完整回归继续通过。
2. 前端测试和构建继续通过。
3. `/api/health` 在调度器未运行或抓取 job 丢失时，不能再返回误导性的 `ready=true`。
4. 管理台不再暴露对抓取任务的伪 cancel 能力。
5. source-scoped 补处理入口对无效 source 给出明确错误，而不是 0-count success。
6. 管理台活跃任务路径不再出现运行时错误。
7. scheduler 配置加载失败时，不能保存前端默认值回后台。
8. 任务记录加载失败时，不能渲染成“当前无任务记录”。
9. 公开列表页与详情页的错误恢复路径闭环。
10. GHCR 正式标签不会在 smoke 前暴露。
11. smoke 文档可被本地或 VPS 运维按说明复现。

## 本轮验证策略

### 本地必须执行

- `python -m unittest discover -s tests -v`
- `python scripts/check_ci_logs.py backend-tests.log --label backend-tests`
- `cd frontend && npm test`
- `cd frontend && npm run build`

### 定向补充验证

- 健康检查与 scheduler readiness 定向测试
- 管理台运行态与错误态定向测试
- 列表/详情错误恢复定向测试
- 发布 workflow 的静态规则检查或最小单元级验证

### 本轮不做

- 本地 Docker compose smoke
- 本地 24h 长跑

## 部署后观察项

本轮代码合入后，在 VPS 更新镜像并部署后执行观察：

1. 确认 `/api/health`、首页、`/admin`、后台登录闭环正常。
2. 观察至少一个定时抓取周期，确认 `next_run_at`、freshness、任务记录推进正常。
3. 若条件允许，再进行更长时间观察，但不作为本轮本地收口门槛。

## 风险与取舍

### 已接受的风险

- 本轮不实现真正的抓取任务取消，只收口伪能力暴露
- 本轮不建设浏览器级 E2E
- 本轮不建设生产级部署保证

### 不接受的风险

- 后端状态说假话
- 管理台把失败伪装成空态或正常态
- 公开页让用户卡死在错误页
- GHCR 把坏版本提前暴露为正式标签

## 结论

这轮收口完成后，项目仍然是“第一源稳定基线”，不是生产就绪版本，也不是多源平台版本；但它应当足以作为后续继续迭代的可靠底座。
