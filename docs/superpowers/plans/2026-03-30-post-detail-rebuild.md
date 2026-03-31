# 招聘详情阅读页重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `/post/:id` 从“系统分析页”重构成“阅读与判断页”，压缩首屏信息密度、移除内部来源表达、改造多岗位展示，并把 `PostDetail.vue` 拆回可维护的组件和纯函数层。

**Architecture:** 前台详情页继续使用现有 `GET /api/posts/:id` 数据，但不再把所有字段原样堆成大卡片。状态获取逻辑抽到 `usePostDetailState.js`，展示规则抽到 `postDetailPresentation.js`，页面本身只负责组合 `Hero / Facts / Jobs / Attachments / Content / InfoDisclosure` 6 个区块。多岗位展示改成表格，信息说明统一收进 disclosure，不再占据首屏。

**Tech Stack:** Vue 3, Tailwind CSS, node:test, Vite

---

### Task 1: 抽出详情页展示规则并先补测试

**Files:**
- Create: `frontend/src/utils/postDetailPresentation.js`
- Test: `frontend/tests/postDetailPresentation.test.mjs`
- Test: `frontend/tests/publicFreshness.test.mjs`

- [ ] **Step 1: 先补展示规则失败测试**

新增 `frontend/tests/postDetailPresentation.test.mjs`，至少覆盖以下 4 类规则：

```javascript
import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildPostFacts,
  buildJobPresentation,
  shouldShowAdminFacingMetadata,
  buildInfoDisclosureItems
} from '../src/utils/postDetailPresentation.js'

test('buildPostFacts should keep the public facts compact and ordered', () => {
  const facts = buildPostFacts({
    fields: {
      '岗位名称': '专职辅导员',
      '招聘人数': '2人',
      '学历要求': '硕士研究生及以上',
      '工作地点': '江苏省苏州市'
    }
  })

  assert.deepEqual(
    facts.map((item) => item.label),
    ['岗位名称', '招聘人数', '学历要求', '工作地点']
  )
})

test('buildJobPresentation should use table mode for multiple jobs', () => {
  const view = buildJobPresentation([
    { job_name: '专职辅导员', headcount: '2人' },
    { job_name: '实验员', headcount: '1人' }
  ])

  assert.equal(view.mode, 'table')
  assert.equal(view.rows.length, 2)
})

test('shouldShowAdminFacingMetadata should hide provider and confidence from first screen', () => {
  assert.equal(shouldShowAdminFacingMetadata('confidence_score'), false)
  assert.equal(shouldShowAdminFacingMetadata('analysis_provider'), false)
})

test('buildInfoDisclosureItems should move provenance copy into disclosure area', () => {
  const items = buildInfoDisclosureItems({
    freshnessHint: '最近一次抓取成功于 2026/03/30 20:41',
    sourceNotes: ['岗位信息由正文、附件和系统整理结果综合展示']
  })

  assert.ok(items.some((item) => /最近一次抓取成功/.test(item.value)))
})
```

- [ ] **Step 2: 跑详情页展示规则测试，确认现状失败**

Run:

```bash
cd frontend
node --test tests/postDetailPresentation.test.mjs tests/publicFreshness.test.mjs
```

Expected:
- `postDetailPresentation.js` 还不存在
- 现有详情页逻辑还没有“表格模式 / disclosure 模式 / 隐藏内部 metadata”

- [ ] **Step 3: 新建 `postDetailPresentation.js`，把展示规则从页面中剥离**

目标片段：

```javascript
const FACT_ORDER = ['岗位名称', '招聘人数', '学历要求', '专业要求', '工作地点', '政治面貌', '年龄要求', '报名时间']
const HIDDEN_FIRST_SCREEN_KEYS = new Set(['confidence_score', 'analysis_provider', 'field_source', 'job_source'])

export function buildPostFacts({ fields = {} } = {}) {
  return FACT_ORDER
    .filter((label) => String(fields[label] || '').trim())
    .map((label) => ({ label, value: String(fields[label]).trim() }))
}

export function buildJobPresentation(jobItems = []) {
  if (jobItems.length <= 1) {
    return { mode: 'single', rows: jobItems }
  }
  return {
    mode: 'table',
    columns: ['岗位名称', '人数', '学历', '专业', '地点'],
    rows: jobItems
  }
}

export function shouldShowAdminFacingMetadata(key) {
  return !HIDDEN_FIRST_SCREEN_KEYS.has(key)
}

export function buildInfoDisclosureItems({ freshnessHint = '', sourceNotes = [] } = {}) {
  return [
    freshnessHint ? { key: 'freshness', label: '更新说明', value: freshnessHint } : null,
    ...sourceNotes.map((value, index) => ({ key: `source-${index}`, label: '信息说明', value }))
  ].filter(Boolean)
}
```

