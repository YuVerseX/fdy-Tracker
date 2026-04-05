import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildPostParams,
  buildEventTypeOptionParams,
  buildStatsParams,
  DEFAULT_COUNSELOR_SCOPE
} from '../src/utils/postFilters.js'

test('buildPostParams should default event_type to 招聘公告 when filters.eventType is empty', () => {
  const params = buildPostParams({
    searchQuery: '南京大学',
    filters: {
      eventType: '',
      counselorScope: DEFAULT_COUNSELOR_SCOPE
    },
    defaultCounselorScope: DEFAULT_COUNSELOR_SCOPE
  })

  assert.equal(params.search, '南京大学')
  assert.equal(params.event_type, '招聘公告')
})

test('buildPostParams should keep explicit eventType instead of default value', () => {
  const params = buildPostParams({
    searchQuery: '南京大学',
    filters: {
      eventType: '结果公示',
      counselorScope: DEFAULT_COUNSELOR_SCOPE
    },
    defaultCounselorScope: DEFAULT_COUNSELOR_SCOPE
  })

  assert.equal(params.search, '南京大学')
  assert.equal(params.event_type, '结果公示')
})

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

test('buildStatsParams should default event_type to 招聘公告 when filters.eventType is empty', () => {
  const params = buildStatsParams({
    days: 7,
    searchQuery: '南京大学',
    filters: {
      eventType: '',
      counselorScope: DEFAULT_COUNSELOR_SCOPE
    },
    defaultCounselorScope: DEFAULT_COUNSELOR_SCOPE
  })

  assert.equal(params.days, 7)
  assert.equal(params.search, '南京大学')
  assert.equal(params.event_type, '招聘公告')
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

test('buildEventTypeOptionParams should not inject default event_type when filters.eventType is empty', () => {
  const params = buildEventTypeOptionParams({
    days: 7,
    searchQuery: '南京大学',
    filters: {
      eventType: '',
      counselorScope: DEFAULT_COUNSELOR_SCOPE
    },
    defaultCounselorScope: DEFAULT_COUNSELOR_SCOPE
  })

  assert.equal(params.days, 7)
  assert.equal(params.search, '南京大学')
  assert.ok(!('event_type' in params))
  assert.equal(params.is_counselor, true)
})
