import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildTaskRequestConfig,
  buildTaskActionGuide,
  getTaskActionDefinitions,
  canRetryTask,
  getTaskRefreshOptions
} from '../src/views/admin/adminDashboardTaskActions.js'

const forms = {
  scrape: { sourceId: 9, maxPages: 7 },
  backfill: { sourceId: '3', limit: 60 },
  duplicate: { limit: 200 },
  baseAnalysis: { sourceId: '', limit: 80, onlyPending: true },
  aiAnalysis: { sourceId: '8', limit: 90, onlyUnanalyzed: false },
  jobIndex: { sourceId: '7', limit: 70, onlyPending: false },
  aiJob: { sourceId: '6', limit: 55, onlyPending: true }
}

test('buildTaskRequestConfig falls back to current scrape form values when retry params are missing', () => {
  const config = buildTaskRequestConfig('manual_scrape', {
    params: {},
    forms
  })

  assert.equal(canRetryTask('manual_scrape'), true)
  assert.deepEqual(config.payload, {
    source_id: 9,
    max_pages: 7
  })
  assert.deepEqual(config.refreshOptions, getTaskRefreshOptions('manual_scrape'))
})

test('buildTaskRequestConfig maps ai job retry params to the job extraction api payload', () => {
  const config = buildTaskRequestConfig('ai_job_extraction', {
    params: {
      source_id: '5',
      limit: '42',
      only_pending: true
    },
    forms
  })

  assert.equal(canRetryTask('ai_job_extraction'), true)
  assert.equal(config.apiAction, 'runJobExtraction')
  assert.deepEqual(config.payload, {
    source_id: 5,
    limit: 42,
    only_unindexed: true,
    use_ai: true
  })
  assert.deepEqual(config.refreshOptions, {
    includeJobs: true,
    includeDuplicate: true
  })
})

test('buildTaskRequestConfig should preserve historical use_ai when rerunning legacy job extraction tasks', () => {
  const config = buildTaskRequestConfig('job_extraction', {
    params: {
      source_id: '5',
      limit: '42',
      only_unindexed: true,
      use_ai: true
    },
    forms
  })

  assert.equal(config.apiAction, 'runJobExtraction')
  assert.deepEqual(config.payload, {
    source_id: 5,
    limit: 42,
    only_unindexed: true,
    use_ai: true
  })
})

test('buildTaskRequestConfig should force rerun back to full processing when the previous run was incremental', () => {
  const config = buildTaskRequestConfig('base_analysis_backfill', {
    actionKey: 'rerun',
    params: {
      source_id: '4',
      limit: '25',
      only_pending: true
    },
    forms
  })

  assert.deepEqual(config.payload, {
    source_id: 4,
    limit: 25,
    only_pending: false
  })
})

test('buildTaskRequestConfig should not inherit incremental defaults for legacy reruns with missing flags', () => {
  const config = buildTaskRequestConfig('base_analysis_backfill', {
    actionKey: 'rerun',
    params: {
      source_id: '4',
      limit: '25'
    },
    forms
  })

  assert.deepEqual(config.payload, {
    source_id: 4,
    limit: 25,
    only_pending: false
  })
})

test('buildTaskRequestConfig should support incremental rerun semantics and carry rerun_of_task_id', () => {
  const config = buildTaskRequestConfig('base_analysis_backfill', {
    actionKey: 'incremental',
    rerunOfTaskId: 'run-prev-9',
    params: {
      source_id: '4',
      limit: '25',
      only_pending: false
    },
    forms
  })

  assert.deepEqual(config.payload, {
    source_id: 4,
    limit: 25,
    only_pending: true,
    rerun_of_task_id: 'run-prev-9'
  })
})

test('buildTaskRequestConfig should rerun duplicate backfill as recheck_recent', () => {
  const config = buildTaskRequestConfig('duplicate_backfill', {
    actionKey: 'rerun',
    rerunOfTaskId: 'run-prev-12',
    params: {
      limit: '25',
      scope_mode: 'unchecked'
    },
    forms
  })

  assert.deepEqual(config.payload, {
    limit: 25,
    scope_mode: 'recheck_recent',
    rerun_of_task_id: 'run-prev-12'
  })
})

test('buildTaskRequestConfig should keep duplicate retry scoped to unchecked records', () => {
  const config = buildTaskRequestConfig('duplicate_backfill', {
    actionKey: 'retry',
    params: {
      limit: '25'
    },
    forms
  })

  assert.deepEqual(config.payload, {
    limit: 25,
    scope_mode: 'unchecked'
  })
})

