import test from 'node:test'
import assert from 'node:assert/strict'

import { buildAdminHealthState } from '../src/views/admin/adminDashboardHealth.js'

const createHealthInput = (overrides = {}) => ({
  overviewReady: true,
  schedulerEnabled: true,
  latestFailedTask: null,
  latestSuccessTask: {
    taskType: 'manual_scrape',
    finishedAt: '2026-03-30T10:00:00Z'
  },
  analysisRuntime: {
    analysis_enabled: true,
    openai_ready: false
  },
  analysisOverview: {
    base_pending_posts: 0,
    openai_pending_posts: 12
  },
  insightOverview: {
    pending_insight_posts: 0
  },
  jobsOverview: {
    pending_posts: 0
  },
  ...overrides
})

test('buildAdminHealthState keeps basic mode healthy when only AI backlog remains', () => {
  const health = buildAdminHealthState(createHealthInput())

  assert.equal(health.level, 'healthy')
  assert.equal(health.label, '正常')
  assert.match(health.summary, /基础模式|基础处理/)
  assert.ok(health.alerts.every((item) => !/AI 增强未开启|基础模式/.test(item)))
  assert.ok(health.alerts.every((item) => !/待 AI 增强分析/.test(item)))
})

test('buildAdminHealthState counts AI backlog only when AI enhancement is truly available', () => {
  const health = buildAdminHealthState(
    createHealthInput({
      analysisRuntime: {
        analysis_enabled: true,
        openai_ready: true
      }
    })
  )

  assert.equal(health.level, 'attention')
  assert.ok(health.alerts.some((item) => /待 AI 增强分析/.test(item)))
})

test('buildAdminHealthState should keep explicit disabled runtime healthy when base chain has no backlog', () => {
  const health = buildAdminHealthState(
    createHealthInput({
      analysisRuntime: {
        mode: 'disabled',
        analysis_enabled: false,
        openai_ready: false
      },
      analysisOverview: {
        base_pending_posts: 0,
        openai_pending_posts: 0
      }
    })
  )

  assert.equal(health.level, 'healthy')
  assert.match(health.summary, /基础处理链路仍可继续推进/)
  assert.ok(health.alerts.every((item) => !/都不会继续推进/.test(item)))
})
