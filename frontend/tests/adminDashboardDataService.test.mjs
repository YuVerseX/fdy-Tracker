import test from 'node:test'
import assert from 'node:assert/strict'

import { createAdminDashboardDataService } from '../src/views/admin/adminDashboardDataService.js'

function createHarness() {
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
    }
  }
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
    jobsSummaryUnavailable: false
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

  return { calls, service, state, loaded, forms }
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
