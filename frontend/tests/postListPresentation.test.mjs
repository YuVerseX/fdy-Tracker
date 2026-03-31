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

test('buildPostCardView should summarize multi-job posts with announcement-level facts instead of the first job only', () => {
  const view = buildPostCardView({
    title: '南京师范大学2026年公开招聘专职辅导员公告',
    publish_date: '2026-03-20',
    source: { name: '江苏省人力资源和社会保障厅' },
    is_counselor: true,
    counselor_scope: 'dedicated',
    has_content: true,
    fields: [
      { field_name: '岗位名称', field_value: '专职辅导员；专职辅导员（男）；专职辅导员（女）；心理健康教育专职辅导员' },
      { field_name: '招聘人数', field_value: '8人；4人；3人；1人' },
      { field_name: '工作地点', field_value: '南京市' }
    ],
    job_items: [
      { job_name: '专职辅导员', recruitment_count: '8人', education_requirement: '博士研究生', location: '南京市' },
      { job_name: '心理健康教育专职辅导员', recruitment_count: '1人', education_requirement: '硕士研究生及以上' },
      { job_name: '专职辅导员（男）', recruitment_count: '4人', education_requirement: '硕士研究生及以上' },
      { job_name: '专职辅导员（女）', recruitment_count: '3人', education_requirement: '硕士研究生及以上' }
    ]
  })

  assert.match(view.highlight, /4 个岗位/)
  assert.match(view.highlight, /16人/)
  assert.deepEqual(
    view.facts.map((item) => item.value),
    ['4 个岗位', '16人', '南京市']
  )
  assert.doesNotMatch(view.highlight, /^专职辅导员$/)
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
