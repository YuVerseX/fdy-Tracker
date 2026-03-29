# 项目稳定化整改设计

## 背景

当前仓库已经打通了 `抓取 -> 解析 -> 附件补强 -> 岗位抽取 -> 去重 -> AI/规则分析 -> API -> 前端 -> 管理台` 主链路，具备本地使用和演示能力。

上一轮全项目审查确认了三个主要问题域：

1. 后端运行时治理不足，存在数据被覆盖、后台任务并发写冲突、状态语义失真等问题。
2. 前端公开页和管理页的主流程可用，但可访问性、滚动管理、加载反馈和状态可信度存在明显短板。
3. 部署与交付基线仍偏演示环境，默认 HTTPS、发布门禁、迁移治理、前端回归等能力不足。

本设计不追求“一次性重构整个项目”，而采用风险优先、分阶段收敛的方式完成整改。

## 目标

### 总目标

在不推翻现有架构的前提下，把项目从“可演示、可本地使用”提升到“数据一致性更可靠、页面体验更稳、交付基线更可控”的状态。

### 分阶段目标

#### Phase 1：后端一致性与运行时治理

- 防止 AI 岗位结果被普通抓取或附件补处理静默覆盖。
- 收紧后台任务互斥矩阵，避免多个任务并发改写同一批帖子状态。
- 修正前台 freshness 语义，只暴露“抓取新鲜度”，不混入 AI/岗位任务时间。
- 在任务提交前校验抓取 source 是否存在且启用，避免“成功但没做事”的假成功状态。
- 让 `DEBUG` 配置对异常环境变量更稳，不再因宿主环境污染直接阻断测试与启动。

#### Phase 2：前端可用性与页面质量

- 补齐列表页、详情页、管理页的关键 A11y 缺口。
- 明确路由滚动行为和异常路由兜底。
- 降低列表页搜索/筛选时的闪断感，改进加载与刷新反馈。
- 让管理台在真实数据返回前显示“未知/加载中”，而不是误导性的默认健康状态。

#### Phase 3：交付与部署基线

- 修正文档与实现不一致的问题。
- 收紧镜像发布门禁，降低 `latest` 漂移风险。
- 明确 HTTPS / cookie secure / 单机 SQLite 的边界和默认建议。
- 把最小前端自动回归纳入正式交付链路。

## 非目标

- 不在本轮整改中引入多数据源架构重构。
- 不在本轮整改中把 SQLite 全量迁移到 PostgreSQL。
- 不做前端全面视觉重设计，只修可验证的交互和信息质量问题。
- 不重写现有抓取、解析、AI 结果模型，只做边界修正和治理补强。

## 约束

- 必须尽量复用现有模块边界，不做无关大重构。
- 每个阶段都需要可独立验证，不能靠“后面一起修”兜底。
- 现有测试资产优先保留和扩展，不删已有回归。
- 当前工作区有用户未提交改动，整改实现时不得覆盖无关变更。

## 方案选择

本次采用“风险优先，分阶段收敛”方案，而不是一次性全修。

原因：

1. 后端一致性问题会直接影响数据正确性和任务结果，优先级高于页面体验。
2. 前端问题多数是体验和可信度问题，应该建立在后端状态语义正确的基础上修。
3. 部署和交付基线调整涉及文档、workflow、默认值，最好在业务和页面逻辑稳定后收尾。

因此执行顺序固定为：

`Phase 1 后端治理 -> Phase 2 前端可用性 -> Phase 3 交付与部署基线`

## 设计细节

### Phase 1：后端一致性与运行时治理

#### 1. 岗位结果写路径治理

当前 `replace_post_jobs()` 的策略是“整帖先删后写”，而 `sync_post_jobs(..., use_ai=False)` 在抓取和附件补处理链路里被大量复用。这会导致此前通过 AI 抽取得到的岗位在下一次普通重建时被抹掉。

本阶段采用“保留现有 AI 岗位，按运行模式选择合并策略”的方案：

- `use_ai=False` 时：
  - 重建本地岗位候选（附件/字段）。
  - 读取当前库里已有 AI 岗位。
  - 最终写入结果为：`本地岗位 + 已有 AI 岗位` 去重后的合并结果。
  - 普通抓取与附件补处理不得删除纯 AI 岗位。
