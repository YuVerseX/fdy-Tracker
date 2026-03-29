import test from 'node:test'
import assert from 'node:assert/strict'

import { getPublicFreshnessHeadline } from '../src/utils/publicFreshness.js'

test('getPublicFreshnessHeadline should use scrape wording', () => {
  assert.equal(
    getPublicFreshnessHeadline({ taskLabel: '定时抓取', finishedAt: '2026-03-27T10:00:00+00:00' }),
    '最近抓取成功任务：定时抓取'
  )
})

test('getPublicFreshnessHeadline should fallback when no success exists', () => {
  assert.equal(getPublicFreshnessHeadline(null), '还没有可展示的抓取成功任务记录。')
})
