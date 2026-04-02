import test from 'node:test'
import assert from 'node:assert/strict'

import { getPublicFreshnessHeadline } from '../src/utils/publicFreshness.js'
import { normalizeLatestSuccessTask } from '../src/utils/taskFreshness.js'
import { getPublicTaskTypeLabel } from '../src/utils/taskTypeLabels.js'

test('getPublicFreshnessHeadline should use latest successful snapshot wording when success exists', () => {
  assert.equal(
    getPublicFreshnessHeadline({ taskLabel: '定时抓取', finishedAt: '2026-03-27T10:00:00+00:00' }),
    '最近一次成功完成'
  )
})

test('getPublicFreshnessHeadline should fallback when no success exists', () => {
  assert.equal(getPublicFreshnessHeadline(null), '最近抓取记录暂时不可用。')
})

test('getPublicTaskTypeLabel should normalize public-facing freshness copy', () => {
  assert.equal(getPublicTaskTypeLabel('manual_scrape'), '手动抓取')
  assert.equal(getPublicTaskTypeLabel('scheduled_scrape'), '定时抓取')
  assert.equal(getPublicTaskTypeLabel('job_extraction'), '岗位整理')
})

test('normalizeLatestSuccessTask should fallback to top-level latest_success_at when run payload is absent', () => {
  assert.deepEqual(
    normalizeLatestSuccessTask({
      latest_success_at: '2026-03-31T10:00:00+00:00'
    }),
    {
      taskType: '',
      taskLabel: '',
      finishedAt: '2026-03-31T10:00:00+00:00'
    }
  )
})
