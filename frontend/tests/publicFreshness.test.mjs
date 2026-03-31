import test from 'node:test'
import assert from 'node:assert/strict'

import { getPublicFreshnessHeadline } from '../src/utils/publicFreshness.js'
import { getPublicTaskTypeLabel } from '../src/utils/taskTypeLabels.js'

test('getPublicFreshnessHeadline should use scrape wording', () => {
  assert.equal(
    getPublicFreshnessHeadline({ taskLabel: '定时抓取', finishedAt: '2026-03-27T10:00:00+00:00' }),
    '最近内容已更新'
  )
})

test('getPublicFreshnessHeadline should fallback when no success exists', () => {
  assert.equal(getPublicFreshnessHeadline(null), '最近内容更新时间暂时不可用。')
})

test('getPublicTaskTypeLabel should normalize public-facing freshness copy', () => {
  assert.equal(getPublicTaskTypeLabel('manual_scrape'), '手动抓取')
  assert.equal(getPublicTaskTypeLabel('scheduled_scrape'), '定时抓取')
  assert.equal(getPublicTaskTypeLabel('job_extraction'), '岗位整理')
})
