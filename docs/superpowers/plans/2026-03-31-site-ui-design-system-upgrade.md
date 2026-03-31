# 整站 UI 与 Design System 升级实施计划

**目标：** 在不推翻当前 Vue + Tailwind + Reka UI 技术栈的前提下，分阶段完成前台与后台的 UI / IA 升级，先建立可复用设计系统，再重做高价值页面。

## 当前状态（2026-03-31）

- 阶段 1 已完成：全局 token、shared primitives、页面壳层与基础信息组件已经收口到统一设计语言。
- 阶段 2 已完成：后台任务中心已经重做为“当前任务 / 最近结果 / 历史记录”三段式，并收口任务动作语义。
- 阶段 3 已完成：招聘详情页首屏已经按“核心判断摘要 -> 关键事实 -> 岗位明细 -> 附件 / 正文”重构。
- 阶段 4 已完成：列表页、后台总览 / 处理任务 / 系统设置等剩余核心页面已经迁移到新 design system。
- 阶段 5 已完成：补做了 responsive / accessibility sweep，并在 `768 / 1024` 中断点收紧后台处理页密度与布局切换。

## 最新验证（2026-03-31）

- `cd frontend && npm test`
  - 结果：`100/100 pass`
- `cd frontend && npm run build`
  - 结果：构建通过
- Playwright
  - 已复核 `/` 在 `1024px` 下的筛选首屏布局
  - 已复核 `/post/13` 在 `1024px` 下的首屏摘要与关键事实布局
  - 已复核 `/admin` 的基础处理与智能整理视图
  - 已确认 `1024px` 下后台处理卡切换为双列
  - 已确认 `768px` 下处理页头部、辅助说明和任务卡层级保持可扫描
  - 已复核 `/admin` 系统设置页在 `768 / 1024` 下的表单可读性与字段宽度
  - 已复核 `/admin` 任务中心在 `768 / 1024` 下的空态、结果卡和动作区密度
- 既有回归记录仍有效
  - `/`
  - `/post/13`
  - `/this-page-does-not-exist`

## 阶段划分

### 阶段 1：设计系统基础层

**状态**

- 已完成

**目标**

- 建立可落地 token
- 收口共享 primitive
- 统一公共页面壳层
- 立刻改善前后台整体观感和一致性

**改动范围**

- `frontend/src/style.css`
- `frontend/src/components/ui/*`
- `frontend/src/views/PostList.vue`
- `frontend/src/views/PostDetail.vue`
- `frontend/src/views/AdminDashboard.vue`
- `frontend/src/views/admin/sections/*` 中直接依赖 shared primitive 的壳层

**关键动作**

1. 重写全局 token 与 surface utility
2. 引入统一 `AppSurface`
3. 重构 `AppPageHeader / AppSectionHeader / AppStatusBadge / AppNotice / AppActionButton / AppStatCard / AppDisclosure / AppMetricPill / AppEmptyState / AppTabNav`
4. 用 shared surface 替换页面级重复白卡片外壳
5. 引入 `AppFactList`，为详情页和后续任务详情做统一 definition-list 结构

**验证**

- `cd frontend && npm test`
- `cd frontend && npm run build`
- Playwright 检查 `/`、`/post/13`、`/admin`

### 阶段 2：后台任务中心重做

**状态**

- 已完成

**目标**

- 让任务卡片真正围绕“阶段 / 结果 / 动作 / 风险”组织
- 降低嵌套层级，减少说明文字依赖

**改动范围**

- `frontend/src/views/admin/sections/AdminTaskRunsSection.vue`
- `frontend/src/views/admin/sections/AdminTaskRunCard.vue`
- `frontend/src/views/admin/adminTaskRunPresentation.js`
- `frontend/src/views/admin/adminDashboardTaskActions.js`
- 相关 shared information components

**关键动作**

1. 重新切分任务卡版面
2. 区分运行中、成功、失败的主视觉和主动作
3. 强化统计值、失败原因、禁用原因和重跑边界
4. 只在可验证的任务上显示 determinate progress

