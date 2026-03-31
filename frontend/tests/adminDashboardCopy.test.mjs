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
