import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildPostCardView,
  buildPostListEmptyState,
  buildPostListMetricCards
} from '../src/utils/postListPresentation.js'

test('buildPostListMetricCards should keep the summary cards compact and ordered', () => {
  const cards = buildPostListMetricCards({
    totalMatchedPosts: 18,
    scopeTotals: {
      dedicated: 8,
      contains: 6,
      all: 30
    }
  })

  assert.deepEqual(
    cards.map((item) => item.label),
    ['当前结果', '只招辅导员', '含辅导员岗位', '全部公告']
  )
  assert.equal(cards[0].value, '18')
})

test('buildPostCardView should turn snapshot data into readable facts and badges', () => {
  const view = buildPostCardView({
    title: '苏州大学 2026 年辅导员招聘公告',
    publish_date: '2026-03-01',
    source: { name: '苏州大学人事处' },
    is_counselor: true,
    counselor_scope: 'dedicated',
    has_content: true,
    analysis: {
      event_type: '事业单位招聘'
    },
    job_snapshot: {
      job_name: '专职辅导员',
      recruitment_count: '2人',
      education_requirement: '硕士研究生',
      location: '苏州'
    }
  })

  assert.equal(view.highlight, '专职辅导员')
  assert.deepEqual(
    view.facts.map((item) => item.value),
    ['2人', '硕士研究生', '苏州']
  )
  assert.ok(view.badges.some((item) => item.label === '只招辅导员'))
  assert.ok(view.badges.some((item) => item.label === '已收录正文'))
  assert.ok(view.meta.some((item) => item.label === '来源'))
})

test('buildPostListEmptyState should distinguish filtered results from first-load empty state', () => {
  assert.deepEqual(
    buildPostListEmptyState({ hasFilters: true }),
    {
      title: '当前条件下还没有匹配结果',
      description: '可以放宽筛选条件，或者换一个关键词再试试。'
    }
  )

  assert.deepEqual(
    buildPostListEmptyState({ hasFilters: false }),
    {
      title: '暂时还没有可浏览的招聘公告',
      description: '稍后再来看看，或等待下一次抓取完成。'
    }
  )
})
