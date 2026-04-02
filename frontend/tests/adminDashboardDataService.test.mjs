import test from 'node:test'
import assert from 'node:assert/strict'

import { createAdminDashboardDataService } from '../src/views/admin/adminDashboardDataService.js'

function createDeferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function createHarness({ adminApiOverrides = {} } = {}) {
  const calls = []
  const adminApi = {
    getSession: async () => ({ data: { username: 'admin' } }),
    getSources: async () => ({ data: { items: [] } }),
    getTaskRuns: async () => ({ data: { items: [] } }),
    getTaskSummary: async () => ({ data: { running_tasks: [] } }),
    getSchedulerConfig: async () => {
      calls.push('scheduler')
      return {
        data: {
          enabled: true,
          interval_seconds: 7200,
          default_source_id: 1,
          default_max_pages: 5
        }
      }
    },
    getAnalysisSummary: async () => {
      calls.push('analysis')
      return { data: { runtime: { mode: 'basic' }, overview: { total_posts: 0 } } }
    },
    getInsightSummary: async () => {
      calls.push('insight')
      return { data: { overview: { insight_posts: 0 } } }
    },
    getJobSummary: async () => {
      calls.push('jobs')
      return { data: { overview: { total_jobs: 0 } } }
    },
    getDuplicateSummary: async () => {
      calls.push('duplicate')
      return { data: { overview: { duplicate_posts: 0 } } }
    },
    runAiAnalysis: async () => ({ data: { message: '任务已提交' } })
  }
  Object.assign(adminApi, adminApiOverrides)
  const adminAuthorized = { value: true }
  const adminAuthChecking = { value: false }
  const adminAuthError = { value: '' }
  const adminAuthForm = { username: '', password: '' }
  const feedback = { value: { type: '', message: '' } }
  const sourceOptions = { value: [] }
  const state = {
    taskRuns: [],
    taskSummary: null,
    taskSummaryUnavailable: false,
    analysisSummary: null,
    insightSummary: null,
    jobSummary: null,
    duplicateSummary: null,
    expandedTaskIds: [],
    retryingTaskId: '',
    retryingTaskActionKey: '',
    cancelingTaskId: '',
    jobsSummaryUnavailable: false,
    taskStatusLastSyncedAt: ''
  }
  const loading = {
    scheduler: false,
    schedulerSaving: false,
    analysis: false,
    insight: false,
    jobs: false,
    duplicate: false,
    taskSummary: false,
    taskRuns: false,
    overview: false
  }
  const loaded = {
    scheduler: false,
    analysis: false,
    insight: false,
    jobs: false,
    duplicate: false,
    taskSummary: false,
    taskRuns: false
  }
  const requests = {
    scrape: false,
    backfill: false,
    duplicate: false,
    baseAnalysis: false,
    aiAnalysis: false,
    jobExtraction: false
  }
  const forms = {
    scrape: { sourceId: 1, maxPages: 5 },
    backfill: { sourceId: '', limit: 100 },
    duplicate: { limit: 200 },
    baseAnalysis: { sourceId: '', limit: 100, onlyPending: true },
    aiAnalysis: { sourceId: '', limit: 100, onlyUnanalyzed: true },
    jobIndex: { sourceId: '', limit: 100, onlyPending: true },
    aiJob: { sourceId: '', limit: 100, onlyPending: true },
    scheduler: { enabled: true, intervalSeconds: 7200, defaultSourceId: 1, defaultMaxPages: 5, nextRunAt: '', updatedAt: '' }
  }

  const service = createAdminDashboardDataService({
    adminApi,
    adminAuthorized,
    adminAuthChecking,
    adminAuthError,
    adminAuthForm,
    feedback,
    sourceOptions,
    state,
    loading,
    loaded,
    requests,
    forms
  })

  return { calls, service, state, loaded, forms, feedback, adminAuthorized, adminAuthError, adminAuthForm }
}

