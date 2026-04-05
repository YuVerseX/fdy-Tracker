import test from 'node:test'
import assert from 'node:assert/strict'

import { getAdminRuntimeCopy } from '../src/utils/adminDashboardMeta.js'
import {
  buildAiEnhancementSectionModel,
  buildDataProcessingSectionModel,
  buildProcessingSectionModel,
  buildOverviewSectionModel,
  buildSystemSectionModel,
  buildTaskRunsSectionModel
} from '../src/views/admin/adminDashboardSectionAdapters.js'
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
  assert.ok(recentTaskCard.meta.some((item) => /最近任务记录/.test(item)))
  assert.ok(recentTaskCard.meta.every((item) => !/接口/.test(item)))
  assert.equal(section.focusItems[0].title, '接下来优先处理')
  assert.match(section.focusItems[0].description, /先补齐关键信息整理|先运行一次任务|最近任务/)
})

test('section model should not expose design-note copy to end users', () => {
  const section = buildTaskRunsSectionModel({
    taskRuns: [],
    taskRunsLoaded: true,
    loadingRuns: false,
    retryingTaskId: '',
    retryingTaskActionKey: 'incremental',
    expandedTaskIds: [],
    nowTs: Date.now(),
    sourceOptions: [],
    heartbeatStaleMs: 600000
  })

  const text = JSON.stringify(section)

  assert.equal(section.retryingTaskActionKey, 'incremental')
  assert.doesNotMatch(text, /默认先看当前异常和最近结果/)
  assert.doesNotMatch(text, /避免把基础处理和 AI 增强混在一起/)
})

test('buildProcessingSectionModel should group base and ai work under shared processing tabs', () => {
  const section = buildProcessingSectionModel({
    mode: 'ai',
    tabOptions: [
      { value: 'base', label: '基础处理' },
      { value: 'ai', label: '智能整理' }
    ],
    baseSection: {
      collectPanel: { id: 'collect-and-backfill' }
    },
    aiSection: {
      panels: [{ id: 'ai-runtime-status' }]
    }
  })

  assert.equal(section.mode, 'ai')
  assert.deepEqual(
    section.tabOptions.map((item) => item.value),
    ['base', 'ai']
  )
  assert.equal(section.baseSection.collectPanel.id, 'collect-and-backfill')
  assert.equal(section.aiSection.panels[0].id, 'ai-runtime-status')
})

test('processing section adapters should preserve task action callbacks needed by action cards', () => {
  const noop = () => {}

  const baseSection = buildDataProcessingSectionModel({
    panels: [],
    sourceOptions: [],
    jobsSummaryUnavailable: false,
    forms: {
      scrape: {},
      backfill: {},
      duplicate: {},
      baseAnalysis: {},
      jobIndex: {}
    },
    busy: {},
    loading: {},
    runScrapeTask: noop,
    runBackfillTask: noop,
    runDuplicateBackfillTask: noop,
    runBaseAnalysisTask: noop,
    runJobIndexTask: noop,
    refreshDuplicateSummary: noop,
    refreshAnalysisSummary: noop,
    refreshJobSummary: noop
  })

  const aiSection = buildAiEnhancementSectionModel({
    runtimeCopy: { badge: 'ok' },
    openaiReady: true,
    disabledReason: '',
    panels: [],
    sourceOptions: [],
    forms: {
      analysis: {},
      jobs: {}
    },
    busy: {},
    loading: {},
    jobsSummaryUnavailable: false,
    latestLabels: {
      analysis: '',
      jobs: ''
    },
    runAiAnalysisTask: noop,
    runAiJobExtractionTask: noop,
    refreshAnalysisSummary: noop,
    refreshJobSummary: noop
  })

  assert.equal(baseSection.runBaseAnalysisTask, noop)
  assert.equal(baseSection.runJobIndexTask, noop)
  assert.equal(baseSection.refreshAnalysisSummary, noop)
  assert.equal(baseSection.refreshJobSummary, noop)
  assert.equal(aiSection.runAiAnalysisTask, noop)
  assert.equal(aiSection.runAiJobExtractionTask, noop)
  assert.equal(aiSection.refreshAnalysisSummary, noop)
  assert.equal(aiSection.refreshJobSummary, noop)
})

test('buildSystemSectionModel should expose concise schedule summary and save impact copy', () => {
  const section = buildSystemSectionModel({
    schedulerForm: {
      enabled: true,
      intervalSeconds: 7200,
      defaultSourceId: 1,
      defaultMaxPages: 5,
      nextRunAt: '2026-03-31T10:00:00Z'
    },
    schedulerLoaded: true,
    schedulerLoading: false,
    schedulerSaving: false,
    sourceOptions: [
      { label: '江苏省人社厅', value: 1 }
    ]
  })

  assert.equal(section.statusBadgeLabel, '自动抓取已启用')
  assert.deepEqual(
    section.summaryCards.map((item) => item.label),
    ['当前状态', '下次运行', '默认范围']
  )
  assert.match(section.summaryCards[2].value, /江苏省人社厅/)
  assert.match(section.helperNotice.description, /保存后会在下一次自动抓取时生效/)
  assert.doesNotMatch(section.helperNotice.description, /环境变量|接口/)
})

test('buildSystemSectionModel should surface proxy status, exit, and scope in system settings', () => {
  const section = buildSystemSectionModel({
    schedulerForm: {
      enabled: true,
      intervalSeconds: 7200,
      defaultSourceId: 1,
      defaultMaxPages: 5,
      nextRunAt: '2026-03-31T10:00:00Z'
    },
    schedulerLoaded: true,
    schedulerLoading: false,
    schedulerSaving: false,
    sourceOptions: [
      { label: '江苏省人社厅', value: 1 }
    ],
    analysisRuntime: {
      proxy_enabled: true,
      proxy_scheme: 'SOCKS5',
      proxy_display: '127.0.0.1:40000',
      proxy_scope: '抓取、附件下载、智能摘要整理、智能岗位识别统一复用'
    }
  })

  assert.deepEqual(
    section.summaryCards.map((item) => item.label),
    ['当前状态', '下次运行', '默认范围', '代理状态', '代理出口']
  )
  assert.equal(section.summaryCards[3].value, '已启用')
  assert.equal(section.summaryCards[4].value, 'SOCKS5 · 127.0.0.1:40000')
  assert.ok(section.runtimeFacts.some((item) => item.label === '代理范围'))
})

test('buildTaskRunsSectionModel should expose sync status metadata for the task center header', () => {
  const section = buildTaskRunsSectionModel({
    taskRuns: [],
    taskRunsLoaded: true,
    loadingRuns: false,
    retryingTaskId: '',
    retryingTaskActionKey: '',
    cancelingTaskId: '',
    expandedTaskIds: [],
    nowTs: Date.now(),
    sourceOptions: [],
    heartbeatStaleMs: 600000,
    syncStatus: {
      badgeLabel: '自动刷新中',
      badgeTone: 'info',
      intervalLabel: '15 秒',
      lastSyncedLabel: '2026/04/01 18:00',
      runningCountLabel: '2 条',
      summary: '每 15 秒自动同步一次任务状态。'
    }
  })

  assert.equal(section.syncStatus.badgeLabel, '自动刷新中')
  assert.equal(section.syncStatus.intervalLabel, '15 秒')
  assert.match(section.syncStatus.summary, /15 秒/)
})
