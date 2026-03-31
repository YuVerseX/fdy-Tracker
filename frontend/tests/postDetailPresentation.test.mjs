import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildInfoDisclosureItems,
  buildJobPresentation,
  buildPostFacts,
  shouldShowAdminFacingMetadata
} from '../src/utils/postDetailPresentation.js'
import { shouldShowPostFactsSection } from '../src/utils/postFactsSection.js'

test('buildPostFacts should keep the public facts compact and ordered', () => {
  const facts = buildPostFacts({
    fields: {
      岗位名称: '专职辅导员',
      招聘人数: '2人',
      学历要求: '硕士研究生及以上',
      工作地点: '江苏省苏州市'
    }
  })

  assert.deepEqual(
    facts.map((item) => item.label),
    ['岗位名称', '招聘人数', '学历要求', '工作地点']
  )
})

test('buildJobPresentation should use table mode for multiple jobs', () => {
  const view = buildJobPresentation([
    { job_name: '专职辅导员', headcount: '2人' },
    { job_name: '实验员', headcount: '1人' }
  ])

  assert.equal(view.mode, 'table')
  assert.equal(view.rows.length, 2)
})

test('shouldShowAdminFacingMetadata should hide provider and confidence from first screen', () => {
  assert.equal(shouldShowAdminFacingMetadata('confidence_score'), false)
  assert.equal(shouldShowAdminFacingMetadata('analysis_provider'), false)
})

test('buildInfoDisclosureItems should move provenance copy into disclosure area', () => {
  const items = buildInfoDisclosureItems({
    freshnessHint: '最近一次抓取成功于 2026/03/30 20:41',
    sourceNotes: ['岗位信息由正文、附件和系统整理结果综合展示']
  })

  assert.ok(items.some((item) => /最近一次抓取成功/.test(item.value)))
})

test('shouldShowPostFactsSection should keep the section visible when supplemental facts exist', () => {
  assert.equal(shouldShowPostFactsSection([], [{ label: '报名时间', value: '4 月 1 日' }]), true)
  assert.equal(shouldShowPostFactsSection([], []), false)
})