function createCancelledIncrementalRun(overrides = {}) {
  return {
    id: 'run-ai-cancelled-1',
    task_type: 'ai_analysis',
    status: 'cancelled',
    actions: [{ key: 'incremental', label: '只补未补充内容' }],
    params: {
      source_id: '8',
      limit: '50',
      only_unanalyzed: false
    },
    ...overrides
  }
}

test('createAdminDashboardDataService should expose refresh aliases expected by AdminDashboard', async () => {
  const { calls, service, state, loaded, forms } = createHarness()

  await service.refreshSchedulerConfig()
  await service.refreshAnalysisSummary()
  await service.refreshStructuredSummary()
  await service.refreshJobSummary()
  await service.refreshDuplicateSummary()

  assert.deepEqual(calls, ['scheduler', 'analysis', 'insight', 'jobs', 'duplicate'])
  assert.equal(loaded.scheduler, true)
  assert.equal(loaded.analysis, true)
  assert.equal(loaded.insight, true)
  assert.equal(loaded.jobs, true)
  assert.equal(loaded.duplicate, true)
  assert.deepEqual(state.analysisSummary, { runtime: { mode: 'basic' }, overview: { total_posts: 0 } })
  assert.deepEqual(state.insightSummary, { overview: { insight_posts: 0 } })
  assert.deepEqual(state.jobSummary, { overview: { total_jobs: 0 } })
  assert.deepEqual(state.duplicateSummary, { overview: { duplicate_posts: 0 } })
  assert.equal(forms.scheduler.defaultSourceId, 1)
})

test('retryTaskRun should submit action-specific rerun payloads and clear retry action state after completion', async () => {
  let receivedPayload = null
  const { service, state } = createHarness({
    adminApiOverrides: {
      runAiAnalysis: async (payload) => {
        receivedPayload = payload
        return { data: { message: '智能整理任务已提交' } }
      }
    }
  })

  await service.retryTaskRun(createCancelledIncrementalRun({
    id: 'run-ai-9'
  }), 'incremental')

  assert.deepEqual(receivedPayload, {
    source_id: 8,
    limit: 50,
    only_unanalyzed: true,
    rerun_of_task_id: 'run-ai-9'
  })
  assert.equal(state.retryingTaskId, '')
  assert.equal(state.retryingTaskActionKey, '')
})

test('retryTaskRun should rerun duplicate backfill with recheck_recent scope', async () => {
  let receivedPayload = null
  const { service, state } = createHarness({
    adminApiOverrides: {
      backfillDuplicates: async (payload) => {
        receivedPayload = payload
        return { data: { message: '历史去重补齐任务已提交' } }
      }
    }
  })

  await service.retryTaskRun({
    id: 'run-dup-9',
    task_type: 'duplicate_backfill',
    status: 'success',
    params: {
      limit: '50',
      scope_mode: 'unchecked'
    }
  }, 'rerun')

  assert.deepEqual(receivedPayload, {
    limit: 50,
    scope_mode: 'recheck_recent',
    rerun_of_task_id: 'run-dup-9'
  })
  assert.equal(state.retryingTaskId, '')
  assert.equal(state.retryingTaskActionKey, '')
})

test('retryTaskRun should reuse legacy task shape params for rerun payloads', async () => {
  let receivedPayload = null
  const { service, state } = createHarness({
    adminApiOverrides: {
      runAiAnalysis: async (payload) => {
        receivedPayload = payload
        return { data: { message: '智能整理任务已提交' } }
      }
    }
  })

  await service.retryTaskRun({
    ...createCancelledIncrementalRun({
      id: 'run-ai-legacy-1',
      taskType: 'ai_analysis'
    }),
    task_type: undefined,
    params: undefined,
    details: {
      params: {
        source_id: '6',
        limit: '40',
        only_unanalyzed: false
      }
    }
  }, 'incremental')

  assert.deepEqual(receivedPayload, {
    source_id: 6,
    limit: 40,
    only_unanalyzed: true,
    rerun_of_task_id: 'run-ai-legacy-1'
  })
  assert.equal(state.retryingTaskId, '')
  assert.equal(state.retryingTaskActionKey, '')
})