- `use_ai=True` 时：
  - 重新生成本地岗位和 AI 岗位。
  - 最终写入结果为本轮完整合并结果，可以覆盖旧 AI 结果。

这样可以在不新增表结构的前提下，修复“非 AI 写路径覆盖 AI 结果”的核心问题。

#### 2. 后台任务互斥矩阵治理

当前互斥只覆盖抓取类任务，无法阻止多个会改帖子状态的任务同时运行。

本阶段将所有会改内容的后台任务统一归入一个互斥域 `content_mutation`，覆盖当前已有任务类型：

- `manual_scrape`
- `scheduled_scrape`
- `attachment_backfill`
- `duplicate_backfill`
- `ai_analysis`
- `job_extraction`（包含 `use_ai=true/false` 两种运行模式）

只读摘要和查询接口不创建任务记录，也不参与该互斥域。

实现口径：

- 所有会改 `posts / post_fields / attachments / post_jobs / post_analyses / post_insights / duplicate_*` 的后台任务统一互斥。
- 同一时刻只允许一个 `content_mutation` 任务运行。
- 冲突时返回明确的 409，并带当前运行任务类型。

该方案保守，但对当前 SQLite 单机架构最稳。

#### 3. Freshness 语义收口

当前 `/api/posts/freshness-summary` 复用了“最近一次成功任务”，会把 AI、岗位抽取、去重任务都混成“数据新鲜度”。

本阶段把 freshness 显式定义为：

- 仅统计 `manual_scrape` 和 `scheduled_scrape` 的最近成功记录。
- 前台文案对应为“最近抓取成功任务”。
- 其他后台任务继续出现在管理台任务记录里，但不再污染公开 freshness。

#### 4. 手动抓取前置校验

在 `run-scrape` 提交后台任务前，先做 source 级校验：

- source 不存在 -> `404`
- source 已停用 -> `409`
- 只有校验通过才创建任务记录。

同时后台实际执行路径若再次遇到 source 异常，应记录为 `failed`，不允许出现“success + 0 条记录”的假成功语义。

#### 5. DEBUG 配置护栏

当前 `Settings.DEBUG` 是布尔值，宿主环境出现 `DEBUG=release` 会直接在导入阶段触发校验错误。

本阶段为 `DEBUG` 增加显式预处理：

- 接受标准布尔文本：`true/false/1/0/yes/no/on/off`
- 空值走默认值
- 非法值不再直接让进程崩溃，而是回退到 `False`
- 同时记录一条 warning，说明配置非法并已回退

目标是让测试、CI、本地运行对宿主环境污染更稳，而不是放任无声吞错。

### Phase 2：前端可用性与页面质量

#### 1. 列表卡片与主交互可访问性

列表页帖子卡片从可点击 `div` 调整为语义化可聚焦交互容器：

- 支持键盘 Tab 聚焦。
- 支持 Enter/Space 进入详情。
- 保留现有视觉样式。

同时补齐：

- 搜索框显式 label 或 `aria-label`
- 详情页返回按钮的可读名称
- 筛选标签删除按钮的 `aria-label`
- 管理页登录表单与配置表单的 `for/id` 关联
- 管理页进度条补 `role="progressbar"` 和相关 aria 属性

#### 2. 路由滚动与异常路由

路由层增加：

- `scrollBehavior`
  - 普通导航回到顶部
  - 浏览器前进/后退优先恢复历史滚动位置
- catch-all 404 路由

这样可以修复“长列表进详情/返回丢上下文”和“错误路径无恢复界面”的问题。

#### 3. 列表页反馈模型

列表页区分两类状态：

- 首次加载：允许全区 skeleton/loading
- 条件刷新：保留当前结果，只在局部显示“正在刷新”或弱 loading 状态

同时收敛统计请求：

- 保持当前功能语义不变
- 但避免用户每次输入时都感知到整块内容闪断

#### 4. 管理台状态可信度

管理台在真实数据未返回前，关键状态不再展示误导性的默认值，而展示：

- `--`
- `加载中`
- `未获取`

只有在实际请求成功后才展示：

- 调度启用状态
- 默认 source
- 模型名
- 各摘要指标