**验证**

- `cd frontend && npm test`
- `cd frontend && npm run build`
- 登录后人工检查 `/admin`
- 真实接口数据核对 `/api/admin/task-runs` 与页面一致性

### 阶段 3：招聘详情页重构

**状态**

- 已完成

**目标**

- 首屏聚焦招聘判断信息
- 修复多岗位公告的主事实表达
- 压缩冗余结构化卡片

**改动范围**

- `frontend/src/utils/postDetailPresentation.js`
- `frontend/src/views/PostDetail.vue`
- `frontend/src/views/post-detail/*`

**关键动作**

1. 区分公告级事实和岗位级事实
2. 新增“核心判断摘要”与“补充说明”层级
3. 岗位表格改成更适合扫描的结构
4. 正文与附件降到次级层次

**验证**

- `cd frontend && npm test`
- `cd frontend && npm run build`
- Playwright 对比 `/post/13`、多岗位详情页与单岗位详情页
- 真实 API 数据对照 `GET /api/posts/:id`

### 阶段 4：列表页与后台剩余页面

**状态**

- 已完成

**目标**

- 让首页和后台其余模块跟上新 design system
- 收口全站视觉与信息节奏

**改动范围**

- `frontend/src/views/PostList.vue`
- `frontend/src/views/post-list/*`
- `frontend/src/views/admin/sections/AdminOverviewSection.vue`
- `frontend/src/views/admin/sections/AdminDataProcessingSection.vue`
- `frontend/src/views/admin/sections/AdminAiEnhancementSection.vue`
- `frontend/src/views/admin/sections/AdminSystemSection.vue`

**关键动作**

1. 压缩列表页首屏与筛选区
2. 收口统计条、卡片标签和结果 meta
3. 减少后台 overview / processing 的卡片嵌套
4. 完成全站 token 和 primitive 替换

**验证**

- `cd frontend && npm test`
- `cd frontend && npm run build`
- Playwright 全站走查

### 阶段 5：响应式与可访问性回归收敛

**状态**

- 已完成

**目标**

- 收敛 `768 / 1024` 中断点的布局密度和信息层级
- 修复长内容、焦点态和辅助导航的可读性问题
- 为后续小步回归保留稳定的共享组件与测试约束

**改动范围**

- `frontend/src/components/ui/AppDisclosure.vue`
- `frontend/src/components/ui/AppSectionHeader.vue`
- `frontend/src/components/ui/AppSectionNav.vue`
- `frontend/src/components/ui/AppTabNav.vue`
- `frontend/src/views/PostList.vue`
- `frontend/src/views/PostDetail.vue`
- `frontend/src/views/admin/sections/AdminProcessingSection.vue`
- `frontend/src/views/admin/sections/AdminDataProcessingSection.vue`
- `frontend/src/views/admin/sections/AdminAiEnhancementSection.vue`
- 对应前端测试

**关键动作**

1. 为 disclosure、tabs、长文本和快捷跳转补齐可访问性与移动端表现
2. 收紧招聘详情页长内容阅读辅助与结构锚点
3. 修正后台处理页在 `768 / 1024` 中断点仍然过度单列的问题
4. 修正系统设置页在中断点下的表单过窄与字段截断问题
5. 修正任务中心在中断点下的空态体积和结果卡过高问题
6. 让首页筛选区和详情页首屏在 `1024px` 下提前进入更高效的横向编排
7. 用测试锁定中断点栅格、任务卡布局与辅助说明的共享约束

**验证**

- `cd frontend && npm test`
- `cd frontend && npm run build`
- Playwright 检查 `/admin` 的基础处理和智能整理在 `768 / 1024` 下的表现

## 当前计划结论

- 本次整站 UI / design system 升级的主计划已经落地完成。
- 后续若继续推进，应进入“回归维护 / 小范围体验优化”节奏，而不是再开启新的大规模页面重做。