test('cancelTaskRun should submit cancel request and clear canceling state after completion', async () => {
  let cancelledTaskId = ''
  const { service, state } = createHarness({
    adminApiOverrides: {
      cancelTaskRun: async (taskId) => {
        cancelledTaskId = taskId
        return { data: { message: '终止请求已提交' } }
      }
    }
  })

  await service.cancelTaskRun({ id: 'run-ai-1' })

  assert.equal(cancelledTaskId, 'run-ai-1')
  assert.equal(state.cancelingTaskId, '')
})

test('runAiAnalysisTask should downgrade timeout into warning feedback after refreshing task state', async () => {
  const timeoutError = new Error('timeout')
  timeoutError.code = 'ECONNABORTED'

  const { service, feedback } = createHarness({
    adminApiOverrides: {
      runAiAnalysis: async () => { throw timeoutError }
    }
  })

  await service.runAiAnalysisTask()

  assert.equal(feedback.value.type, 'warning')
  assert.match(feedback.value.message, /已刷新当前状态/)
  assert.match(feedback.value.message, /确认是否已受理/)
})

test('runScrapeTask should convert 409 conflict into warning feedback instead of error copy', async () => {
  const conflictError = new Error('conflict')
  conflictError.response = {
    status: 409,
    data: { detail: '手动抓取最新数据已经在运行了，请先等当前任务结束后再试。若刚才页面超时了，先点“刷新记录”确认后台状态。' }
  }

  const { service, feedback } = createHarness({
    adminApiOverrides: {
      runScrape: async () => { throw conflictError }
    }
  })

  await service.runScrapeTask()

  assert.equal(feedback.value.type, 'warning')
  assert.match(feedback.value.message, /已有同类任务在运行/)
})

test('retryTaskRun should downgrade timeout into warning feedback in retry catch branch', async () => {
  const timeoutError = new Error('timeout')
  timeoutError.code = 'ECONNABORTED'

  const { service, feedback } = createHarness({
    adminApiOverrides: {
      runAiAnalysis: async () => { throw timeoutError }
    }
  })

  await service.retryTaskRun(createCancelledIncrementalRun({
    id: 'run-ai-timeout-1'
  }), 'incremental')

  assert.equal(feedback.value.type, 'warning')
  assert.match(feedback.value.message, /已刷新当前状态/)
  assert.match(feedback.value.message, /确认是否已受理/)
})

test('runAiAnalysisTask should keep refresh error feedback when timeout refresh fails', async () => {
  const timeoutError = new Error('timeout')
  timeoutError.code = 'ECONNABORTED'
  const refreshError = new Error('refresh-failed')

  const { service, feedback } = createHarness({
    adminApiOverrides: {
      runAiAnalysis: async () => { throw timeoutError },
      getTaskRuns: async () => { throw refreshError }
    }
  })

  await service.runAiAnalysisTask()

  assert.equal(feedback.value.type, 'error')
  assert.match(feedback.value.message, /加载任务记录失败/)
})

test('runAiAnalysisTask should keep timeout warning feedback when task summary falls back but task runs refresh succeeds', async () => {
  const timeoutError = new Error('timeout')
  timeoutError.code = 'ECONNABORTED'
  const summaryError = new Error('summary-failed')

  const originalWarn = console.warn
  console.warn = () => {}
  try {
    const { service, feedback, state } = createHarness({
      adminApiOverrides: {
        runAiAnalysis: async () => { throw timeoutError },
        getTaskSummary: async () => { throw summaryError },
        getTaskRuns: async () => ({ data: { items: [{ id: 'run-1' }] } })
      }
    })

    await service.runAiAnalysisTask()

    assert.equal(state.taskSummaryUnavailable, true)
    assert.equal(feedback.value.type, 'warning')
    assert.match(feedback.value.message, /已刷新当前状态/)
    assert.match(feedback.value.message, /确认是否已受理/)
  } finally {
    console.warn = originalWarn
  }
})

