import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import {
  buildHeroSummary,
  buildInfoDisclosureItems,
  buildJobPresentation,
  buildPostFacts,
  buildResolvedPostFields,
  buildSupplementalFields,
  shouldShowAdminFacingMetadata
} from '../src/utils/postDetailPresentation.js'
import { shouldShowPostFactsSection } from '../src/utils/postFactsSection.js'

const readSource = (relativePath) => readFileSync(new URL(`../src/${relativePath}`, import.meta.url), 'utf8')

test('buildResolvedPostFields should preserve announcement-level fields for multi-job posts', () => {
  const fields = buildResolvedPostFields({
    fields: [
      { field_name: '岗位名称', field_value: '专职辅导员；专职辅导员（男）；专职辅导员（女）；心理健康教育专职辅导员' },
      { field_name: '招聘人数', field_value: '8人；4人；3人；1人' },
      { field_name: '学历要求', field_value: '本科' }
    ]
  }, [
    { job_name: '专职辅导员', headcount: '8人', education: '博士研究生' },
    { job_name: '专职辅导员（男）', headcount: '4人', education: '硕士研究生及以上' }
  ])

  assert.equal(fields.岗位名称, '专职辅导员；专职辅导员（男）；专职辅导员（女）；心理健康教育专职辅导员')
  assert.equal(fields.招聘人数, '8人；4人；3人；1人')
  assert.equal(fields.学历要求, '本科')
})

test('buildResolvedPostFields should accept object-shaped field snapshots from list responses', () => {
  const fields = buildResolvedPostFields({
    fields: {
      岗位名称: '专职辅导员；专职辅导员（男）',
      招聘人数: '8人；4人',
      工作地点: '南京市'
    }
  }, [
    { job_name: '专职辅导员', headcount: '8人', education: '博士研究生', location: '南京市' }
  ])

  assert.equal(fields.岗位名称, '专职辅导员；专职辅导员（男）')
  assert.equal(fields.招聘人数, '8人；4人')
  assert.equal(fields.工作地点, '南京市')
})

test('buildPostFacts should keep announcement-level facts ahead of individual job fields for multi-job posts', () => {
  const facts = buildPostFacts({
    postData: { is_counselor: true, counselor_scope: 'dedicated' },
    fields: {
      岗位名称: '专职辅导员；专职辅导员（男）；专职辅导员（女）；心理健康教育专职辅导员',
      招聘人数: '8人；4人；3人；1人',
      学历要求: '本科',
      专业要求: '不限；心理学相关',
      工作地点: '江苏省苏州市'
    },
    jobItems: [
      { job_name: '专职辅导员', headcount: '8人', education: '博士研究生', major: '不限', location: '南京市', is_counselor_job: true },
      { job_name: '心理健康教育专职辅导员', headcount: '1人', education: '硕士研究生及以上', major: '心理学相关', location: '', is_counselor_job: true },
      { job_name: '专职辅导员（男）', headcount: '4人', education: '硕士研究生及以上', major: '不限', location: '', is_counselor_job: true },
      { job_name: '专职辅导员（女）', headcount: '3人', education: '硕士研究生及以上', major: '不限', location: '', is_counselor_job: true }
    ]
  })

  assert.deepEqual(
    facts.map((item) => item.label).slice(0, 5),
    ['岗位数量', '招聘人数', '学历要求', '专业要求', '工作地点']
  )
  assert.equal(facts[0].value, '4 个岗位')
  assert.equal(facts[1].value, '16人')
  assert.equal(facts[2].value, '博士研究生 / 硕士研究生及以上')
  assert.equal(facts[3].value, '部分岗位不限，部分岗位要求相关专业')
  assert.equal(facts[4].value, '南京市')
  assert.ok(facts.every((item) => item.label !== '岗位名称'))
})

