import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildTaskRequestConfig,
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
