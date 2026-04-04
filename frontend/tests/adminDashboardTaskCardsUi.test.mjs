import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const readSource = (relativePath) => readFileSync(new URL(`../src/${relativePath}`, import.meta.url), 'utf8')

test('admin task cards should use shared action, stat, and metric primitives', () => {
  const runsSectionSource = readSource('views/admin/sections/AdminTaskRunsSection.vue')
  const actionCardSource = readSource('views/admin/sections/AdminTaskActionCard.vue')
  const runCardSource = readSource('views/admin/sections/AdminTaskRunCard.vue')
  const runPresentationSource = readSource('views/admin/adminTaskRunPresentation.js')
  const combined = [runsSectionSource, actionCardSource, runCardSource, runPresentationSource].join('\n')

  assert.match(combined, /AppActionButton/)
  assert.match(combined, /AppFactList/)
  assert.match(combined, /AppMetricPill/)
  assert.match(runsSectionSource, /当前任务/)
  assert.match(runsSectionSource, /最近结果/)
  assert.match(runsSectionSource, /历史记录/)
  assert.match(runCardSource, /cardPresentation\.stageTitle/)
  assert.match(runCardSource, /cardPresentation\.resultTitle/)
  assert.match(runCardSource, /cardPresentation\.failureNotice/)
  assert.match(combined, /任务信息/)
  assert.match(combined, /处理结果/)
})

test('admin task run card should show user-facing guidance for task actions', () => {
  const runCardSource = readSource('views/admin/sections/AdminTaskRunCard.vue')

  assert.match(runCardSource, /actionDefinitions/)
  assert.match(runCardSource, /v-for="action in actionDefinitions"/)
  assert.match(runCardSource, /AppActionButton/)
  assert.match(runCardSource, /:aria-expanded=/)
  assert.match(runCardSource, /:aria-controls=/)
  assert.match(runCardSource, /role="region"/)
  assert.match(runCardSource, /:aria-labelledby=/)
  assert.match(runCardSource, /detailPanelId/)
  assert.doesNotMatch(runCardSource, /primaryActionDefinition/)
  assert.doesNotMatch(runCardSource, /cardPresentation\.actionSummary/)
})

test('admin task center should keep empty sections lightweight and switch run cards to denser desktop layouts at lg', () => {
  const runsSectionSource = readSource('views/admin/sections/AdminTaskRunsSection.vue')
  const runCardSource = readSource('views/admin/sections/AdminTaskRunCard.vue')

  assert.match(runsSectionSource, /title="当前没有活跃任务"/)
  assert.doesNotMatch(runsSectionSource, /title="当前没有进行中的任务"/)
  assert.match(runsSectionSource, /title="最近还没有结果记录"/)
  assert.match(runsSectionSource, /tone="info"/)
  assert.match(runCardSource, /lg:flex-row/)
  assert.match(runCardSource, /lg:grid-cols-\[minmax\(0,1\.15fr\)_minmax\(0,1fr\)\]/)
  assert.match(runCardSource, /lg:max-w-\[320px\]/)
})

test('admin task action cards should use compact disclosure controls for mobile density', () => {
  const actionCardSource = readSource('views/admin/sections/AdminTaskActionCard.vue')
  const styles = readSource('style.css')

  assert.match(actionCardSource, /app-select app-select--compact/)
  assert.match(actionCardSource, /app-input app-input--compact/)
  assert.match(actionCardSource, /text-xs font-medium uppercase/)
  assert.match(styles, /app-input--compact/)
  assert.match(styles, /app-select--compact/)
})

test('admin task center should surface sync status instead of implying continuous realtime updates', () => {
  const runsSectionSource = readSource('views/admin/sections/AdminTaskRunsSection.vue')

  assert.match(runsSectionSource, /最近同步/)
  assert.match(runsSectionSource, /当前无自动刷新，仅支持手动刷新/)
  assert.match(runsSectionSource, /自动刷新中/)
  assert.match(runsSectionSource, /活跃任务/)
  assert.match(runsSectionSource, /项活跃/)
  assert.doesNotMatch(runsSectionSource, /运行中任务/)
  assert.doesNotMatch(runsSectionSource, /项进行中/)
})

test('admin task center should keep loaded task cards visible while a refresh is in flight', () => {
  const runsSectionSource = readSource('views/admin/sections/AdminTaskRunsSection.vue')

  assert.match(runsSectionSource, /v-if="loadingRuns && !taskRunsLoaded"/)
  assert.doesNotMatch(runsSectionSource, /v-if="loadingRuns \|\| !taskRunsLoaded"/)
})

test('admin task run card should bind result empty copy from presentation instead of hardcoded promise text', () => {
  const runCardSource = readSource('views/admin/sections/AdminTaskRunCard.vue')

  assert.match(runCardSource, /cardPresentation\.resultEmptyText/)
  assert.doesNotMatch(runCardSource, /开始处理后，这里会出现可核对的结果数量/)
})

test('admin task run card should describe snapshot sections as snapshot guidance instead of task results', () => {
  const runCardSource = readSource('views/admin/sections/AdminTaskRunCard.vue')

  assert.match(runCardSource, /section\.id === 'snapshot' \? '这里显示当前状态快照的可信度、时间和范围。' : '这里显示本次任务的补充结果。'/)
})

test('admin task stage timeline should use semantic ordered list and dynamic aria-current', () => {
  const source = readSource('views/admin/sections/AdminTaskStageTimeline.vue')

  assert.match(source, /<ol/)
  assert.match(source, /<li/)
  assert.match(source, /:aria-current=/)
})
