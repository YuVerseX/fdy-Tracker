const FACT_ORDER = ['岗位数量', '岗位名称', '招聘人数', '学历要求', '专业要求', '工作地点', '政治面貌', '年龄要求', '报名时间']
const PRIMARY_FIELD_NAMES = ['性别要求', '学历要求', '专业要求', '工作地点', '招聘人数', '政治面貌', '年龄要求']
const HIDDEN_FIRST_SCREEN_KEYS = new Set(['confidence_score', 'analysis_provider', 'field_source', 'job_source'])
const JOB_TABLE_COLUMNS = ['岗位名称', '人数', '学历', '专业', '地点']

const normalizeText = (value) => String(value ?? '').trim()

const pickFirstText = (source = {}, keys = []) => {
  for (const key of keys) {
    const value = normalizeText(source?.[key])
    if (value) return value
  }
  return ''
}

const formatJobSource = (value) => {
  const labels = {
    hybrid: '正文和附件',
    attachment: '附件',
    attachment_pdf: '附件',
    field: '公告正文',
    ai: 'AI 整理',
    snapshot: '岗位快照'
  }
  return labels[value] || normalizeText(value)
}

const inferGenderFromJobs = (jobItems = []) => {
  const hasMale = jobItems.some((job) => (job.job_name || '').includes('（男）') || (job.job_name || '').includes('(男)'))
  const hasFemale = jobItems.some((job) => (job.job_name || '').includes('（女）') || (job.job_name || '').includes('(女)'))

  if (hasMale && hasFemale) return ''
  if (hasMale) return '男'
  if (hasFemale) return '女'
  return ''
}

const normalizeCounselorScope = (scope, isCounselor) => {
  const normalizedScope = normalizeText(scope)
  if (normalizedScope && normalizedScope !== 'none') {
    return normalizedScope
  }
  return isCounselor ? 'related' : ''
}

const collectUniqueText = (values = []) => Array.from(new Set(values.map((value) => normalizeText(value)).filter(Boolean)))

const parseHeadcountNumber = (value) => {
  const text = normalizeText(value)
  if (!text || /-|至|以上|不少于/.test(text)) return null
  const matches = text.match(/\d+/g)
  if (!matches || matches.length !== 1) return null
  const numeric = Number(matches[0])
  return Number.isFinite(numeric) ? numeric : null
}

const buildHeadcountSummary = (fields = {}, jobItems = []) => {
  const parsedCounts = jobItems.map((job) => parseHeadcountNumber(job?.headcount))

  if (jobItems.length > 1 && parsedCounts.length === jobItems.length && parsedCounts.every((value) => value !== null)) {
    return `${parsedCounts.reduce((sum, value) => sum + value, 0)}人`
  }

  return normalizeText(fields['招聘人数'])
}

const buildEducationSummary = (fields = {}, jobItems = []) => {
  const values = collectUniqueText(jobItems.map((job) => job?.education))
  if (values.length === 1) return values[0]
  if (values.length > 1) return values.slice(0, 2).join(' / ')
  return normalizeText(fields['学历要求'])
}

const buildMajorSummary = (fields = {}, jobItems = []) => {
  const values = collectUniqueText(jobItems.map((job) => job?.major))
  if (values.length === 1) return values[0]
  if (values.length > 1 && values.includes('不限')) {
    return '部分岗位不限，部分岗位要求相关专业'
  }
  if (values.length > 1) return values.slice(0, 2).join(' / ')
  return normalizeText(fields['专业要求'])
}

const buildLocationSummary = (fields = {}, jobItems = []) => {
  const values = collectUniqueText(jobItems.map((job) => job?.location))
  if (values.length === 1) return values[0]
  if (values.length > 1) return values.join(' / ')
  return normalizeText(fields['工作地点'])
}

