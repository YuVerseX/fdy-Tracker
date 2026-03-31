# 管理台信息架构与共享组件层重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把管理台从“实现过程说明页”重构成“任务导向后台”，收敛一级导航、去掉内部说明型文案、引入共享 UI primitives，并把 `AI 增强` 合并进 `处理任务` 的内部结构。

**Architecture:** 前端新增 `components/ui/` 基础组件层，并引入 `Reka UI` 作为低层交互 primitives。`AdminDashboard.vue` 变成 4 个一级入口的 shell：`总览 / 处理任务 / 任务中心 / 系统设置`。`处理任务` 内部通过二级 tabs 划分 `基础处理 / AI 增强`。页面文案、导航 taxonomy 和 section adapters 统一收口到纯函数/常量层，避免再把设计说明直接写进模板。

**Tech Stack:** Vue 3, Tailwind CSS, Reka UI, node:test, Vite

---

### Task 1: 收紧导航 taxonomy 与文案边界

**Files:**
- Modify: `frontend/src/utils/adminDashboardMeta.js`
- Modify: `frontend/src/views/admin/adminDashboardSectionAdapters.js`
- Test: `frontend/tests/adminDashboardMeta.test.mjs`
- Test: `frontend/tests/adminDashboardSectionAdapters.test.mjs`

- [ ] **Step 1: 先补 taxonomy 与 copy 失败测试**

更新 `frontend/tests/adminDashboardMeta.test.mjs`，把后台一级导航断言改成 4 项，并要求 `任务记录` 改名为 `任务中心`：

```javascript
test('ADMIN_SECTION_OPTIONS should expose the new navigation order', () => {
  assert.deepEqual(
    ADMIN_SECTION_OPTIONS.map((item) => item.value),
    ['overview', 'processing', 'tasks', 'system']
  )
  assert.deepEqual(
    ADMIN_SECTION_OPTIONS.map((item) => item.label),
    ['总览', '处理任务', '任务中心', '系统设置']
  )
})
```

在 `frontend/tests/adminDashboardSectionAdapters.test.mjs` 里补“页面 copy 不再出现设计说明句”的断言：

```javascript
test('section model should not expose design-note copy to end users', () => {
  const section = buildTaskRunsSectionModel({
    taskRuns: [],
    taskRunsLoaded: true,
    loadingRuns: false,
    retryingTaskId: '',
    expandedTaskIds: [],
    nowTs: Date.now(),
    sourceOptions: [],
    heartbeatStaleMs: 600000
  })

  const text = JSON.stringify(section)
  assert.doesNotMatch(text, /默认先看当前异常和最近结果/)
  assert.doesNotMatch(text, /避免把基础处理和 AI 增强混在一起/)
})
```

- [ ] **Step 2: 跑前端 meta/adapters 测试，确认现状失败**

Run:

```bash
cd frontend
node --test tests/adminDashboardMeta.test.mjs tests/adminDashboardSectionAdapters.test.mjs
```

Expected:
- 现有导航仍是 5 项
- adapters / meta 里仍包含旧的设计说明型文案

- [ ] **Step 3: 收口 `adminDashboardMeta.js` 和 section adapters**

在 `frontend/src/utils/adminDashboardMeta.js` 中把 taxonomy 改成：

```javascript
export const ADMIN_SECTION_OPTIONS = [
  { value: 'overview', label: '总览' },
  { value: 'processing', label: '处理任务' },
  { value: 'tasks', label: '任务中心' },
  { value: 'system', label: '系统设置' }
]
```

同时在 `adminDashboardSectionAdapters.js` 里把“设计说明句”替换成用户视角 copy，例如：

```javascript
{
  id: 'recent-task',
  label: '最近任务',
  value: latestSuccessTask ? getTaskTypeLabel(latestSuccessTask.taskType) : '还没有成功记录',
  meta: [
    latestSuccessTask?.finishedAt
      ? `${formatAdminDateTime(latestSuccessTask.finishedAt)}（${getRelativeTimeLabel(latestSuccessTask.finishedAt)}）`
      : '先运行一次任务后再看这里',
    latestFailedTask?.finishedAt
      ? `最近失败：${getTaskTypeLabel(latestFailedTask.taskType)}`
      : ''
  ].filter(Boolean)
}
```

- [ ] **Step 4: 再跑 taxonomy 与 copy 回归**

Run:

```bash
cd frontend
node --test tests/adminDashboardMeta.test.mjs tests/adminDashboardSectionAdapters.test.mjs
```

Expected:
- PASS
- 元数据层不再暴露内部设计说明

