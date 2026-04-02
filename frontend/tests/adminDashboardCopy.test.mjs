import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const readSource = (relativePath) => readFileSync(new URL(`../src/${relativePath}`, import.meta.url), 'utf8')

test('admin dashboard shell should route processing work through a shared processing section', () => {
  const source = readSource('views/AdminDashboard.vue')

  assert.match(source, /AdminProcessingSection/)
  assert.doesNotMatch(source, /activeAdminSection === 'ai-enhancement'/)
  assert.doesNotMatch(source, /按任务目标拆分入口，避免把基础处理和 AI 增强混在一起/)
  assert.doesNotMatch(source, /后台鉴权还没配置/)
})

test('admin task and processing templates should not expose internal implementation notes', () => {
  const sources = [
    readSource('views/admin/sections/AdminTaskRunsSection.vue'),
    readSource('views/admin/sections/AdminDataProcessingSection.vue'),
    readSource('views/admin/sections/AdminAiEnhancementSection.vue'),
    readSource('views/admin/adminDashboardTaskSummary.js')
  ]

  const combined = sources.join('\n')

  assert.doesNotMatch(combined, /默认先看当前异常和最近结果/)
  assert.doesNotMatch(combined, /后端还没开放岗位摘要接口/)
  assert.doesNotMatch(combined, /任务摘要接口不可用/)
})

test('admin dashboard should not hardcode every non-success feedback to danger tone', () => {
  const source = readSource('views/AdminDashboard.vue')

  assert.match(source, /dashboard\.feedback\.type === 'error' \? 'danger' : dashboard\.feedback\.type/)
  assert.doesNotMatch(source, /dashboard\.feedback\.type === 'success' \? 'success' : 'danger'/)
})

test('admin dashboard active task hint should not tell users to manually refresh while auto sync is available', () => {
  const source = readSource('views/AdminDashboard.vue')

  assert.match(source, /任务中心会按当前同步状态更新/)
  assert.doesNotMatch(source, /稍后刷新任务中心获取最新结果/)
})

test('admin dashboard active task notice should use active wording instead of processing wording', () => {
  const dashboardSource = readSource('views/AdminDashboard.vue')
  const stateSource = readSource('views/admin/useAdminDashboardState.js')

  assert.match(dashboardSource, /title="有活跃任务"/)
  assert.doesNotMatch(dashboardSource, /title="有任务正在处理"/)
  assert.match(stateSource, /任务活跃：/)
  assert.doesNotMatch(stateSource, /正在处理：/)
})

test('admin dashboard task sync copy should keep initial sync state neutral before the first snapshot arrives', () => {
  const stateSource = readSource('views/admin/useAdminDashboardState.js')

  assert.match(stateSource, /同步状态更新中/)
  assert.match(stateSource, /正在获取任务中心状态。/)
  assert.match(stateSource, /runningCountLabel: syncStatus\.pending \? '--' :/)
  assert.match(stateSource, /if \(!adminAuthorized\.value \|\| !loaded\.taskRuns\) return \[\]/)
})