const buildRoleSummary = (postData = {}, jobItems = []) => {
  if (jobItems.length === 0) return ''

  const counselorJobsCount = jobItems.filter((job) => job?.is_counselor_job).length
  if (jobItems.length === 1) {
    const jobName = normalizeText(jobItems[0]?.job_name)
    return jobName ? `岗位为${jobName}` : ''
  }

  const counselorScope = normalizeCounselorScope(
    postData?.counselor_scope || postData?.analysis?.counselor_scope,
    Boolean(postData?.is_counselor)
  )

  if (counselorScope === 'dedicated' || counselorJobsCount === jobItems.length) {
    return '均为辅导员岗位'
  }
  if (counselorJobsCount > 0) {
    return `包含 ${counselorJobsCount} 个辅导员岗位`
  }
  return ''
}

export const buildFieldMap = (fields = []) => {
  if (Array.isArray(fields)) {
    return fields.reduce((accumulator, field) => {
      const fieldName = normalizeText(field?.field_name)
      if (!fieldName || accumulator[fieldName]) {
        return accumulator
      }
      accumulator[fieldName] = normalizeText(field?.field_value)
      return accumulator
    }, {})
  }

  if (fields && typeof fields === 'object') {
    return Object.entries(fields).reduce((accumulator, [fieldName, fieldValue]) => {
      const normalizedName = normalizeText(fieldName)
      if (!normalizedName || accumulator[normalizedName]) {
        return accumulator
      }
      accumulator[normalizedName] = normalizeText(fieldValue)
      return accumulator
    }, {})
  }

  return {}
}

export function normalizeJobItems(postData = {}) {
  const rawItems =
    postData?.job_items ||
    postData?.jobs ||
    postData?.analysis?.job_items ||
    postData?.analysis?.jobs ||
    []

  if (Array.isArray(rawItems) && rawItems.length > 0) {
    const normalizedItems = rawItems.map((item, index) => ({
      id: item?.id || item?.job_id || `job-${index}`,
      job_name: pickFirstText(item, ['job_name', 'position_name', 'title']),
      headcount: pickFirstText(item, ['headcount', 'recruitment_count', 'count']),
      education: pickFirstText(item, ['education', 'education_requirement']),
      major: pickFirstText(item, ['major', 'major_requirement']),
      location: pickFirstText(item, ['location', 'city', 'work_location']),
      source: formatJobSource(item?.source || item?.data_source || item?.source_type),
      is_counselor_job: Boolean(
        item?.is_counselor_job ||
        item?.is_counselor ||
        pickFirstText(item, ['job_name', 'position_name', 'title']).includes('辅导员')
      )
    }))

    const hasSpecificStructuredJobs = normalizedItems.some((item) => item.source && item.source !== formatJobSource('field'))
    if (!hasSpecificStructuredJobs) {
      return normalizedItems
    }

    return normalizedItems.filter((item) => {
      const isNoisyFieldAggregate =
        item.source === formatJobSource('field') &&
        ((item.job_name || '').includes('；') || (item.headcount || '').includes('；'))

      return !isNoisyFieldAggregate
    })
  }

  const snapshot = postData?.job_snapshot || postData?.analysis?.job_snapshot
  if (typeof snapshot === 'string' && normalizeText(snapshot)) {
    return [{
      id: 'snapshot',
      job_name: normalizeText(snapshot),
      headcount: '',
      education: '',
      major: '',
      location: '',
      source: formatJobSource('snapshot'),
      is_counselor_job: normalizeText(snapshot).includes('辅导员')
    }]
  }

  if (snapshot && typeof snapshot === 'object') {
    return [{
      id: snapshot.id || 'snapshot',
      job_name: pickFirstText(snapshot, ['job_name', 'position_name', 'title']),
      headcount: pickFirstText(snapshot, ['headcount', 'recruitment_count', 'count']),
      education: pickFirstText(snapshot, ['education', 'education_requirement']),
      major: pickFirstText(snapshot, ['major', 'major_requirement']),
      location: pickFirstText(snapshot, ['location', 'city', 'work_location']),
      source: formatJobSource(snapshot.source || snapshot.data_source || snapshot.source_type || 'snapshot'),
      is_counselor_job: Boolean(
        snapshot.is_counselor_job ||
        snapshot.is_counselor ||
        pickFirstText(snapshot, ['job_name', 'position_name', 'title']).includes('辅导员')
      )
    }]
  }

  return []
}