test('runAiAnalysisTask should keep timeout warning feedback when supplemental summaries fail after task center refresh succeeds', async () => {
  const timeoutError = new Error('timeout')
  timeoutError.code = 'ECONNABORTED'
  const analysisError = new Error('analysis-failed')

  const { service, feedback, state } = createHarness({
    adminApiOverrides: {
      runAiAnalysis: async () => { throw timeoutError },
      getTaskRuns: async () => ({ data: { items: [{ id: 'run-3' }] } }),
      getTaskSummary: async () => ({ data: { running_tasks: [{ id: 'run-3', task_type: 'ai_analysis' }] } }),
      getAnalysisSummary: async () => { throw analysisError }
    }
  })

  await service.runAiAnalysisTask()

  assert.match(state.taskStatusLastSyncedAt, /^20\d\d-/)
  assert.equal(feedback.value.type, 'warning')
  assert.match(feedback.value.message, /已刷新当前状态/)
  assert.match(feedback.value.message, /确认是否已受理/)
})

test('retryTaskRun should keep conflict warning feedback when task summary falls back but task runs refresh succeeds', async () => {
  const conflictError = new Error('conflict')
  conflictError.response = {
    status: 409,
    data: { detail: '手动抓取最新数据已经在运行了，请先等当前任务结束后再试。若刚才页面超时了，先点“刷新记录”确认后台状态。' }
  }
  const summaryError = new Error('summary-failed')

  const originalWarn = console.warn
  console.warn = () => {}
  try {
    const { service, feedback, state } = createHarness({
      adminApiOverrides: {
        runAiAnalysis: async () => { throw conflictError },
        getTaskSummary: async () => { throw summaryError },
        getTaskRuns: async () => ({ data: { items: [{ id: 'run-2' }] } })
      }
    })

    await service.retryTaskRun(createCancelledIncrementalRun({
      id: 'run-ai-conflict-1',
      params: {
        source_id: '9',
        limit: '20',
        only_unanalyzed: true
      }
    }), 'incremental')

    assert.equal(state.taskSummaryUnavailable, true)
    assert.equal(feedback.value.type, 'warning')
    assert.match(feedback.value.message, /已有同类任务在运行/)
  } finally {
    console.warn = originalWarn
  }
})

test('retryTaskRun should keep conflict warning feedback when supplemental summaries fail after task center refresh succeeds', async () => {
  const conflictError = new Error('conflict')
  conflictError.response = {
    status: 409,
    data: { detail: '手动抓取最新数据已经在运行了，请先等当前任务结束后再试。若刚才页面超时了，先点“刷新记录”确认后台状态。' }
  }
  const analysisError = new Error('analysis-failed')

  const { service, feedback, state } = createHarness({
    adminApiOverrides: {
      runAiAnalysis: async () => { throw conflictError },
      getTaskRuns: async () => ({ data: { items: [{ id: 'run-4' }] } }),
      getTaskSummary: async () => ({ data: { running_tasks: [{ id: 'run-4', task_type: 'ai_analysis' }] } }),
      getAnalysisSummary: async () => { throw analysisError }
    }
  })

  await service.retryTaskRun(createCancelledIncrementalRun({
    id: 'run-ai-conflict-2',
    params: {
      source_id: '9',
      limit: '20',
      only_unanalyzed: true
    }
  }), 'incremental')

  assert.match(state.taskStatusLastSyncedAt, /^20\d\d-/)
  assert.equal(feedback.value.type, 'warning')
  assert.match(feedback.value.message, /已有同类任务在运行/)
})

test('retryTaskRun should use action-specific fallback copy for plain rerun failures', async () => {
  const plainError = new Error('plain-failure')

  const { service, feedback } = createHarness({
    adminApiOverrides: {
      runAiAnalysis: async () => { throw plainError }
    }
  })

  await service.retryTaskRun({
    id: 'run-ai-rerun-plain-1',
    task_type: 'ai_analysis',
    status: 'success',
    params: {
      source_id: '9',
      limit: '20',
      only_unanalyzed: true
    }
  }, 'rerun')

  assert.equal(feedback.value.type, 'error')
  assert.equal(feedback.value.message, '再次运行失败')
})

