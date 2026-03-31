import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const readSource = (relativePath) => readFileSync(new URL(`../src/${relativePath}`, import.meta.url), 'utf8')

test('admin task cards should use shared action, stat, and metric primitives', () => {
  const actionCardSource = readSource('views/admin/sections/AdminTaskActionCard.vue')
  const runCardSource = readSource('views/admin/sections/AdminTaskRunCard.vue')
  const runPresentationSource = readSource('views/admin/adminTaskRunPresentation.js')
  const combined = [actionCardSource, runCardSource, runPresentationSource].join('\n')

  assert.match(combined, /AppActionButton/)
  assert.match(combined, /AppStatCard/)
  assert.match(combined, /AppMetricPill/)
  assert.match(runCardSource, /progressView\.showProgressBar/)
  assert.match(runCardSource, /progressView\.modeLabel/)
  assert.match(runCardSource, /detailSections/)
  assert.match(combined, /任务信息/)
  assert.match(combined, /处理结果/)
})

test('admin task run card should show user-facing guidance for task actions', () => {
  const runCardSource = readSource('views/admin/sections/AdminTaskRunCard.vue')

  assert.match(runCardSource, /AppNotice/)
  assert.match(runCardSource, /actionGuide\.title/)
  assert.match(runCardSource, /actionGuide\.description/)
  assert.match(runCardSource, /actionGuide\.contextBadge/)
  assert.match(runCardSource, /action\.description/)
  assert.match(runCardSource, /action\.scopeLabel/)
})
