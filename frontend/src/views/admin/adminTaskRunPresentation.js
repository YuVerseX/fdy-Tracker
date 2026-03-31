import {
  formatAdminDateTime,
  formatAdminDurationMs,
  getTaskHeartbeatAt,
  isRunningTaskStatus,
  isTaskRunPossiblyStuck
} from '../../utils/adminDashboardViewModels.js'

const EMPTY_LABEL = '--'

const METRIC_LABELS = Object.freeze({
  processed_records: '处理记录',
  posts_seen: '发现公告',
  posts_total: '预计公告',
  posts_created: '新增公告',
  posts_updated: '更新公告',
  posts_scanned: '扫描公告',
  posts_analyzed: '完成分析',
  analysis_created: '新增分析',
  analysis_refreshed: '刷新分析',
  success_count: '成功完成',
  fallback_count: '回退处理',
  failure_count: '失败',
  failures: '失败',
  analysis_reused_count: '沿用已有结果',
  insight_created: '新增关键信息字段',
  insight_refreshed: '刷新关键信息字段',
  insight_success_count: '关键信息字段完成',
  insight_fallback_count: '关键信息字段改用基础结果',
  insight_failed_count: '关键信息字段未完成',
  insight_skipped_count: '跳过关键信息字段',
  attachments_discovered: '发现附件',
  attachments_downloaded: '下载附件',
  attachments_parsed: '解析附件',
  fields_added: '补齐字段',
  jobs_saved: '写入岗位',
  ai_posts: '智能识别帖子',
  attachment_posts: '附件岗位来源',
  dedicated_posts: '专职岗位',
  contains_posts: '含岗位公告',
  selected: '检查公告',
  candidate_posts: '待比对帖子',
  compared_pairs: '已比对候选',
  total_comparisons: '候选总对数',
  processed_groups: '已确认重复组',
  total_groups: '重复组总数',
  groups: '新增重复组',
  duplicates: '折叠记录',
  remaining_unchecked: '剩余未检查'
})

const TASK_METRIC_ORDER = Object.freeze({
  manual_scrape: ['posts_seen', 'posts_created', 'posts_updated', 'processed_records', 'posts_total'],
  scheduled_scrape: ['processed_records', 'posts_seen', 'posts_created', 'posts_updated', 'posts_total'],
  attachment_backfill: ['posts_scanned', 'posts_updated', 'attachments_discovered', 'attachments_downloaded', 'attachments_parsed', 'fields_added', 'failures'],
  duplicate_backfill: ['selected', 'candidate_posts', 'processed_groups', 'total_groups', 'groups', 'duplicates', 'remaining_unchecked', 'compared_pairs', 'total_comparisons', 'processed_records'],
  base_analysis_backfill: ['posts_scanned', 'posts_updated', 'analysis_created', 'analysis_refreshed', 'insight_created', 'insight_refreshed'],
  ai_analysis: ['posts_scanned', 'posts_analyzed', 'success_count', 'analysis_reused_count', 'fallback_count', 'failure_count', 'insight_success_count', 'insight_fallback_count', 'insight_failed_count', 'insight_skipped_count'],
  job_extraction: ['posts_scanned', 'posts_updated', 'jobs_saved', 'ai_posts', 'attachment_posts', 'dedicated_posts', 'contains_posts', 'failures'],
  ai_job_extraction: ['posts_scanned', 'posts_updated', 'jobs_saved', 'ai_posts', 'attachment_posts', 'dedicated_posts', 'contains_posts', 'failures']
})