### Task 2: 引入共享 UI primitives 与设计 token

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/src/style.css`
- Create: `frontend/src/components/ui/AppPageHeader.vue`
- Create: `frontend/src/components/ui/AppSectionHeader.vue`
- Create: `frontend/src/components/ui/AppStatusBadge.vue`
- Create: `frontend/src/components/ui/AppNotice.vue`
- Create: `frontend/src/components/ui/AppDisclosure.vue`
- Create: `frontend/src/components/ui/AppEmptyState.vue`
- Create: `frontend/src/components/ui/AppTabNav.vue`
- Test: `frontend/tests/adminDashboardViewModels.test.mjs`

- [ ] **Step 1: 先补基础组件接入断言**

在 `frontend/tests/adminDashboardViewModels.test.mjs` 里补一条“处理任务内部存在基础/AI 两个子模式”的测试，避免重新退回一级分裂结构：

```javascript
test('processing area should expose base and ai sub-modes instead of a top-level ai section', () => {
  const panels = buildDataProcessingPanels({
    sourceOptions: [{ label: '江苏省人社厅（source_id=1）', value: 1, isActive: true }]
  })

  assert.ok(Array.isArray(panels))
  assert.ok(panels.some((panel) => panel.id === 'collect-and-backfill'))
  assert.ok(panels.some((panel) => panel.id === 'job-index'))
})
```

补完后让测试先失败在“新 UI primitives 还不存在”的层面即可。

- [ ] **Step 2: 安装 `Reka UI` 并建立设计 token**

在 `frontend/package.json` 新增依赖：

```json
{
  "dependencies": {
    "axios": "^1.13.6",
    "reka-ui": "^2.0.0",
    "vue": "^3.5.30",
    "vue-router": "^4.6.4"
  }
}
```

在 `frontend/src/style.css` 顶部加入 CSS 变量，统一状态色和 spacing：

```css
:root {
  --app-bg: #f8fafc;
  --panel-bg: #ffffff;
  --panel-muted: #f1f5f9;
  --text-strong: #0f172a;
  --text-muted: #475569;
  --tone-info: #0369a1;
  --tone-success: #15803d;
  --tone-warning: #b45309;
  --tone-danger: #b91c1c;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --radius-md: 12px;
  --radius-lg: 16px;
}

body {
  background: var(--app-bg);
  color: var(--text-strong);
}
```

- [ ] **Step 3: 新建共享 UI primitives**

目标组件最小形态如下。

`frontend/src/components/ui/AppSectionHeader.vue`：

```vue
<script setup>
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  aside: { type: String, default: '' }
})
</script>

<template>
  <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
    <div>
      <h2 class="text-lg font-semibold text-slate-900">{{ title }}</h2>
      <p v-if="description" class="mt-1 text-sm text-slate-600">{{ description }}</p>
    </div>
    <div v-if="aside" class="text-xs text-slate-500">{{ aside }}</div>
  </div>
</template>
```

`frontend/src/components/ui/AppTabNav.vue` 使用 `Reka UI` 的 tabs primitives：

```vue
<script setup>
import { TabsRoot, TabsList, TabsTrigger } from 'reka-ui'

defineProps({
  modelValue: { type: String, required: true },
  items: { type: Array, required: true }
})
const emit = defineEmits(['update:modelValue'])
</script>

<template>
  <TabsRoot :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)">
    <TabsList class="flex flex-wrap gap-2 rounded-full bg-slate-100 p-1">
      <TabsTrigger
        v-for="item in items"
        :key="item.value"
        :value="item.value"
        class="rounded-full px-4 py-2 text-sm data-[state=active]:bg-sky-700 data-[state=active]:text-white"
      >
        {{ item.label }}
      </TabsTrigger>
    </TabsList>
  </TabsRoot>
</template>
```

- [ ] **Step 4: 跑依赖安装与前端测试**

Run:

```bash
cd frontend
npm install
npm test
```

Expected:
- `reka-ui` 安装成功
- 现有 node:test 回归仍通过

### Task 3: 重建管理台 shell 与“处理任务”结构

**Files:**
- Modify: `frontend/src/views/AdminDashboard.vue`
- Modify: `frontend/src/views/admin/useAdminDashboardState.js`
- Modify: `frontend/src/views/admin/adminDashboardSectionAdapters.js`
- Create: `frontend/src/views/admin/sections/AdminProcessingSection.vue`
- Modify: `frontend/src/views/admin/sections/AdminOverviewSection.vue`
- Modify: `frontend/src/views/admin/sections/AdminSystemSection.vue`
- Modify: `frontend/src/views/admin/sections/AdminTaskRunsSection.vue`

- [ ] **Step 1: 先把状态层改成 4 个一级入口**

在 `useAdminDashboardState.js` 中让 `activeAdminSection` 只允许：

```javascript
const ADMIN_SECTION_ORDER = ['overview', 'processing', 'tasks', 'system']
const activeAdminSection = ref(ADMIN_SECTION_ORDER[0])
```

并把 `ai-enhancement` 相关选择逻辑改成 `processingSubSection`：

```javascript
const processingMode = ref('base')