test('retryTaskRun should reject action keys that current run does not expose', async () => {
  let apiCalled = false
  const { service, feedback } = createHarness({
    adminApiOverrides: {
      runAiAnalysis: async () => {
        apiCalled = true
        return { data: { message: '智能整理任务已提交' } }
      }
    }
  })

  await service.retryTaskRun({
    id: 'run-ai-unsupported-1',
    task_type: 'ai_analysis',
    status: 'success',
    actions: [{ key: 'rerun', label: '重新整理当前范围' }],
    params: {
      source_id: '8',
      limit: '50',
      only_unanalyzed: false
    }
  }, 'incremental')

  assert.equal(apiCalled, false)
  assert.equal(feedback.value.type, 'error')
  assert.equal(feedback.value.message, '当前记录暂不支持这个操作。')
})

test('refreshTaskStatus should stamp the latest task-status sync time', async () => {
  const { service, state } = createHarness()

  await service.refreshTaskStatus()

  assert.match(state.taskStatusLastSyncedAt, /^20\d\d-/)
})

test('refreshTaskStatus should not stamp sync time when task runs fail and task summary only falls back', async () => {
  const taskRunsError = new Error('task-runs-failed')
  const taskSummaryError = new Error('task-summary-failed')
  const originalWarn = console.warn
  console.warn = () => {}

  try {
    const { service, state } = createHarness({
      adminApiOverrides: {
        getTaskRuns: async () => { throw taskRunsError },
        getTaskSummary: async () => { throw taskSummaryError }
      }
    })

    const refreshSucceeded = await service.refreshTaskStatus()

    assert.equal(refreshSucceeded, false)
    assert.equal(state.taskSummaryUnavailable, true)
    assert.equal(state.taskStatusLastSyncedAt, '')
  } finally {
    console.warn = originalWarn
  }
})

test('fetchTaskRuns should keep contextual fallback copy for 500 responses', async () => {
  const serverError = new Error('server-error')
  serverError.response = { status: 500, data: {} }

  const { service, feedback } = createHarness({
    adminApiOverrides: {
      getTaskRuns: async () => { throw serverError }
    }
  })

  const succeeded = await service.fetchTaskRuns()

  assert.equal(succeeded, false)
  assert.equal(feedback.value.type, 'error')
  assert.equal(feedback.value.message, '加载任务记录失败')
})

test('verifyAdminAccess should keep timeout feedback contextual when session check times out', async () => {
  const timeoutError = new Error('timeout')
  timeoutError.code = 'ECONNABORTED'

  const { service, feedback } = createHarness({
    adminApiOverrides: {
      getSession: async () => { throw timeoutError }
    }
  })

  const succeeded = await service.verifyAdminAccess()

  assert.equal(succeeded, false)
  assert.equal(feedback.value.type, 'error')
  assert.equal(feedback.value.message, '验证登录状态失败')
})

test('submitAdminLogin should keep timeout feedback contextual when login request times out', async () => {
  const timeoutError = new Error('timeout')
  timeoutError.code = 'ECONNABORTED'

  const { service, adminAuthError, adminAuthForm } = createHarness({
    adminApiOverrides: {
      login: async () => { throw timeoutError }
    }
  })
  adminAuthForm.username = 'admin'
  adminAuthForm.password = 'secret'

  await service.submitAdminLogin()

  assert.equal(adminAuthError.value, '登录失败')
})

test('refreshTaskStatus should not stamp sync time when task runs fail but task summary succeeds', async () => {
  const taskRunsError = new Error('task-runs-failed')

  const { service, state } = createHarness({
    adminApiOverrides: {
      getTaskRuns: async () => { throw taskRunsError },
      getTaskSummary: async () => ({ data: { running_tasks: [{ id: 'run-summary-only', task_type: 'manual_scrape' }] } })
    }
  })

  const refreshSucceeded = await service.refreshTaskStatus()

  assert.equal(refreshSucceeded, false)
  assert.equal(state.taskSummaryUnavailable, false)
  assert.deepEqual(state.taskSummary, { running_tasks: [{ id: 'run-summary-only', task_type: 'manual_scrape' }] })
  assert.equal(state.taskStatusLastSyncedAt, '')
})

