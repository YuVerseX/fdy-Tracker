import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildEventTypeOptionParams,
  buildStatsParams,
  DEFAULT_COUNSELOR_SCOPE
} from '../src/utils/postFilters.js'

test('buildStatsParams should keep event_type filter in stats query', () => {
  const params = buildStatsParams({
    days: 7,
    searchQuery: '南京大学',
    filters: {
      gender: '',
      education: '',
      location: '南京',
      eventType: '招聘公告',
      counselorScope: 'dedicated',
      hasContent: true
    },
    defaultCounselorScope: DEFAULT_COUNSELOR_SCOPE
  })

  assert.equal(params.days, 7)
  assert.equal(params.search, '南京大学')
  assert.equal(params.location, '南京')
  assert.equal(params.event_type, '招聘公告')
  assert.equal(params.has_content, true)
  assert.equal(params.counselor_scope, 'dedicated')
  assert.equal(params.is_counselor, true)
})

test('buildEventTypeOptionParams should exclude current event_type but keep other filters and counselor scope', () => {
  const params = buildEventTypeOptionParams({
    days: 7,
    searchQuery: '南京大学',
    filters: {
      gender: '女',
      education: '硕士',
      location: '南京',
      eventType: '招聘公告',
      counselorScope: 'dedicated',
      hasContent: true
    },
    defaultCounselorScope: DEFAULT_COUNSELOR_SCOPE
  })

  assert.equal(params.days, 7)
  assert.equal(params.search, '南京大学')
  assert.equal(params.gender, '女')
  assert.equal(params.education, '硕士')
  assert.equal(params.location, '南京')
  assert.ok(!('event_type' in params))
  assert.equal(params.has_content, true)
  assert.equal(params.counselor_scope, 'dedicated')
  assert.equal(params.is_counselor, true)
})