const processingTabOptions = [
  { value: 'base', label: '基础处理' },
  { value: 'ai', label: 'AI 增强' }
]
```

- [ ] **Step 2: 新建 `AdminProcessingSection.vue`，把基础处理和 AI 增强合并到同一页**

新组件目标片段：

```vue
<script setup>
import AppSectionHeader from '../../../components/ui/AppSectionHeader.vue'
import AppTabNav from '../../../components/ui/AppTabNav.vue'
import AdminDataProcessingSection from './AdminDataProcessingSection.vue'
import AdminAiEnhancementSection from './AdminAiEnhancementSection.vue'

defineProps({
  processingMode: { type: String, required: true },
  processingTabOptions: { type: Array, required: true },
  setProcessingMode: { type: Function, required: true },
  baseSection: { type: Object, required: true },
  aiSection: { type: Object, required: true }
})
</script>

<template>
  <section class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
    <AppSectionHeader
      title="处理任务"
      description="按任务目标处理数据。先完成基础处理，再视需要追加 AI 增强。"
    />
    <div class="mt-5">
      <AppTabNav :model-value="processingMode" :items="processingTabOptions" @update:modelValue="setProcessingMode" />
    </div>
    <div class="mt-6">
      <AdminDataProcessingSection v-if="processingMode === 'base'" v-bind="baseSection" />
      <AdminAiEnhancementSection v-else v-bind="aiSection" />
    </div>
  </section>
</template>
```

- [ ] **Step 3: 让 `AdminDashboard.vue` 只做 shell 组合，不再写解释性 copy**

目标片段：

```vue
<AppPageHeader
  title="管理台"
  description="查看系统状态、处理数据任务和检查执行结果。"
  action-label="返回前台"
  :action-to="{ name: 'PostList' }"
/>

<AppTabNav
  :model-value="dashboard.activeAdminSection"
  :items="dashboard.adminSectionOptions"
  @update:modelValue="dashboard.setActiveSection"
/>

<AdminProcessingSection
  v-if="dashboard.activeAdminSection === 'processing'"
  :processing-mode="dashboard.processingSection.mode"
  :processing-tab-options="dashboard.processingSection.tabOptions"
  :set-processing-mode="dashboard.setProcessingMode"
  :base-section="dashboard.processingSection.baseSection"
  :ai-section="dashboard.processingSection.aiSection"
/>
```

- [ ] **Step 4: 跑前端完整回归与构建**

Run:

```bash
cd frontend
npm test
npm run build
```

Expected:
- PASS
- 后台一级导航收敛到 4 项
- `AI 增强` 不再是一级入口

### Task 4: 清理 Overview / 任务中心的内部说明型文案

**Files:**
- Modify: `frontend/src/views/admin/sections/AdminOverviewSection.vue`
- Modify: `frontend/src/views/admin/sections/AdminTaskRunsSection.vue`
- Modify: `frontend/src/views/admin/sections/AdminAiEnhancementSection.vue`
- Modify: `frontend/src/views/admin/sections/AdminDataProcessingSection.vue`
- Test: `frontend/tests/adminDashboardSectionAdapters.test.mjs`

- [ ] **Step 1: 把“设计说明句”替换成用户视角 copy**

目标替换方向：

```vue
<!-- 不要 -->
<p>默认先看当前异常和最近结果，历史明细收进下方折叠区</p>

<!-- 改成 -->
<p>查看正在执行、刚完成和历史任务记录。</p>
```

```vue
<!-- 不要 -->
<p>按任务目标拆分入口，避免把基础处理和 AI 增强混在一起。</p>

<!-- 改成 -->
<p>按任务类型处理数据，并查看最近执行结果。</p>
```

- [ ] **Step 2: 把接口占位型提示降级成禁用态或空状态**

例如 `AdminAiEnhancementSection.vue` 里：

```vue
<p v-if="jobsSummaryUnavailable" class="mt-2 text-xs text-slate-500">
  当前无法读取岗位统计，不影响你继续发起岗位补抽。
</p>
```

不要再出现：

```vue
后端还没开放岗位摘要接口，当前先显示占位值
```

- [ ] **Step 3: 再跑前端回归**

Run:

```bash
cd frontend
npm test
npm run build
```

Expected:
- PASS
- 管理台模板中不再出现内部设计说明或接口占位说明