test('refreshTaskStatus should ignore stale task-center responses from older refreshes', async () => {
  const originalDate = global.Date
  const timestamps = [
    '2026-04-01T10:00:01.000Z',
    '2026-04-01T10:00:09.000Z'
  ]
  let stampIndex = 0

  class FakeDate extends originalDate {
    constructor(...args) {
      super(...(args.length ? args : [timestamps[Math.min(stampIndex, timestamps.length - 1)]]))
    }

    static now() {
      return originalDate.parse(timestamps[Math.min(stampIndex, timestamps.length - 1)])
    }

    static parse(value) {
      return originalDate.parse(value)
    }

    static UTC(...args) {
      return originalDate.UTC(...args)
    }
  }

  global.Date = FakeDate

  const runsFirst = createDeferred()
  const runsSecond = createDeferred()
  const summaryFirst = createDeferred()
  const summarySecond = createDeferred()
  let runsCallIndex = 0
  let summaryCallIndex = 0

  try {
    const { service, state } = createHarness({
      adminApiOverrides: {
        getTaskRuns: async () => (runsCallIndex++ === 0 ? runsFirst.promise : runsSecond.promise),
        getTaskSummary: async () => (summaryCallIndex++ === 0 ? summaryFirst.promise : summarySecond.promise)
      }
    })

    const firstRefresh = service.refreshTaskStatus()
    const secondRefresh = service.refreshTaskStatus()

    runsSecond.resolve({ data: { items: [{ id: 'fresh-run' }] } })
    summarySecond.resolve({ data: { running_tasks: [{ id: 'fresh-run', task_type: 'manual_scrape' }] } })

    await secondRefresh

    const syncedAfterFreshRefresh = state.taskStatusLastSyncedAt

    assert.deepEqual(state.taskRuns, [{ id: 'fresh-run' }])
    assert.deepEqual(state.taskSummary, { running_tasks: [{ id: 'fresh-run', task_type: 'manual_scrape' }] })
    assert.equal(syncedAfterFreshRefresh, '2026-04-01T10:00:01.000Z')

    stampIndex = 1
    runsFirst.resolve({ data: { items: [{ id: 'stale-run' }] } })
    summaryFirst.resolve({ data: { running_tasks: [{ id: 'stale-run', task_type: 'manual_scrape' }] } })

    await firstRefresh

    assert.deepEqual(state.taskRuns, [{ id: 'fresh-run' }])
    assert.deepEqual(state.taskSummary, { running_tasks: [{ id: 'fresh-run', task_type: 'manual_scrape' }] })
    assert.equal(state.taskStatusLastSyncedAt, syncedAfterFreshRefresh)
  } finally {
    global.Date = originalDate
  }
})

test('runAiAnalysisTask should stop timeout info feedback when supplemental refresh loses auth', async () => {
  const timeoutError = new Error('timeout')
  timeoutError.code = 'ECONNABORTED'
  const authError = new Error('auth-lost')
  authError.response = {
    status: 503,
    data: { detail: '管理会话暂不可用。' }
  }

  const { service, feedback, state, adminAuthorized, adminAuthError } = createHarness({
    adminApiOverrides: {
      runAiAnalysis: async () => { throw timeoutError },
      getTaskRuns: async () => ({ data: { items: [{ id: 'run-auth-refresh' }] } }),
      getTaskSummary: async () => ({ data: { running_tasks: [{ id: 'run-auth-refresh', task_type: 'ai_analysis' }] } }),
      getAnalysisSummary: async () => { throw authError }
    }
  })

  await service.runAiAnalysisTask()

  assert.equal(adminAuthorized.value, false)
  assert.match(adminAuthError.value, /暂不可用|重新登录/)
  assert.equal(feedback.value.message, '')
  assert.equal(state.taskStatusLastSyncedAt, '')
})