export function buildResolvedPostFields(postData = {}, jobItems = []) {
  const fieldMap = buildFieldMap(postData?.fields || [])
  const primaryJob = jobItems.length === 1 ? (jobItems[0] || {}) : {}
  const inferredGender = inferGenderFromJobs(jobItems)
  const fallbackLocation = collectUniqueText(jobItems.map((job) => job?.location))[0] || ''

  return {
    ...fieldMap,
    岗位名称: fieldMap.岗位名称 || primaryJob.job_name || '',
    性别要求: inferredGender || fieldMap.性别要求 || '',
    学历要求: fieldMap.学历要求 || primaryJob.education || '',
    专业要求: fieldMap.专业要求 || primaryJob.major || '',
    工作地点: fieldMap.工作地点 || primaryJob.location || fallbackLocation || '',
    招聘人数: fieldMap.招聘人数 || primaryJob.headcount || ''
  }
}

export function buildPostFacts({ postData = {}, fields = {}, jobItems = [] } = {}) {
  const factMap = {
    岗位数量: jobItems.length > 1 ? `${jobItems.length} 个岗位` : '',
    岗位名称: jobItems.length === 1 ? (normalizeText(jobItems[0]?.job_name) || normalizeText(fields['岗位名称'])) : '',
    招聘人数: buildHeadcountSummary(fields, jobItems),
    学历要求: buildEducationSummary(fields, jobItems),
    专业要求: buildMajorSummary(fields, jobItems),
    工作地点: buildLocationSummary(fields, jobItems),
    政治面貌: normalizeText(fields['政治面貌']),
    年龄要求: normalizeText(fields['年龄要求']),
    报名时间: normalizeText(fields['报名时间'])
  }

  return FACT_ORDER
    .filter((label) => normalizeText(factMap[label]))
    .map((label) => ({ label, value: normalizeText(factMap[label]) }))
}

export function buildHeroSummary({ postData = {}, fields = {}, jobItems = [] } = {}) {
  const parts = []
  const jobCount = jobItems.length
  const headcount = buildHeadcountSummary(fields, jobItems)
  const roleSummary = buildRoleSummary(postData, jobItems)
  const location = buildLocationSummary(fields, jobItems)
  const education = buildEducationSummary(fields, jobItems)

  if (jobCount > 1) {
    parts.push(`本次公告共整理出 ${jobCount} 个岗位`)
  } else if (jobCount === 1) {
    const singleRole = buildRoleSummary(postData, jobItems)
    parts.push(singleRole ? `本次公告整理出 1 个岗位，${singleRole}` : '本次公告整理出 1 个岗位')
  }

  if (headcount) parts.push(`预计招聘 ${headcount}`)
  if (jobCount > 1 && roleSummary) parts.push(roleSummary)
  if (location) parts.push(`工作地点在 ${location}`)
  if (jobCount > 1 && education) parts.push(`学历要求覆盖 ${education}`)

  if (parts.length > 0) {
    return `${parts.join('，')}。`
  }

  return '当前公告已收录正文和结构化信息，可以先看首屏判断信息，再决定是否继续阅读原文。'
}

export function buildSupplementalFields(postData = {}, preferredFacts = [], jobItems = []) {
  const existingLabels = new Set(preferredFacts.map((item) => item.label))
  const hasStructuredJobs = Array.isArray(jobItems) && jobItems.some((job) => (
    normalizeText(job?.job_name) ||
    normalizeText(job?.headcount) ||
    normalizeText(job?.education) ||
    normalizeText(job?.major) ||
    normalizeText(job?.location)
  ))

  return (postData?.fields || [])
    .filter((field) => {
      const fieldName = normalizeText(field?.field_name)
      const fieldValue = normalizeText(field?.field_value)
      if (!fieldName || !fieldValue) return false
      if (existingLabels.has(fieldName)) return false
      if (PRIMARY_FIELD_NAMES.includes(fieldName)) return false
      if (hasStructuredJobs && fieldName === '岗位名称') return false
      return true
    })
    .map((field) => ({
      label: normalizeText(field.field_name),
      value: normalizeText(field.field_value)
    }))
}

