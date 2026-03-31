import { buildResolvedPostFields, normalizeJobItems } from './postDetailPresentation.js'

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

const buildSummary = (post = {}) => {
  const title = normalizeText(post?.title)
  const summary = normalizeText(post?.analysis?.summary || post?.summary)

  if (!summary || summary === title) {
    return ''
  }

  if (NON_USER_FACING_PATTERNS.some((pattern) => pattern.test(summary))) {
    return ''
  }

  return clampText(summary, 120)
}

const buildCardFacts = (fields = {}) => {
  return [
    { label: '性别', value: normalizeText(fields.性别要求) },
    { label: '学历', value: normalizeText(fields.学历要求) },
    { label: '地点', value: normalizeText(fields.工作地点) },
    { label: '人数', value: normalizeText(fields.招聘人数) }
  ].filter((item) => item.value)
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
      title: '最近抓取记录',
      description: '正在更新最近抓取记录。'
    }
  }

  if (latestSuccessTask?.finishedAt) {
    return {
      title: '最近抓取记录',
      description: `${freshnessHeadline}，完成于 ${formatDateTime(latestSuccessTask.finishedAt)}（${formatRelativeTime(latestSuccessTask.finishedAt)}）。这能帮助你判断列表最近是否更新。`
    }
  }

  if (unavailable) {
    return {
      title: '最近抓取记录',
      description: '最近抓取记录暂时不可用，不影响继续筛选和浏览。'
    }
  }

  return {
    title: '最近抓取记录',
    description: '还没有可展示的抓取成功任务记录。'
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
  const primaryJob = jobItems[0] || {}
  const jobOverview = [
    normalizeText(primaryJob.job_name || fields.岗位名称),
    normalizeText(fields.招聘人数) ? `人数 ${normalizeText(fields.招聘人数)}` : '',
    normalizeText(fields.学历要求) ? `学历 ${normalizeText(fields.学历要求)}` : '',
    normalizeText(fields.工作地点) ? `地点 ${normalizeText(fields.工作地点)}` : ''
  ].filter(Boolean).join(' · ')
  const title = normalizeText(post?.title) || '未命名公告'

  return {
    id: post?.id || post?._id || title,
    title,
    summary: buildSummary(post),
    jobOverview: jobOverview && jobOverview !== title ? jobOverview : '',
    factItems: buildCardFacts(fields),
    badges: buildCardBadges(post, jobItems),
    metaItems: buildMetaItems(post, formatDate)
  }
}

export function buildPostCardView(post = {}, options = {}) {
  const card = buildPostListCard(post, options)
  const jobItems = normalizeJobItems(post)
  const primaryJobName = normalizeText(jobItems[0]?.job_name)
  const preferredFacts = [
    card.factItems.find((item) => item.label === '人数'),
    card.factItems.find((item) => item.label === '学历'),
    card.factItems.find((item) => item.label === '地点'),
    card.factItems.find((item) => item.label === '性别')
  ].filter(Boolean)

  return {
    id: card.id,
    title: card.title,
    highlight: primaryJobName || card.jobOverview,
    facts: preferredFacts,
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