test('buildHeroSummary should summarize multi-job counselor posts without reusing the first job as the only conclusion', () => {
  const summary = buildHeroSummary({
    postData: { is_counselor: true, counselor_scope: 'dedicated' },
    fields: {
      工作地点: '南京市'
    },
    jobItems: [
      { job_name: '专职辅导员', headcount: '8人', education: '博士研究生', location: '南京市', is_counselor_job: true },
      { job_name: '心理健康教育专职辅导员', headcount: '1人', education: '硕士研究生及以上', location: '', is_counselor_job: true },
      { job_name: '专职辅导员（男）', headcount: '4人', education: '硕士研究生及以上', location: '', is_counselor_job: true },
      { job_name: '专职辅导员（女）', headcount: '3人', education: '硕士研究生及以上', location: '', is_counselor_job: true }
    ]
  })

  assert.match(summary, /4 个岗位/)
  assert.match(summary, /预计招聘 16人/)
  assert.match(summary, /辅导员岗位/)
  assert.match(summary, /南京市/)
})

test('post detail page should promote headline summary and move structured facts behind the hero', () => {
  const source = readSource('views/PostDetail.vue')
  const heroSource = readSource('views/post-detail/PostHeroSection.vue')

  assert.match(source, /:summary="heroSummary"/)
  assert.match(source, /:headline-facts="heroFacts"/)
  assert.match(source, /AppSectionNav/)
  assert.match(source, /sectionLinks/)
  assert.match(source, /id="post-jobs"/)
  assert.match(source, /id="post-facts"/)
  assert.match(source, /id="post-content"/)
  assert.match(source, /id="post-disclosure"/)
  assert.match(source, /href: '#post-content'/)
  assert.match(source, /<PostJobsSection id="post-jobs" class="scroll-mt-6" :job-view="jobView" \/>/)
  assert.match(source, /<PostFactsSection id="post-facts" class="scroll-mt-6" :facts="\[\]" :supplemental-facts="supplementalFacts" \/>/)
  assert.match(source, /buildSupplementalFields\(post\.value \|\| {}, heroFacts\.value, jobItems\.value\)/)
  assert.match(heroSource, /lg:grid-cols-\[minmax\(0,1\.2fr\)_minmax\(0,0\.95fr\)\]/)
})

test('buildJobPresentation should use table mode for multiple jobs', () => {
  const view = buildJobPresentation([
    { job_name: '专职辅导员', headcount: '2人' },
    { job_name: '实验员', headcount: '1人' }
  ])

  assert.equal(view.mode, 'table')
  assert.equal(view.rows.length, 2)
})

test('buildSupplementalFields should drop redundant job-name aggregation when a job section already exists', () => {
  const facts = buildSupplementalFields({
    fields: [
      { field_name: '岗位名称', field_value: '专职辅导员；实验员' },
      { field_name: '报名时间', field_value: '2026 年 4 月 1 日' }
    ]
  }, [], [
    { job_name: '专职辅导员' },
    { job_name: '实验员' }
  ])

  assert.deepEqual(facts, [
    { label: '报名时间', value: '2026 年 4 月 1 日' }
  ])
})

test('post jobs section should switch multi-job details to cards on mobile and table on desktop', () => {
  const source = readSource('views/post-detail/PostJobsSection.vue')

  assert.match(source, /md:hidden/)
  assert.match(source, /hidden md:block/)
  assert.match(source, /AppMetricPill/)
  assert.match(source, /<caption class="sr-only">/)
})

test('shared fact list and attachment cards should support long content without losing focus cues', () => {
  const factListSource = readSource('components/ui/AppFactList.vue')
  const attachmentSource = readSource('views/post-detail/PostAttachmentsSection.vue')
  const sectionNavSource = readSource('components/ui/AppSectionNav.vue')

  assert.match(factListSource, /app-break/)
  assert.match(attachmentSource, /focus-visible:ring-2/)
  assert.match(attachmentSource, /app-break/)
  assert.match(sectionNavSource, /focus-visible:ring-2/)
  assert.match(sectionNavSource, /aria-label/)
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