test('getTaskActionDefinitions should keep one primary action per task status', () => {
  const failedActions = getTaskActionDefinitions({
    task_type: 'attachment_backfill',
    status: 'failed',
    params: { limit: 50 }
  })
  const runningActions = getTaskActionDefinitions({
    task_type: 'ai_analysis',
    status: 'running',
    details: {}
  })
  const successActions = getTaskActionDefinitions({
    task_type: 'ai_analysis',
    status: 'success',
    params: { limit: 50, only_unanalyzed: false }
  })
  const cancelledActions = getTaskActionDefinitions({
    task_type: 'ai_analysis',
    status: 'cancelled',
    details: {},
    params: { limit: 100, only_unanalyzed: true }
  })

  assert.deepEqual(failedActions.map((item) => item.key), ['retry'])
  assert.deepEqual(runningActions.map((item) => item.key), ['cancel'])
  assert.deepEqual(successActions.map((item) => item.key), ['rerun'])
  assert.deepEqual(cancelledActions.map((item) => item.key), ['incremental'])
})

test('getTaskActionDefinitions should expose cancel for running task without cancel request', () => {
  const actions = getTaskActionDefinitions({
    task_type: 'ai_analysis',
    status: 'running',
    details: {}
  })

  assert.deepEqual(actions.map((item) => item.key), ['cancel'])
})

test('getTaskActionDefinitions should hide actions while cancel request is pending', () => {
  const actions = getTaskActionDefinitions({
    task_type: 'ai_analysis',
    status: 'cancel_requested',
    actions: [{ key: 'cancel', label: '提前终止' }],
    details: { cancel_requested_at: '2026-04-01T10:00:00Z' }
  })

  assert.deepEqual(actions, [])
})

test('getTaskActionDefinitions should keep retry and incremental for cancelled incremental task', () => {
  const actions = getTaskActionDefinitions({
    task_type: 'ai_analysis',
    status: 'cancelled',
    details: {},
    params: { limit: 100, only_unanalyzed: true }
  })

  assert.deepEqual(actions.map((item) => item.key), ['incremental'])
})

test('getTaskActionDefinitions should prefer backend action contract over local fallback', () => {
  const actions = getTaskActionDefinitions({
    task_type: 'ai_analysis',
    status: 'cancelled',
    actions: [{ key: 'retry', label: '按原条件重试' }],
    params: { limit: 100, only_unanalyzed: true }
  })

  assert.deepEqual(actions.map((item) => item.key), ['retry'])
})

test('getTaskActionDefinitions should expose user-facing semantics for retry, rerun, and incremental actions', () => {
  const failedActions = getTaskActionDefinitions({
    task_type: 'attachment_backfill',
    status: 'failed',
    params: { limit: 50 }
  })
  const successActions = getTaskActionDefinitions({
    task_type: 'ai_analysis',
    status: 'success',
    rerun_of_task_id: 'run-prev-9',
    params: { limit: 50, only_unanalyzed: false }
  })

  assert.equal(failedActions[0].description, '沿用这次的数据源和批量，再提交一次附件补处理。')
  assert.equal(failedActions[0].scopeLabel, '沿用当前补处理范围')
  assert.equal(successActions[0].description, '按这次范围重新补充智能摘要，并刷新已有结果。')
  assert.equal(successActions[0].scopeLabel, '重新整理当前范围')
})

test('buildTaskActionGuide should describe action context for continued tasks without exposing internal ids', () => {
  const guide = buildTaskActionGuide({
    task_type: 'ai_analysis',
    status: 'success',
    rerun_of_task_id: 'run-prev-9',
    params: { limit: 50, only_unanalyzed: true }
  })

  assert.equal(guide.title, '操作前说明')
  assert.equal(guide.description, '继续补充会沿用当前条件；重新整理会刷新当前范围；只补未补充内容只会补缺口。')
  assert.deepEqual(guide.contextBadge, {
    label: '当前记录',
    value: '来自之前一次继续处理'
  })
  assert.deepEqual(
    guide.actions.map((item) => item.key),
    ['rerun']
  )
  assert.doesNotMatch(guide.contextBadge.value, /run-prev-9/)
})

test('buildTaskActionGuide should omit continuation context for standalone tasks', () => {
  const guide = buildTaskActionGuide({
    task_type: 'attachment_backfill',
    status: 'failed',
    params: { limit: 50 }
  })

  assert.equal(guide.contextBadge, null)
  assert.deepEqual(
    guide.actions.map((item) => item.key),
    ['retry']
  )
})

test('getTaskActionDefinitions should use duplicate-specific action copy for retry and rerun', () => {
  const retryActions = getTaskActionDefinitions({
    task_type: 'duplicate_backfill',
    status: 'failed',
    params: { limit: 50, scope_mode: 'unchecked' }
  })
  const rerunActions = getTaskActionDefinitions({
    task_type: 'duplicate_backfill',
    status: 'success',
    params: { limit: 50, scope_mode: 'unchecked' }
  })

  assert.equal(retryActions[0].label, '继续检查未检查记录')
  assert.equal(retryActions[0].description, '继续补齐还没检查过的帖子，已经确认过的结果会保留。')
  assert.equal(retryActions[0].scopeLabel, '仅处理未检查记录')
  assert.equal(rerunActions[0].label, '重新检查当前范围')
  assert.equal(rerunActions[0].description, '按这次任务的范围重新检查最近一批帖子，并刷新这批记录的重复结果。')
  assert.equal(rerunActions[0].scopeLabel, '重新检查最近一批记录')
})
