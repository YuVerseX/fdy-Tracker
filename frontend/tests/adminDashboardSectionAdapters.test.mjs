import test from 'node:test'
import assert from 'node:assert/strict'

import { getAdminRuntimeCopy } from '../src/utils/adminDashboardMeta.js'
import { buildOverviewSectionModel } from '../src/views/admin/adminDashboardSectionAdapters.js'
import { buildRecentTaskState } from '../src/views/admin/adminDashboardTaskSummary.js'

test('buildRecentTaskState falls back to task runs when task summary is unavailable', () => {
  const taskState = buildRecentTaskState({
    taskSummary: null,
    taskSummaryLoaded: false,
    taskSummaryUnavailable: true,
    taskRunsLoaded: true,
    taskRuns: [
      {
        task_type: 'manual_scrape',
        status: 'success',
        finished_at: '2026-03-30T09:00:00Z',
        summary: '抓取完成'
      },
      {
        task_type: 'base_analysis_backfill',
        status: 'failed',
        finished_at: '2026-03-30T08:30:00Z',
        summary: '分析失败'
      }
    ]
  })

  assert.equal(taskState.recentTaskLoaded, true)
  assert.equal(taskState.isDegraded, true)
  assert.equal(taskState.latestSuccessTask.taskType, 'manual_scrape')
  assert.equal(taskState.latestFailedTask.taskType, 'base_analysis_backfill')
})

test('buildOverviewSectionModel surfaces degraded fallback instead of staying in loading state', () => {
  const recentTaskState = buildRecentTaskState({
    taskSummary: null,
    taskSummaryLoaded: false,
    taskSummaryUnavailable: true,
    taskRunsLoaded: true,
    taskRuns: [
      {
        task_type: 'manual_scrape',
        status: 'success',
        finished_at: '2026-03-30T09:00:00Z',
        summary: '抓取完成'
      }
    ]
  })

  const section = buildOverviewSectionModel({
    health: {
      panelClass: 'panel',
      badgeClass: 'badge',
      textClass: 'text',
      label: '正常',
      summary: '基础链路正常',
      alerts: []
    },
    refreshing: false,
    runtimeCopy: getAdminRuntimeCopy({
      analysis_enabled: true,
      openai_ready: false
    }),
    schedulerLoaded: true,
    schedulerForm: {
      enabled: true,
      intervalSeconds: 7200,
      nextRunAt: '',
      defaultMaxPages: 5
    },
    jobsLoaded: true,
    jobsOverview: {
      total_jobs: 12,
      posts_with_jobs: 4,
      pending_posts: 0
    },
    recentTaskState,
    analysisLoaded: true,
    analysisOverview: {
      base_ready_posts: 10,
      openai_analyzed_posts: 0,
      total_posts: 10
    },
    insightLoaded: true,
    insightOverview: {
      insight_posts: 10
    },
    structureRefreshing: false
  })

  const recentTaskCard = section.cards.find((card) => card.id === 'recent-task')

  assert.equal(recentTaskCard.value, '手动抓取最新数据')
  assert.ok(recentTaskCard.meta.some((item) => /任务摘要接口不可用/.test(item)))
})
