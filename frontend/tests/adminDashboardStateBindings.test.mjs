import test from 'node:test'
import assert from 'node:assert/strict'
import { computed, ref } from 'vue'

import {
  buildSystemSectionModel,
  buildTaskRunsSectionModel
} from '../src/views/admin/adminDashboardSectionAdapters.js'
import {
  ADMIN_SECTION_ORDER,
  PROCESSING_MODE_ORDER,
  collectBackendRunningTasks,
  normalizeAdminDashboardBindings,
  normalizeAdminSection,
  normalizeProcessingMode
} from '../src/views/admin/useAdminDashboardState.js'

test('normalizeAdminDashboardBindings should unwrap refs and computed section models for template access', () => {
  const dashboard = normalizeAdminDashboardBindings({
    activeAdminSection: ref('overview'),
    taskRunsSection: computed(() => ({
      taskRuns: [],
      taskRunsLoaded: true
    })),
    setActiveSection(value) {
      this.lastValue = value
    }
  })

  assert.equal(dashboard.activeAdminSection, 'overview')
  assert.deepEqual(dashboard.taskRunsSection.taskRuns, [])
  assert.equal(dashboard.taskRunsSection.taskRunsLoaded, true)
  assert.equal(typeof dashboard.setActiveSection, 'function')
})

test('normalizeAdminSection should collapse legacy ai enhancement routing into processing', () => {
  assert.deepEqual(ADMIN_SECTION_ORDER, ['overview', 'processing', 'tasks', 'system'])
  assert.equal(normalizeAdminSection('ai-enhancement'), 'processing')
  assert.equal(normalizeAdminSection('governance'), 'processing')
  assert.equal(normalizeAdminSection('unknown-section'), 'overview')
})

test('normalizeProcessingMode should keep processing tabs inside base and ai modes', () => {
  assert.deepEqual(PROCESSING_MODE_ORDER, ['base', 'ai'])
  assert.equal(normalizeProcessingMode('base'), 'base')
  assert.equal(normalizeProcessingMode('ai'), 'ai')
  assert.equal(normalizeProcessingMode('other'), 'base')
})

test('normalizeAdminDashboardBindings should preserve syncStatus on taskRunsSection', () => {
  const dashboard = normalizeAdminDashboardBindings({
    taskRunsSection: computed(() => ({
      taskRuns: [],
      taskRunsLoaded: true,
      syncStatus: {
        badgeLabel: '自动刷新中',
        lastSyncedLabel: '2026/04/01 18:00'
      }
    }))
  })

  assert.equal(dashboard.taskRunsSection.syncStatus.badgeLabel, '自动刷新中')
  assert.equal(dashboard.taskRunsSection.syncStatus.lastSyncedLabel, '2026/04/01 18:00')
})

test('normalizeAdminDashboardBindings should preserve section-local error and save blocking fields', () => {
  const dashboard = normalizeAdminDashboardBindings({
    taskRunsSection: computed(() => buildTaskRunsSectionModel({
      taskRuns: [],
      taskRunsLoaded: false,
      taskRunsError: '加载任务记录失败',
      loadingRuns: false,
      retryingTaskId: '',
      retryingTaskActionKey: '',
      cancelingTaskId: '',
      expandedTaskIds: [],
      nowTs: Date.now(),
      sourceOptions: [],
      heartbeatStaleMs: 600000,
      syncStatus: {
        badgeLabel: '手动刷新',
        lastSyncedLabel: '尚未同步'
      }
    })),
    systemSection: computed(() => buildSystemSectionModel({
      schedulerForm: {
        enabled: true,
        intervalSeconds: 7200,
        defaultSourceId: '',
        defaultMaxPages: 5,
        nextRunAt: '',
        updatedAt: ''
      },
      schedulerLoaded: false,
      schedulerLoading: false,
      schedulerSaving: false,
      schedulerConfigError: '加载定时抓取配置失败',
      sourceOptions: []
    }))
  })

  assert.equal(dashboard.taskRunsSection.taskRunsError, '加载任务记录失败')
  assert.equal(dashboard.systemSection.saveDisabled, true)
  assert.match(dashboard.systemSection.saveBlockedReason, /先刷新配置/)
})

test('collectBackendRunningTasks should keep summary-only running tasks when task run snapshot is unavailable', () => {
  const runningTasks = collectBackendRunningTasks({
    adminAuthorized: true,
    taskSummary: {
      running_tasks: [
        { id: 'summary-run-1', task_type: 'manual_scrape', status: 'running' },
        { id: 'summary-run-1', task_type: 'manual_scrape', status: 'running' }
      ]
    },
    taskRuns: []
  })

  assert.deepEqual(runningTasks, [
    { id: 'summary-run-1', task_type: 'manual_scrape', status: 'running' }
  ])
})

test('buildSystemSectionModel should keep save enabled when a stale scheduler snapshot remains usable after refresh failure', () => {
  const model = buildSystemSectionModel({
    schedulerForm: {
      enabled: true,
      intervalSeconds: 7200,
      defaultSourceId: 1,
      defaultMaxPages: 5,
      nextRunAt: '2026-04-05T09:00:00Z',
      updatedAt: '2026-04-05T08:30:00Z'
    },
    schedulerLoaded: true,
    schedulerLoading: false,
    schedulerSaving: false,
    schedulerConfigError: '加载定时抓取配置失败',
    sourceOptions: [{ label: '江苏省人社厅', value: 1, isActive: true }]
  })

  assert.equal(model.saveDisabled, false)
  assert.equal(model.saveBlockedReason, '')
  assert.match(model.schedulerRefreshNotice.description, /仍显示上次成功加载的配置/)
})
