import test from 'node:test'
import assert from 'node:assert/strict'
import { computed, ref } from 'vue'

import {
  ADMIN_SECTION_ORDER,
  PROCESSING_MODE_ORDER,
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
