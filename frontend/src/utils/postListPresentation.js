import { buildHeroSummary, buildPostFacts, buildResolvedPostFields, normalizeJobItems } from './postDetailPresentation.js'

const normalizeText = (value) => String(value ?? '').trim()

const COUNSELOR_SCOPE_LABELS = {
  any: '所有辅导员相关',
  dedicated: '只招辅导员',
  contains: '含辅导员岗位',
  all: '全部公告'
}

const NON_USER_FACING_PATTERNS = [
  /TODO/i,
  /FIXME/i,
  /\bmock\b/i,
  /\bstub\b/i,
  /\bdebug\b/i,
  /待接接口/,
  /provider/i,
  /base_url/i,
  /source_id/i,
  /规则分析/,
  /OpenAI/i,
  /AI 分析/
]

const clampText = (value, maxLength = 120) => {
  const normalized = normalizeText(value)
  if (normalized.length <= maxLength) {
    return normalized
  }
  return `${normalized.slice(0, Math.max(0, maxLength - 1)).trim()}…`
}

const splitFieldValues = (value) => normalizeText(value)
  .split(/[；;]\s*/)
  .map((item) => normalizeText(item))
  .filter(Boolean)

const parseHeadcountNumber = (value) => {
  const text = normalizeText(value)
  if (!text || /-|至|以上|不少于/.test(text)) return null
  const matches = text.match(/\d+/g)
  if (!matches || matches.length !== 1) return null
  const numeric = Number(matches[0])
  return Number.isFinite(numeric) ? numeric : null
}

const getCardJobCount = (post = {}, fields = {}) => {
  const explicitCount = Number(post?.jobs_count ?? post?.jobsCount)
  if (Number.isFinite(explicitCount) && explicitCount > 0) {
    return explicitCount
  }

  const segmentedJobs = splitFieldValues(fields.岗位名称)
  return segmentedJobs.length > 1 ? segmentedJobs.length : 0
}

const buildAggregateHeadcountFromFields = (fields = {}, jobCount = 0) => {
  const rawValue = normalizeText(fields.招聘人数)
  if (jobCount <= 1) return rawValue

  const segments = splitFieldValues(rawValue)
  if (segments.length <= 1) return rawValue

  const parsed = segments.map((item) => parseHeadcountNumber(item))
  if (parsed.length === segments.length && parsed.every((value) => value !== null)) {
    return `${parsed.reduce((sum, value) => sum + value, 0)}人`
  }

  return rawValue
}

const normalizeCounselorScope = (scope, isCounselor) => {
  const normalizedScope = normalizeText(scope)
  if (normalizedScope && normalizedScope !== 'none') {
    return normalizedScope
  }
  return isCounselor ? 'related' : ''
}

const formatListDate = (value) => {
  if (!value) return ''
  return new Date(value).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  })
}

const buildSummary = (post = {}, fields = {}, jobItems = []) => {
  const title = normalizeText(post?.title)
  const jobCount = getCardJobCount(post, fields)
  const aggregateHeadcount = buildAggregateHeadcountFromFields(fields, jobCount)
  const location = normalizeText(fields.工作地点)
  const derivedSummary = buildHeroSummary({
    postData: post,
    fields,
    jobItems
  })
  const summary = normalizeText(post?.analysis?.summary || post?.summary)

  if (jobCount > 1) {
    return clampText(
      [
        `本次公告共整理出 ${jobCount} 个岗位`,
        aggregateHeadcount ? `预计招聘 ${aggregateHeadcount}` : '',
        location ? `工作地点在 ${location}` : ''
      ].filter(Boolean).join('，') + '。',
      110
    )
  }

  if (jobItems.length > 0 || normalizeText(fields.招聘人数) || normalizeText(fields.工作地点)) {
    return clampText(derivedSummary, 110)
  }

  if (!summary || summary === title) {
    return ''
  }

  if (NON_USER_FACING_PATTERNS.some((pattern) => pattern.test(summary))) {
    return ''
  }

  return clampText(summary, 120)
}

const buildCardFacts = (post = {}, fields = {}, jobItems = []) => {
  const jobCount = getCardJobCount(post, fields)
  const aggregateHeadcount = buildAggregateHeadcountFromFields(fields, jobCount)
  const location = normalizeText(fields.工作地点)

  if (jobCount > 1) {
    return [
      { label: '岗位', value: `${jobCount} 个岗位` },
      aggregateHeadcount ? { label: '人数', value: aggregateHeadcount } : null,
      location ? { label: '地点', value: location } : null
    ].filter(Boolean)
  }

  const labelMap = {
    岗位数量: '岗位',
    招聘人数: '人数',
    学历要求: '学历',
    工作地点: '地点'
  }
  const preferredLabels = jobItems.length > 1
    ? ['岗位数量', '招聘人数', '学历要求']
    : ['招聘人数', '学历要求', '工作地点']

  return buildPostFacts({ postData: post, fields, jobItems })
    .filter((item) => preferredLabels.includes(item.label))
    .map((item) => ({
      label: labelMap[item.label] || item.label,
      value: item.value
    }))
    .slice(0, 3)
}

