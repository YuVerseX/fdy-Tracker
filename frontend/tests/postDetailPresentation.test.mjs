import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import {
  buildHeroTags,
  buildHeroSummary,
  buildInfoDisclosureItems,
  buildJobPresentation,
  buildPostFacts,
  buildResolvedPostFields,
  buildSourceNotes,
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

test('buildHeroSummary should not overstate completeness for sparse records', () => {
  const summary = buildHeroSummary({
    postData: {
      record_completeness: {
        content: 'missing',
        summary: 'missing',
        jobs: 'pending',
        attachments: 'unknown'
      }
    },
    fields: {},
    jobItems: []
  })

  assert.match(summary, /仅收录公告标题和基础信息/)
})

test('buildHeroSummary should acknowledge available content when only summary metadata is missing', () => {
  const summary = buildHeroSummary({
    postData: {
      content: '招聘公告正文',
      record_completeness: {
        content: 'available',
        summary: 'missing',
        jobs: 'missing',
        attachments: 'unknown'
      }
    },
    fields: {},
    jobItems: []
  })

  assert.match(summary, /已收录正文/)
  assert.doesNotMatch(summary, /仅收录公告标题和基础信息/)
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

test('post detail error state should keep deterministic recovery actions in AppNotice', () => {
  const source = readSource('views/PostDetail.vue')

  assert.match(source, /<AppNotice[\s\S]*v-else-if="error"[\s\S]*title="招聘详情暂时无法显示"/)
  assert.match(source, />\s*返回列表\s*</)
  assert.match(source, /v-if="errorStatus !== 404"/)
  assert.match(source, />\s*重新加载\s*</)
  assert.match(source, /router\.push\(\s*\{\s*name: 'PostList',\s*query: \{ \.\.\.route\.query \}\s*\}\s*\)/)
  assert.doesNotMatch(source, /window\.history\.length/)
})

test('post detail state should track errorStatus and clear freshness state on failure', () => {
  const source = readSource('views/post-detail/usePostDetailState.js')

  assert.match(source, /const errorStatus = ref\(0\)/)
  assert.match(source, /errorStatus\.value = 0/)
  assert.match(source, /errorStatus\.value = requestError\?\.response\?\.status \?\? 0/)
  assert.match(source, /post\.value = null/)
  assert.match(source, /latestSuccessTask\.value = null/)
  assert.match(source, /freshnessLoading\.value = false/)
  assert.match(source, /freshnessUnavailable\.value = false/)
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

test('buildHeroTags and buildSourceNotes should expose completeness and provenance truthfully', () => {
  const postData = {
    is_counselor: true,
    counselor_scope: 'contains',
    attachments: [{ id: 1 }],
    record_completeness: {
      content: 'missing',
      summary: 'available',
      jobs: 'pending',
      attachments: 'available'
    },
    record_provenance: {
      summary_source: 'rule',
      job_sources: ['attachment'],
      duplicate_resolution: {
        resolved_from_duplicate: true,
        requested_post_id: 99,
        resolved_post_id: 1,
        reason: 'source_date_title'
      }
    }
  }

  const tags = buildHeroTags(postData, [])
  const notes = buildSourceNotes(postData, [])

  assert.ok(tags.every((item) => item.label !== '规则整理'))
  assert.ok(tags.some((item) => item.label === '正文待补充'))
  assert.ok(tags.some((item) => item.label === '岗位待整理'))
  assert.ok(notes.some((item) => /去重后的主记录/.test(item)))
  assert.ok(notes.some((item) => /摘要来源：规则整理/.test(item)))
  assert.ok(notes.some((item) => /岗位来源：附件/.test(item)))
  assert.ok(notes.some((item) => /暂未收录正文/.test(item)))
})

test('buildSourceNotes should keep snapshot provenance explicit when backend provenance is absent', () => {
  const notes = buildSourceNotes(
    {
      record_completeness: {
        content: 'available',
        summary: 'missing',
        jobs: 'available',
        attachments: 'unknown'
      }
    },
    [{ job_name: '辅导员岗位快照', source: '岗位快照' }]
  )

  assert.ok(notes.some((item) => /岗位来源：岗位快照/.test(item)))
  assert.ok(notes.every((item) => !/页面整理结果展示|综合展示/.test(item)))
})

test('buildHeroTags should expose positive completeness when detail content is available', () => {
  const tags = buildHeroTags({
    record_completeness: {
      content: 'available',
      summary: 'available',
      jobs: 'available',
      attachments: 'missing'
    }
  }, [])

  assert.ok(tags.some((item) => item.label === '已收录正文'))
})

test('buildSourceNotes should not leak unknown provider or source identifiers into public copy', () => {
  const notes = buildSourceNotes({
    record_completeness: {
      content: 'available',
      summary: 'available',
      jobs: 'available',
      attachments: 'unknown'
    },
    record_provenance: {
      summary_source: 'unknown',
      job_sources: ['mystery_source']
    }
  }, [])

  assert.ok(notes.some((item) => /摘要来源：来源待确认/.test(item)))
  assert.ok(notes.some((item) => /岗位来源：其他来源/.test(item)))
  assert.ok(notes.every((item) => !/mystery_source|unknown/.test(item)))
})

test('buildSourceNotes should treat summary_source none as missing summary instead of unknown provenance', () => {
  const notes = buildSourceNotes({
    record_completeness: {
      content: 'available',
      summary: 'missing',
      jobs: 'available',
      attachments: 'unknown'
    },
    record_provenance: {
      summary_source: 'none',
      job_sources: []
    }
  }, [])

  assert.ok(notes.every((item) => !/摘要来源：/.test(item)))
  assert.ok(notes.every((item) => !/来源待确认/.test(item)))
})

test('buildHeroSummary should treat summary_source none as missing even when completeness payload drifts', () => {
  const summary = buildHeroSummary({
    postData: {
      content: '招聘公告正文',
      record_completeness: {
        content: 'available',
        jobs: 'available',
        attachments: 'unknown'
      },
      record_provenance: {
        summary_source: 'none'
      }
    },
    fields: {},
    jobItems: []
  })

  assert.match(summary, /已收录正文/)
  assert.doesNotMatch(summary, /已收录正文和结构化信息/)
})

test('buildInfoDisclosureItems should move provenance copy into disclosure area', () => {
  const items = buildInfoDisclosureItems({
    freshnessHint: '最近一次抓取成功于 2026/03/30 20:41',
    sourceNotes: ['岗位来源：附件'],
    metadata: [
      { key: 'record_completeness', label: '记录完整度', value: '正文待补充，岗位待整理' },
      { key: 'duplicate_resolution', label: '重复记录处理', value: '当前详情已自动切换到主记录' }
    ]
  })

  assert.ok(items.some((item) => /最近一次抓取成功/.test(item.value)))
  assert.ok(items.some((item) => item.label === '记录完整度'))
  assert.ok(items.some((item) => item.label === '重复记录处理'))
})

test('shouldShowPostFactsSection should keep the section visible when supplemental facts exist', () => {
  assert.equal(shouldShowPostFactsSection([], [{ label: '报名时间', value: '4 月 1 日' }]), true)
  assert.equal(shouldShowPostFactsSection([], []), false)
})