test('refreshTaskStatus should not stamp sync time after auth loss even when task runs succeed', async () => {
  const authError = new Error('auth-lost')
  authError.response = {
    status: 503,
    data: { detail: '管理会话暂不可用。' }
  }

  const { service, state, adminAuthorized, adminAuthError } = createHarness({
    adminApiOverrides: {
      getTaskRuns: async () => ({ data: { items: [{ id: 'run-auth-1' }] } }),
      getTaskSummary: async () => { throw authError }
    }
  })

  const refreshSucceeded = await service.refreshTaskStatus()

  assert.equal(refreshSucceeded, false)
  assert.equal(adminAuthorized.value, false)
  assert.match(adminAuthError.value, /暂不可用|重新登录/)
  assert.equal(state.taskStatusLastSyncedAt, '')
})

test('refreshOverview should not stamp sync time after auth loss even when task runs succeed', async () => {
  const authError = new Error('auth-lost')
  authError.response = {
    status: 503,
    data: { detail: '管理会话暂不可用。' }
  }

  const { service, state, adminAuthorized, adminAuthError } = createHarness({
    adminApiOverrides: {
      getTaskRuns: async () => ({ data: { items: [{ id: 'run-auth-2' }] } }),
      getTaskSummary: async () => { throw authError }
    }
  })

  const refreshSucceeded = await service.refreshOverview()

  assert.equal(refreshSucceeded, false)
  assert.equal(adminAuthorized.value, false)
  assert.match(adminAuthError.value, /暂不可用|重新登录/)
  assert.equal(state.taskStatusLastSyncedAt, '')
})

test('refreshOverview should ignore late responses after logout clears admin runtime state', async () => {
  const taskRuns = createDeferred()
  const taskSummary = createDeferred()
  const scheduler = createDeferred()
  const analysis = createDeferred()
  const insight = createDeferred()
  const jobs = createDeferred()
  const duplicate = createDeferred()

  const { service, state, loaded, adminAuthorized, feedback } = createHarness({
    adminApiOverrides: {
      getTaskRuns: async () => taskRuns.promise,
      getTaskSummary: async () => taskSummary.promise,
      getSchedulerConfig: async () => scheduler.promise,
      getAnalysisSummary: async () => analysis.promise,
      getInsightSummary: async () => insight.promise,
      getJobSummary: async () => jobs.promise,
      getDuplicateSummary: async () => duplicate.promise,
      logout: async () => ({})
    }
  })

  const refreshPromise = service.refreshOverview()
  await service.logoutAdmin()

  taskSummary.resolve({ data: { running_tasks: [{ id: 'stale-summary-run', task_type: 'manual_scrape' }] } })
  taskRuns.resolve({ data: { items: [{ id: 'stale-run', task_type: 'manual_scrape', status: 'running' }] } })
  scheduler.resolve({
    data: {
      enabled: true,
      interval_seconds: 7200,
      default_source_id: 1,
      default_max_pages: 5
    }
  })
  analysis.resolve({ data: { runtime: { mode: 'basic' }, overview: { total_posts: 3 } } })
  insight.resolve({ data: { overview: { insight_posts: 2 } } })
  jobs.resolve({ data: { overview: { total_jobs: 8 } } })
  duplicate.resolve({ data: { overview: { duplicate_posts: 1 } } })

  await refreshPromise

  assert.equal(adminAuthorized.value, false)
  assert.deepEqual(state.taskRuns, [])
  assert.equal(state.taskSummary, null)
  assert.equal(state.analysisSummary, null)
  assert.equal(state.insightSummary, null)
  assert.equal(state.jobSummary, null)
  assert.equal(state.duplicateSummary, null)
  assert.equal(loaded.taskRuns, false)
  assert.equal(loaded.taskSummary, false)
  assert.equal(loaded.analysis, false)
  assert.equal(loaded.insight, false)
  assert.equal(loaded.jobs, false)
  assert.equal(loaded.duplicate, false)
  assert.equal(state.taskStatusLastSyncedAt, '')
  assert.equal(feedback.value.type, 'success')
  assert.equal(feedback.value.message, '已退出登录')
})