const toNumber = (value) => {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

const toDisplayValue = (value) => {
  const numeric = toNumber(value)
  if (numeric !== null) return String(numeric)
  const text = String(value ?? '').trim()
  return text || ''
}

const getTaskParam = (run = {}, ...keys) => {
  const sources = [run?.params, run?.details?.params, run?.details?.request_params, run]
  for (const source of sources) {
    if (!source) continue
    for (const key of keys) {
      if (source[key] !== undefined && source[key] !== null && source[key] !== '') return source[key]
    }
  }
  return null
}

const getRunMetricSource = (run = {}) => {
  const merged = {}
  for (const source of [run?.details, run?.details?.metrics, run?.metrics, run]) {
    if (!source || typeof source !== 'object') continue
    Object.assign(merged, source)
  }
  return merged
}

const resolveProgressMode = (run = {}) => {
  const rawMode = run?.progress_mode || run?.details?.progress_mode
  return rawMode === 'determinate' ? 'determinate' : 'stage_only'
}

const getDeterminateProgressKind = (metrics = {}) => {
  const completed = toNumber(metrics.completed)
  const total = toNumber(metrics.total)
  if (completed === null || total === null || total <= 0) return 'unknown'

  const unit = String(metrics.unit || '').trim().toLowerCase()
  return unit === 'percent' ? 'estimated_percent' : 'count_based'
}

const getDefaultStageLabel = (run = {}) => {
  if (run?.status === 'success') return '已完成'
  if (run?.status === 'failed') return '处理未完成'
  if (run?.status === 'queued' || run?.status === 'pending') return '排队等待执行'
  if (isRunningTaskStatus(run?.status)) return '正在处理'
  return EMPTY_LABEL
}

const getProgressPercent = (run = {}, metrics = {}) => {
  const numeric = toNumber(run?.progress)
  if (numeric !== null) return Math.max(0, Math.min(Math.round(numeric), 100))

  const completed = toNumber(metrics.completed)
  const total = toNumber(metrics.total)
  if (completed !== null && total !== null && total > 0) {
    const unit = String(metrics.unit || '').trim().toLowerCase()
    if (unit === 'percent') return Math.max(0, Math.min(Math.round(completed), 100))
    return Math.max(0, Math.min(Math.round((completed / total) * 100), 100))
  }

  if (run?.status === 'success') return 100
  return 0
}

const getTaskElapsedMs = (run = {}, nowTs = Date.now()) => {
  const durationMs = Number(run?.duration_ms)
  if (Number.isFinite(durationMs) && durationMs >= 0) return durationMs
  const startedMs = Date.parse(run?.started_at || run?.startedAt || '')
  if (Number.isNaN(startedMs)) return null
  const finishedMs = Date.parse(run?.finished_at || run?.finishedAt || '')
  return Math.max((Number.isNaN(finishedMs) ? nowTs : finishedMs) - startedMs, 0)
}

const formatSourceParam = (run = {}, sourceOptions = []) => {
  const sourceId = getTaskParam(run, 'source_id', 'sourceId')
  if (!sourceId) return '全部数据源'
  const matchedSource = sourceOptions.find((source) => source.value === Number(sourceId))
  return matchedSource ? matchedSource.label : `数据源 ${sourceId}`
}

const buildDeterminateProgressLabel = (run = {}, metrics = {}) => {
  const completed = toNumber(metrics.completed)
  const total = toNumber(metrics.total)
  const unit = String(metrics.unit || '').trim()

  if (run?.status === 'success') return '已完成'
  if (run?.status === 'failed') return '处理未完成'
  if (completed !== null && unit === 'percent') return `已推进 ${completed}%`
  if (completed !== null && total !== null && total > 0 && unit && unit !== 'percent') {
    return `已处理 ${completed} / ${total} ${unit}`
  }
  if (completed !== null && total !== null && total > 0) {
    return `已处理 ${completed} / ${total}`
  }
  if (isRunningTaskStatus(run?.status)) return '按进度推进'
  return EMPTY_LABEL
}

const buildEstimatedProgressLabel = (run = {}, { isStuck = false } = {}) => {
  if (run?.status === 'success') return '已完成'
  if (run?.status === 'failed') return '处理未完成'
  if (isStuck) return '等待阶段更新'
  if (run?.status === 'queued' || run?.status === 'pending') return '等待开始处理'
  return '当前百分比仅用于提示阶段位置'
}

const buildStageOnlyProgressLabel = (run = {}, metrics = {}, { isStuck = false } = {}) => {
  if (run?.status === 'success') return '已完成'
  if (run?.status === 'failed') return '处理未完成'
  if (isStuck) return '等待阶段更新'

  const taskType = run?.task_type || run?.taskType
  const seen = toNumber(metrics.posts_seen)
  const scanned = toNumber(metrics.posts_scanned)
  const total = toNumber(metrics.posts_total)
  const processedGroups = toNumber(metrics.processed_groups)
  const totalGroups = toNumber(metrics.total_groups)
  const comparedPairs = toNumber(metrics.compared_pairs)
  const totalComparisons = toNumber(metrics.total_comparisons)
  const completedPercent = toNumber(metrics.completed)
  const unit = String(metrics.unit || '').trim().toLowerCase()

  if (taskType === 'duplicate_backfill') {
    if (processedGroups !== null && totalGroups !== null && totalGroups > 0) {
      return `已写入 ${processedGroups} / ${totalGroups} 个重复组`
    }
    if (comparedPairs !== null && totalComparisons !== null && totalComparisons > 0) {
      return `已比对 ${comparedPairs} / ${totalComparisons} 组候选`
    }
    if (completedPercent !== null && unit === 'percent') {
      return `已推进 ${completedPercent}%`
    }
  }

  if (seen !== null && total !== null && total > 0) {
    return `已处理 ${seen} / ${total} 条公告`
  }

  if (scanned !== null && total !== null && total > 0) {
    if (['job_extraction', 'ai_job_extraction', 'attachment_backfill'].includes(taskType)) {
      return `已检查 ${scanned} / ${total} 条公告`
    }
    return `已处理 ${scanned} / ${total} 条公告`
  }

  return '按阶段推进'
}

export function buildTaskProgressView(run = {}, { nowTs = Date.now(), heartbeatStaleMs = 10 * 60 * 1000 } = {}) {
  const mode = resolveProgressMode(run)
  const metrics = getRunMetricSource(run)
  const percent = getProgressPercent(run, metrics)
  const isStuck = isTaskRunPossiblyStuck(run, nowTs, heartbeatStaleMs)
  const stageLabel = String(run?.stage_label || run?.phase || '').trim() || getDefaultStageLabel(run)
  const determinateKind = getDeterminateProgressKind(metrics)

  if (mode === 'determinate' && determinateKind === 'count_based') {
    return {
      mode,
      isStuck,
      modeLabel: '按完成量更新',
      showProgressBar: true,
      stageLabel,
      progressLabel: buildDeterminateProgressLabel(run, metrics),
      progressPercentLabel: `${percent}%`,
      percent,
      visualPercent: percent
    }
  }

  if (mode === 'determinate') {
    return {
      mode,
      isStuck,
      modeLabel: '阶段估算',
      showProgressBar: false,
      stageLabel,
      progressLabel: buildEstimatedProgressLabel(run, { isStuck }),
      progressPercentLabel: run?.status === 'success' || run?.status === 'failed' ? '' : `约 ${percent}%`,
      percent,
      visualPercent: 0
    }
  }

  return {
    mode,
    isStuck,
    modeLabel: '按阶段更新',
    showProgressBar: false,
    stageLabel,
    progressLabel: buildStageOnlyProgressLabel(run, metrics, { isStuck }),
    progressPercentLabel: '',
    percent: 0,
    visualPercent: 0
  }
}

export function buildTaskMetricItems(run = {}) {
  const taskType = run?.task_type || run?.taskType
  const metrics = getRunMetricSource(run)
  const orderedKeys = TASK_METRIC_ORDER[taskType] || []

  const items = orderedKeys
    .map((key) => {
      if (!(key in metrics)) return null
      const value = toDisplayValue(metrics[key])
      if (!value) return null
      return {
        key,
        label: METRIC_LABELS[key] || key,
        value
      }
    })
    .filter(Boolean)

  if (items.length > 0) return items

  const completed = toNumber(metrics.completed)
  const total = toNumber(metrics.total)
  if (completed !== null && total !== null && total > 0) {
    const unit = String(metrics.unit || '').trim()
    if (unit === 'percent') return []
    return [{
      key: 'completed',
      label: '处理进度',
      value: unit && unit !== 'percent'
        ? `${completed} / ${total} ${unit}`
        : `${completed} / ${total}`
    }]
  }

  return []
}

export function buildTaskDetailSections(run = {}, { sourceOptions = [], nowTs = Date.now() } = {}) {
  const factItems = [
    { label: '开始时间', value: formatAdminDateTime(run?.started_at) },
    { label: run?.finished_at ? '完成时间' : '最近更新', value: formatAdminDateTime(run?.finished_at || getTaskHeartbeatAt(run)) },
    { label: '耗时', value: formatAdminDurationMs(getTaskElapsedMs(run, nowTs)) },
    { label: '数据源', value: formatSourceParam(run, sourceOptions) },
    { label: '抓取页数', value: getTaskParam(run, 'max_pages', 'maxPages') ?? EMPTY_LABEL },
    { label: '处理上限', value: getTaskParam(run, 'limit') ?? EMPTY_LABEL }
  ].filter((item) => item.value && item.value !== EMPTY_LABEL)

  const resultItems = buildTaskMetricItems(run).slice(4)
  const sections = []

  if (factItems.length > 0) {
    sections.push({
      id: 'facts',
      title: '任务信息',
      items: factItems
    })
  }

  if (resultItems.length > 0) {
    sections.push({
      id: 'results',
      title: '处理结果',
      items: resultItems
    })
  }

  return sections
}
