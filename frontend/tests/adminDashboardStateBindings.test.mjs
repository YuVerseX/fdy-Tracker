import test from 'node:test'
import assert from 'node:assert/strict'
import { computed, ref } from 'vue'

import { normalizeAdminDashboardBindings } from '../src/views/admin/useAdminDashboardState.js'

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