const buildCardHighlight = (post = {}, fields = {}, jobItems = []) => {
  const jobCount = getCardJobCount(post, fields)
  const headcount = buildAggregateHeadcountFromFields(fields, jobCount)
  const location = normalizeText(fields.工作地点)
  const primaryJobName = normalizeText(jobItems[0]?.job_name)

  if (jobCount > 1) {
    return [`${jobCount} 个岗位`, headcount ? `招聘 ${headcount}` : '', location].filter(Boolean).join(' · ')
  }

  return primaryJobName || normalizeText(fields.岗位名称)
}

const buildCardBadges = (post = {}, jobItems = []) => {
  const badges = []
  const counselorScope = normalizeCounselorScope(
    post?.counselor_scope || post?.analysis?.counselor_scope,
    Boolean(post?.is_counselor)
  )
  const counselorJobsCount =
    post?.counselor_jobs_count ??
    post?.analysis?.counselor_jobs_count ??
    jobItems.filter((job) => job.is_counselor_job).length

  if (counselorScope === 'dedicated') {
    badges.push({ label: '只招辅导员', tone: 'success' })
  } else if (counselorScope === 'contains') {
    badges.push({ label: '含辅导员岗位', tone: 'info' })
  } else if (counselorScope === 'general') {
    badges.push({ label: '综合招聘', tone: 'neutral' })
  } else if (counselorScope === 'related') {
    badges.push({ label: '辅导员相关', tone: 'success' })
  }

  if (Number(counselorJobsCount) > 0 && counselorScope !== 'dedicated') {
    badges.push({ label: `辅导员岗位 ${counselorJobsCount} 个`, tone: 'info' })
  }

  if (post?.has_content) {
    badges.push({ label: '已收录正文', tone: 'info' })
  }

  const eventType = normalizeText(post?.analysis?.event_type || post?.event_type)
  if (eventType) {
    badges.push({ label: eventType, tone: 'neutral' })
  }

  return badges
}

const buildMetaItems = (post = {}, formatDate = formatListDate) => {
  const items = []
  const sourceName = normalizeText(post?.source?.name)

  if (normalizeText(post?.publish_date)) {
    items.push({ label: '发布日期', value: formatDate(post.publish_date) })
  }

  if (sourceName) {
    items.push({ label: '来源', value: sourceName })
  }

  if (post?.has_content) {
    items.push({ label: '正文', value: '已收录', tone: 'success' })
  }

  return items
}

export const POST_LIST_PAGE_HEADER = {
  eyebrow: '招聘公告',
  title: '辅导员招聘信息',
  description: '按关键词和条件筛选，优先查看与辅导员岗位相关的公告。'
}

export const POST_LIST_SCOPE_OPTIONS = Object.entries(COUNSELOR_SCOPE_LABELS).map(([value, label]) => ({
  value,
  label
}))

export const COUNSELOR_SCOPE_OPTIONS = POST_LIST_SCOPE_OPTIONS

export function getPostListScopeLabel(scope) {
  return COUNSELOR_SCOPE_LABELS[scope] || COUNSELOR_SCOPE_LABELS.any
}

export function getFilterCounselorScopeLabel(scope) {
  return getPostListScopeLabel(scope)
}

export function buildPostListFilterSummary({
  hasActiveFilters = false,
  searchQuery = '',
  currentScopeLabel = getPostListScopeLabel('any')
} = {}) {
  if (normalizeText(searchQuery) || hasActiveFilters) {
    return {
      title: '筛选条件',
      description: '已根据当前关键词和条件收口结果，可以继续细筛或直接查看详情。',
      aside: `当前范围：${currentScopeLabel}`
    }
  }

  return {
    title: '筛选条件',
    description: '先用关键词缩小范围，再按学历、地点和公告类型细筛。',
    aside: `当前范围：${currentScopeLabel}`
  }
}