- [ ] **Step 4: 再跑展示规则测试**

Run:

```bash
cd frontend
node --test tests/postDetailPresentation.test.mjs tests/publicFreshness.test.mjs
```

Expected:
- PASS
- 详情页的核心展示规则已脱离 `PostDetail.vue`

### Task 2: 抽出状态层和共享任务标签

**Files:**
- Create: `frontend/src/views/post-detail/usePostDetailState.js`
- Create: `frontend/src/utils/taskTypeLabels.js`
- Modify: `frontend/src/views/PostDetail.vue`
- Modify: `frontend/src/views/PostList.vue`
- Test: `frontend/tests/publicFreshness.test.mjs`

- [ ] **Step 1: 先把公共 freshness 标签逻辑改成共享模块测试**

更新 `frontend/tests/publicFreshness.test.mjs`，让测试直接断言共享任务标签 helper，而不是分别依赖 `PostList.vue` 和 `PostDetail.vue` 内部私有函数：

```javascript
import { getPublicTaskTypeLabel } from '../src/utils/taskTypeLabels.js'

test('getPublicTaskTypeLabel should normalize public-facing freshness copy', () => {
  assert.equal(getPublicTaskTypeLabel('manual_scrape'), '手动抓取')
  assert.equal(getPublicTaskTypeLabel('scheduled_scrape'), '定时抓取')
  assert.equal(getPublicTaskTypeLabel('job_extraction'), '岗位整理')
})
```

- [ ] **Step 2: 跑 freshness 测试，确认现状失败**

Run:

```bash
cd frontend
node --test tests/publicFreshness.test.mjs
```

Expected:
- 共享 `taskTypeLabels.js` 还不存在
- `PostList.vue` / `PostDetail.vue` 仍各自维护一份标签表

- [ ] **Step 3: 抽状态层和共享标签**

新建 `frontend/src/utils/taskTypeLabels.js`：

```javascript
const PUBLIC_TASK_TYPE_LABELS = {
  manual_scrape: '手动抓取',
  scheduled_scrape: '定时抓取',
  attachment_backfill: '历史附件补处理',
  job_extraction: '岗位整理',
  ai_job_extraction: '岗位整理'
}

export const getPublicTaskTypeLabel = (taskType) => PUBLIC_TASK_TYPE_LABELS[taskType] || '后台任务'
```

新建 `frontend/src/views/post-detail/usePostDetailState.js`：

```javascript
import { computed, onMounted, ref } from 'vue'
import { postsApi } from '../../api/posts.js'

export function usePostDetailState(route) {
  const post = ref(null)
  const loading = ref(false)
  const error = ref('')
  const latestSuccessTask = ref(null)
  const freshnessLoading = ref(false)
  const freshnessUnavailable = ref(false)

  async function fetchPostDetail() { /* 搬迁现有请求逻辑 */ }
  async function fetchLatestSuccessTask() { /* 搬迁现有 freshness 逻辑 */ }

  onMounted(async () => {
    await Promise.all([fetchPostDetail(), fetchLatestSuccessTask()])
  })

  return {
    post,
    loading,
    error,
    latestSuccessTask,
    freshnessLoading,
    freshnessUnavailable,
    fetchPostDetail,
  }
}
```

- [ ] **Step 4: 让 `PostList.vue` 和 `PostDetail.vue` 共用标签 helper**

把两个页面里重复的 `getTaskTypeLabel()` 删除，统一改成：

```javascript
import { getPublicTaskTypeLabel } from '../utils/taskTypeLabels.js'

const label = run.taskLabel || getPublicTaskTypeLabel(run.taskType)
```

- [ ] **Step 5: 再跑 freshness 与已有前端回归**

Run:

```bash
cd frontend
node --test tests/publicFreshness.test.mjs tests/postFilters.test.mjs tests/routerScroll.test.mjs
```

Expected:
- PASS
- 详情页和列表页不再各自维护重复任务标签逻辑