`activeAdminSection` 本轮先不做 URL 化；若阶段内成本可控，可作为增强项加入 Phase 2，否则保持为后续优化。

### Phase 3：交付与部署基线

#### 1. 文档一致性收口

修正文档与实现不一致项：

- `STATUS.md` 的 Basic Auth 过期表述
- AI 默认模型值口径不一致
- 管理会话、HTTPS、长期运行边界的说明

#### 2. 发布门禁

发布流程改为“验证通过后再发镜像”，原则上有两种安全实现：

- 把测试和发布并入同一个 workflow，发布 job 依赖测试 job
- 或保留分离 workflow，但用 `workflow_run`/tag gate 明确要求 CI 先绿

推荐第一种，结构更直接，维护成本更低。

#### 3. 部署默认值与边界说明

本阶段不强行改变本地开发默认行为，但要明确：

- 生产部署必须启用 HTTPS
- `ADMIN_SESSION_SECURE` 的生产建议值
- `latest` tag 不适合作为稳定部署锚点
- 单机 SQLite 仅适合轻量部署和演示，不是长期稳定运行方案

#### 4. 前端最小自动回归

把最小前端自动测试纳入交付链路：

- 至少新增一个正式 `test` 脚本
- 把当前已有的 `postFilters` 工具测试纳入 CI
- 若阶段成本允许，补一个 API client 或路由层 smoke test

## 文件边界

### Phase 1 预计涉及

- `src/config.py`
- `src/api/admin.py`
- `src/api/posts.py`
- `src/services/admin_task_service.py`
- `src/services/post_job_service.py`
- `src/services/scraper_service.py`
- `tests/test_admin_api.py`
- `tests/test_admin_task_service.py`
- `tests/test_api.py`
- `tests/test_post_job_service.py`
- 可能新增针对 `config` 的单测文件

### Phase 2 预计涉及

- `frontend/src/router/index.js`
- `frontend/src/views/PostList.vue`
- `frontend/src/views/PostDetail.vue`
- `frontend/src/views/AdminDashboard.vue`
- `frontend/src/api/posts.js`
- `frontend/tests/*`

### Phase 3 预计涉及

- `README.md`
- `STATUS.md`
- `docs/deploy-vps-docker.md`
- `docs/deploy-1panel-ghcr.md`
- `.github/workflows/ci.yml`
- `.github/workflows/publish-images.yml`
- `frontend/package.json`
- 可能新增前端测试配置文件

## 验证策略

### Phase 1

- 后端完整回归：`python -m unittest discover -s tests -v`
- 重点回归：
  - 管理任务互斥
  - freshness 语义
  - AI 岗位保留
  - source 校验
  - DEBUG 非法值回退

### Phase 2

- 前端构建：`npm run build`
- 前端测试：纳入现有工具测试，并补新增测试
- 运行态抽查：
  - `/`
  - `/post/:id`
  - `/admin`

### Phase 3

- workflow 静态检查
- 文档一致性检查
- CI 真实运行结果确认

## 风险与取舍

### 1. 后端互斥会降低并发度

这是有意为之。当前单机 SQLite 架构优先保证数据正确性，而不是后台吞吐。

### 2. 保留已有 AI 岗位可能带来旧数据残留

该风险低于“普通重建直接覆盖 AI 结果”。后续若要更彻底解决，应把岗位来源分层建模，但不属于本轮范围。

### 3. Phase 2 不做全面前端拆分

`AdminDashboard.vue` 过大是事实，但本轮先修关键可用性问题，不把阶段目标扩张成“大规模前端重构”。

## 实施顺序

1. 先执行 `Phase 1：后端一致性与运行时治理`
2. 验证通过后执行 `Phase 2：前端可用性与页面质量`
3. 最后执行 `Phase 3：交付与部署基线`

## 验收标准

- 普通抓取和附件补处理不再覆盖已有 AI 岗位结果。
- 后台会改内容的任务不能并发运行。
- 前台 freshness 只反映抓取成功时间。
- 非法 `DEBUG` 环境变量不再让测试与启动直接崩溃。
- 列表页和管理页关键交互可被键盘和基础辅助技术访问。
- 路由具备滚动管理和 404 兜底。
- 文档、默认值、workflow 门禁与实现保持一致。