export function buildPostListFreshnessNotice({
  loading = false,
  latestSuccessTask = null,
  unavailable = false,
  freshnessHeadline = '',
  formatDateTime = (value) => normalizeText(value),
  formatRelativeTime = (value) => normalizeText(value)
} = {}) {
  if (loading) {
    return {
      tone: 'info',
      title: '正在读取最近抓取记录',
      description: '你可以先继续筛选和浏览当前结果。'
    }
  }

  if (latestSuccessTask?.finishedAt) {
    return {
      tone: 'info',
      title: '最近抓取记录',
      description: `${freshnessHeadline}于 ${formatDateTime(latestSuccessTask.finishedAt)}（${formatRelativeTime(latestSuccessTask.finishedAt)}）。`
    }
  }

  if (unavailable) {
    return {
      tone: 'warning',
      title: '最近抓取记录暂时不可用',
      description: '这不会影响继续浏览当前列表。'
    }
  }

  return {
    tone: 'warning',
    title: '还没有可展示的抓取成功任务记录',
    description: '稍后再来看看，或等待下一次抓取完成。'
  }
}

export function buildPostListMetricCards({
  totalMatchedPosts = 0,
  scopeTotals = {},
  currentScopeLabel = getPostListScopeLabel('any')
} = {}) {
  return [
    {
      key: 'matched',
      label: '当前结果',
      value: String(totalMatchedPosts ?? 0),
      tone: 'info',
      description: `当前范围：${currentScopeLabel}`
    },
    {
      key: 'dedicated',
      label: '只招辅导员',
      value: String(scopeTotals?.dedicated ?? 0),
      tone: 'success',
      description: '快速查看专职辅导员公告'
    },
    {
      key: 'contains',
      label: '含辅导员岗位',
      value: String(scopeTotals?.contains ?? 0),
      tone: 'neutral',
      description: '综合招聘里也包含辅导员岗位'
    },
    {
      key: 'all',
      label: '全部公告',
      value: String(scopeTotals?.all ?? 0),
      tone: 'neutral',
      description: '便于和当前筛选结果快速对比'
    }
  ]
}

export function buildPostListCard(post = {}, { formatDate = formatListDate } = {}) {
  const jobItems = normalizeJobItems(post)
  const fields = buildResolvedPostFields(post, jobItems)
  const jobOverview = buildCardHighlight(post, fields, jobItems)
  const title = normalizeText(post?.title) || '未命名公告'

  return {
    id: post?.id || post?._id || title,
    title,
    summary: buildSummary(post, fields, jobItems),
    jobOverview: jobOverview && jobOverview !== title ? jobOverview : '',
    factItems: buildCardFacts(post, fields, jobItems),
    badges: buildCardBadges(post, jobItems),
    metaItems: buildMetaItems(post, formatDate)
  }
}

export function buildPostCardView(post = {}, options = {}) {
  const card = buildPostListCard(post, options)

  return {
    id: card.id,
    title: card.title,
    highlight: card.jobOverview,
    facts: card.factItems,
    badges: card.badges,
    meta: card.metaItems.filter((item) => item.label !== '正文')
  }
}

export function buildActiveFilterChips({
  searchQuery = '',
  filters = {},
  defaultCounselorScope = 'any'
} = {}) {
  const chips = []
  const normalizedSearch = normalizeText(searchQuery)

  if (normalizedSearch) {
    chips.push({ key: 'search', label: '关键词', value: normalizedSearch })
  }
  if (normalizeText(filters.gender)) {
    chips.push({ key: 'gender', label: '性别', value: normalizeText(filters.gender) })
  }
  if (normalizeText(filters.education)) {
    chips.push({ key: 'education', label: '学历', value: normalizeText(filters.education) })
  }
  if (normalizeText(filters.location)) {
    chips.push({ key: 'location', label: '地点', value: normalizeText(filters.location) })
  }
  if (normalizeText(filters.eventType)) {
    chips.push({ key: 'eventType', label: '公告类型', value: normalizeText(filters.eventType) })
  }
  if (filters.counselorScope && filters.counselorScope !== defaultCounselorScope) {
    chips.push({
      key: 'counselorScope',
      label: '招聘范围',
      value: getPostListScopeLabel(filters.counselorScope)
    })
  }
  if (filters.hasContent) {
    chips.push({ key: 'hasContent', label: '正文', value: '已收录正文' })
  }

  return chips
}

export function buildPostListEmptyState({
  hasFilters = false,
  hasActiveFilters = false,
  searchQuery = ''
} = {}) {
  if (hasFilters || normalizeText(searchQuery) || hasActiveFilters) {
    return {
      title: '当前条件下还没有匹配结果',
      description: '可以放宽筛选条件，或者换一个关键词再试试。'
    }
  }

  return {
    title: '暂时还没有可浏览的招聘公告',
    description: '稍后再来看看，或等待下一次抓取完成。'
  }
}