### Task 3: 拆分详情页区块组件并重排阅读结构

**Files:**
- Create: `frontend/src/views/post-detail/PostHeroSection.vue`
- Create: `frontend/src/views/post-detail/PostFactsSection.vue`
- Create: `frontend/src/views/post-detail/PostJobsSection.vue`
- Create: `frontend/src/views/post-detail/PostAttachmentsSection.vue`
- Create: `frontend/src/views/post-detail/PostInfoDisclosure.vue`
- Modify: `frontend/src/views/PostDetail.vue`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: 先定义 6 个区块的职责边界**

页面区块固定为：

```text
PostHeroSection
PostFactsSection
PostJobsSection
PostAttachmentsSection
正文区（保留在 PostDetail.vue）
PostInfoDisclosure
```

约束：

- `PostDetail.vue` 自身只做组装和路由返回
- 不再在单文件里保留 700+ 行展示逻辑

- [ ] **Step 2: 创建事实区与岗位区组件**

`frontend/src/views/post-detail/PostFactsSection.vue` 目标片段：

```vue
<script setup>
defineProps({
  facts: { type: Array, required: true }
})
</script>

<template>
  <section v-if="facts.length > 0" class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
    <h2 class="text-lg font-semibold text-slate-900">关键信息</h2>
    <dl class="mt-4 grid grid-cols-1 gap-x-6 gap-y-4 md:grid-cols-2">
      <div v-for="item in facts" :key="item.label" class="border-b border-slate-100 pb-3">
        <dt class="text-sm text-slate-500">{{ item.label }}</dt>
        <dd class="mt-1 text-base font-medium text-slate-900">{{ item.value }}</dd>
      </div>
    </dl>
  </section>
</template>
```

`frontend/src/views/post-detail/PostJobsSection.vue` 目标片段：

```vue
<script setup>
defineProps({
  jobView: { type: Object, required: true }
})
</script>

<template>
  <section v-if="jobView.rows.length > 0" class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
    <h2 class="text-lg font-semibold text-slate-900">岗位明细</h2>
    <table v-if="jobView.mode === 'table'" class="mt-4 w-full border-collapse text-sm">
      <thead>
        <tr class="border-b border-slate-200 text-left text-slate-500">
          <th class="py-2">岗位名称</th>
          <th class="py-2">人数</th>
          <th class="py-2">学历</th>
          <th class="py-2">专业</th>
          <th class="py-2">地点</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in jobView.rows" :key="row.id || row.job_name" class="border-b border-slate-100">
          <td class="py-3">{{ row.job_name || '--' }}</td>
          <td class="py-3">{{ row.headcount || '--' }}</td>
          <td class="py-3">{{ row.education || '--' }}</td>
          <td class="py-3">{{ row.major || '--' }}</td>
          <td class="py-3">{{ row.location || '--' }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>
```

- [ ] **Step 3: 重写 `PostDetail.vue` 组装顺序并去掉系统味首屏元素**

目标变化：

```vue
<template>
  <div class="min-h-screen bg-slate-50">
    <PostHeroSection
      :title="post.title"
      :publish-date="post.publish_date"
      :source-name="post.source?.name"
      :tags="heroTags"
      :freshness-note="freshnessNote"
      @back="goBack"
    />

    <main class="mx-auto max-w-5xl space-y-6 px-4 py-8">
      <PostFactsSection :facts="facts" />
      <PostJobsSection :job-view="jobView" />
      <PostAttachmentsSection :attachments="post.attachments || []" />
      <section class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 class="text-lg font-semibold text-slate-900">公告正文</h2>
        <div class="prose prose-slate mt-4 max-w-none" v-html="formattedContent" />
      </section>
      <PostInfoDisclosure :items="infoDisclosureItems" />
    </main>
  </div>
</template>
```

必须移除或降级：

- 顶部 `管理台` 按钮
- 首屏 `匹配度`
- 首屏 `岗位级结果 / 原始字段` 来源标签
- 首屏 `规则分析 / OpenAI 分析` provider 说明

- [ ] **Step 4: 跑前端完整回归与构建**

Run:

```bash
cd frontend
npm test
npm run build
```

Expected:
- PASS
- `PostDetail.vue` 明显降到可维护体量
- 多岗位公告改成表格展示
- 首屏不再出现内部元数据和系统说明