export function buildJobPresentation(jobItems = []) {
  const rows = jobItems
    .map((job, index) => ({
      id: job?.id || `job-${index}`,
      job_name: normalizeText(job?.job_name) || '--',
      headcount: normalizeText(job?.headcount) || '--',
      education: normalizeText(job?.education) || '--',
      major: normalizeText(job?.major) || '--',
      location: normalizeText(job?.location) || '--'
    }))
    .filter((row) => row.job_name !== '--' || row.headcount !== '--' || row.education !== '--' || row.major !== '--' || row.location !== '--')

  if (rows.length <= 1) {
    return { mode: 'single', columns: JOB_TABLE_COLUMNS, rows }
  }

  return {
    mode: 'table',
    columns: JOB_TABLE_COLUMNS,
    rows
  }
}

export function shouldShowAdminFacingMetadata(key) {
  return !HIDDEN_FIRST_SCREEN_KEYS.has(key)
}

export function buildHeroTags(postData = {}, jobItems = []) {
  const tags = []
  const counselorScope = normalizeCounselorScope(
    postData?.counselor_scope || postData?.analysis?.counselor_scope,
    Boolean(postData?.is_counselor)
  )
  const counselorJobsCount = jobItems.filter((job) => job.is_counselor_job).length

  if (counselorScope === 'dedicated') {
    tags.push({ label: '只招辅导员', tone: 'success' })
  } else if (counselorScope === 'contains') {
    tags.push({ label: '含辅导员岗位', tone: 'info' })
  } else if (counselorScope === 'general') {
    tags.push({ label: '综合招聘', tone: 'neutral' })
  }

  if (counselorJobsCount > 0) {
    tags.push({ label: `辅导员岗位 ${counselorJobsCount} 个`, tone: 'success' })
  }

  const attachmentCount = Array.isArray(postData?.attachments) ? postData.attachments.length : 0
  if (attachmentCount > 0) {
    tags.push({ label: `附件 ${attachmentCount} 份`, tone: 'neutral' })
  }

  return tags
}

export function buildSourceNotes(postData = {}, jobItems = []) {
  const notes = []
  const attachmentCount = Array.isArray(postData?.attachments) ? postData.attachments.length : 0

  if (jobItems.length > 0 && attachmentCount > 0) {
    notes.push('岗位信息结合公告正文、附件和页面整理结果综合展示。')
  } else if (jobItems.length > 0) {
    notes.push('岗位信息根据公告正文和页面整理结果展示。')
  } else {
    notes.push('页面优先展示公告中的关键信息，原始表述请以原文为准。')
  }

  if (attachmentCount > 0) {
    notes.push(`当前共收录 ${attachmentCount} 份附件，可在附件区查看。`)
  }

  return notes
}

export function buildInfoDisclosureItems({ freshnessHint = '', sourceNotes = [], metadata = [] } = {}) {
  const items = [
    freshnessHint ? { key: 'freshness', label: '更新说明', value: normalizeText(freshnessHint) } : null,
    ...sourceNotes.map((value, index) => normalizeText(value) ? { key: `source-${index}`, label: '信息说明', value: normalizeText(value) } : null)
  ]

  metadata.forEach((item, index) => {
    if (!item) return
    const key = normalizeText(item.key)
    const label = normalizeText(item.label)
    const value = normalizeText(item.value)
    if (!key || !label || !value || !shouldShowAdminFacingMetadata(key)) return
    items.push({ key: `meta-${index}-${key}`, label, value })
  })

  return items.filter(Boolean)
}

export function buildAttachmentCards(attachments = []) {
  return (attachments || []).map((attachment, index) => {
    const fileType = normalizeText(attachment?.file_type)
    const isDownloaded = Boolean(attachment?.is_downloaded)
    const meta = [fileType ? fileType.toUpperCase() : '', isDownloaded ? '已收录' : '待获取'].filter(Boolean).join(' · ')

    return {
      id: attachment?.id || attachment?.file_url || `attachment-${index}`,
      title: normalizeText(attachment?.filename) || `附件 ${index + 1}`,
      url: normalizeText(attachment?.file_url),
      meta
    }
  }).filter((item) => item.url)
}
