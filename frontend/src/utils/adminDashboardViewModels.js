import { getAdminRuntimeCopy } from './adminDashboardMeta.js'
import {
  getAdminTaskParam,
  normalizeAdminTaskSnapshot,
  normalizeAdminTaskStatus
} from './adminTaskSnapshots.js'

const EMPTY_LABEL = '--'
const NOT_FETCHED_LABEL = '未获取'
const DEFAULT_AI_DISABLED_REASON = '智能整理暂时不可用，基础处理仍可继续。'
const DEFAULT_HEARTBEAT_STALE_MS = 10 * 60 * 1000
const RUNNING_TASK_STATUSES = ['queued', 'running', 'cancel_requested']
const FINAL_TASK_STATUSES = new Set(['success', 'failed', 'cancelled'])

const TASK_TYPE_LABELS = {
  manual_scrape: '手动抓取最新数据',
  scheduled_scrape: '定时抓取',
  attachment_backfill: '补处理历史附件',
  duplicate_backfill: '检查重复记录',
  base_analysis_backfill: '补齐关键信息整理',
  ai_analysis: '补充智能摘要整理',
  job_extraction: '补齐岗位整理',
  ai_job_extraction: '补充智能岗位识别'
}

const countItems = (items = []) => items.filter(Boolean).length

const normalizeNumber = (value) => {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

const getMetricNumber = (metrics = {}, ...keys) => {
  for (const key of keys) {
    const numeric = normalizeNumber(metrics?.[key])
    if (numeric !== null) return numeric
  }
  return null
}

const formatCount = (value, suffix = '') => {
  const numeric = normalizeNumber(value)
  return numeric === null ? EMPTY_LABEL : `${numeric}${suffix}`
}
const normalizeBooleanParam = (value, fallback = false) => {
  if (typeof value === 'boolean') return value
  if (value === 'true' || value === '1') return true
  if (value === 'false' || value === '0') return false
  return fallback
}

const buildStat = (label, value, tone = 'slate', options = {}) => ({
  label,
  value,
  tone,
  description: options.description || '',
  meta: Array.isArray(options.meta) ? options.meta.filter(Boolean) : (options.meta ? [options.meta] : [])
})

export const formatAdminPercent = (part, total) => {
  const numerator = normalizeNumber(part)
  const denominator = normalizeNumber(total)

  if (numerator === null || denominator === null || denominator <= 0) {
    return '0%'
  }

  return `${Math.round((numerator / denominator) * 100)}%`
}

export const formatAdminDateTime = (value) => {
  if (!value) {
    return NOT_FETCHED_LABEL
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return NOT_FETCHED_LABEL
  }

  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Shanghai'
  })
}

export const formatAdminInterval = (secondsValue) => {
  const seconds = normalizeNumber(secondsValue)
  if (seconds === null || seconds <= 0) {
    return EMPTY_LABEL
  }
  if (seconds < 60) return `${seconds} 秒`
  if (seconds < 3600) return `${Math.round(seconds / 60)} 分钟`
  if (seconds % 3600 === 0) return `${seconds / 3600} 小时`
  return `${Math.floor(seconds / 3600)} 小时 ${Math.round((seconds % 3600) / 60)} 分钟`
}

export const formatAdminDurationMs = (durationMs) => {
  if (durationMs === null || durationMs === undefined || String(durationMs).trim() === '') {
    return EMPTY_LABEL
  }
  const normalized = normalizeNumber(durationMs)
  if (normalized === null || normalized < 0) return EMPTY_LABEL
  if (normalized < 1000) return `${Math.round(normalized)}ms`

  const seconds = Math.floor(normalized / 1000)
  if (seconds < 60) return `${seconds}秒`

  const minutes = Math.floor(seconds / 60)
  const restSeconds = seconds % 60
  return `${minutes}分${restSeconds}秒`
}

const parseTimeToMs = (value) => {
  if (!value) return null
  const time = new Date(value).getTime()
  return Number.isFinite(time) ? time : null
}

const getTaskRunKey = (run) => run?.id || `${run?.task_type || run?.taskType || 'task'}-${run?.started_at || run?.startedAt || run?.finished_at || run?.finishedAt || ''}`

export const getTaskTypeLabel = (taskType) => TASK_TYPE_LABELS[taskType] || taskType || EMPTY_LABEL
export const isRunningTaskStatus = (status) => RUNNING_TASK_STATUSES.includes(normalizeAdminTaskStatus(status))
export const getTaskHeartbeatAt = (run) => run?.heartbeat_at || run?.heartbeatAt || run?.started_at || run?.startedAt || ''
export const isTaskRunPossiblyStuck = (run, nowTs = Date.now(), heartbeatStaleMs = DEFAULT_HEARTBEAT_STALE_MS) => {
  const normalizedRun = normalizeAdminTaskSnapshot(run)
  if (!isRunningTaskStatus(normalizedRun?.status)) return false
  const heartbeatMs = parseTimeToMs(getTaskHeartbeatAt(normalizedRun))
  return heartbeatMs !== null && nowTs - heartbeatMs >= heartbeatStaleMs
}

const getRunMetricSource = (run = {}) => {
  const metricSources = FINAL_TASK_STATUSES.has(run?.status)
    ? [run, run?.details, run?.details?.metrics, run?.metrics, run?.details?.final_metrics, run?.final_metrics]
    : [run, run?.details, run?.details?.metrics, run?.metrics, run?.details?.live_metrics, run?.live_metrics]

  const merged = {}
  for (const source of metricSources) {
    if (!source || typeof source !== 'object') continue
    Object.assign(merged, source)
  }
  return merged
}

const findLatestTaskByMatcher = (taskRuns = [], matcher) => (
  taskRuns.find((run) => matcher(run))
)

const buildLiveProgressMeta = (summary, detailParts = []) => {
  if (!summary) return []
  const parts = [summary, ...detailParts.filter(Boolean)]
  return [`进行中：${parts.join('，')}`]
}

const buildProgressCountLabel = (prefix, completed, total, suffix = '条') => {
  if (completed === null) return ''
  if (suffix === '%') return `${prefix} ${completed}%`
  if (total !== null && total > 0) return `${prefix} ${completed}/${total} ${suffix}`
  return `${prefix} ${completed} ${suffix}`
}

const buildScrapeLiveMeta = (taskRuns = []) => {
  const run = findLatestTaskByMatcher(taskRuns, (item) => ['manual_scrape', 'scheduled_scrape'].includes(item?.task_type || item?.taskType) && isRunningTaskStatus(item?.status))
  if (!run) return []
  const metrics = getRunMetricSource(run)
  const seen = getMetricNumber(metrics, 'posts_seen', 'posts_scanned')
  const total = getMetricNumber(metrics, 'posts_total')
  const created = getMetricNumber(metrics, 'posts_created')
  const updated = getMetricNumber(metrics, 'posts_updated')
  return buildLiveProgressMeta(
    buildProgressCountLabel('本轮已处理', seen, total),
    [
      created !== null ? `新增 ${created} 条` : '',
      updated !== null ? `更新 ${updated} 条` : ''
    ]
  )
}

const buildAttachmentLiveMeta = (taskRuns = []) => {
  const run = findLatestTaskByMatcher(taskRuns, (item) => (item?.task_type || item?.taskType) === 'attachment_backfill' && isRunningTaskStatus(item?.status))
  if (!run) return []
  const metrics = getRunMetricSource(run)
  const scanned = getMetricNumber(metrics, 'posts_scanned')
  const total = getMetricNumber(metrics, 'posts_total')
  const updated = getMetricNumber(metrics, 'posts_updated')
  const downloaded = getMetricNumber(metrics, 'attachments_downloaded')
  return buildLiveProgressMeta(
    buildProgressCountLabel('本轮已检查', scanned, total),
    [
      updated !== null ? `更新 ${updated} 条` : '',
      downloaded !== null ? `下载 ${downloaded} 个附件` : ''
    ]
  )
}

const buildDuplicateLiveMeta = (taskRuns = []) => {
  const run = findLatestTaskByMatcher(taskRuns, (item) => (item?.task_type || item?.taskType) === 'duplicate_backfill' && isRunningTaskStatus(item?.status))
  if (!run) return []
  const metrics = getRunMetricSource(run)
  const processedGroups = getMetricNumber(metrics, 'processed_groups')
  const totalGroups = getMetricNumber(metrics, 'total_groups')
  const comparedPairs = getMetricNumber(metrics, 'compared_pairs')
  const totalComparisons = getMetricNumber(metrics, 'total_comparisons')
  const groups = getMetricNumber(metrics, 'groups')
  const duplicates = getMetricNumber(metrics, 'duplicates')
  const completed = getMetricNumber(metrics, 'completed')
  const total = getMetricNumber(metrics, 'total')
  const candidatePosts = getMetricNumber(metrics, 'candidate_posts')
  let summary = ''

  if (processedGroups !== null && totalGroups !== null && totalGroups > 0) {
    summary = buildProgressCountLabel('本轮已写入', processedGroups, totalGroups, '个重复组')
  } else if (comparedPairs !== null && totalComparisons !== null && totalComparisons > 0) {
    summary = buildProgressCountLabel('本轮已比对', comparedPairs, totalComparisons, '组候选')
  } else {
    summary = buildProgressCountLabel('本轮已完成', completed, total, '%')
  }

  return buildLiveProgressMeta(
    summary,
    [
      candidatePosts !== null ? `候选 ${candidatePosts} 条` : '',
      groups !== null ? `发现 ${groups} 个重复组` : '',
      duplicates !== null ? `折叠 ${duplicates} 条` : ''
    ]
  )
}

const buildJobExtractionLiveMeta = (taskRuns = [], { useAi = false } = {}) => {
  const run = findLatestTaskByMatcher(taskRuns, (item) => {
    const taskType = item?.task_type || item?.taskType
    const runUsesAi = normalizeBooleanParam(getAdminTaskParam(item, 'use_ai', 'useAi'), false)
    if (!isRunningTaskStatus(item?.status)) return false
    if (useAi) return taskType === 'ai_job_extraction' || (taskType === 'job_extraction' && runUsesAi)
    return taskType === 'job_extraction' && !runUsesAi
  })
  if (!run) return []
  const metrics = getRunMetricSource(run)
  const scanned = getMetricNumber(metrics, 'posts_scanned')
  const total = getMetricNumber(metrics, 'posts_total')
  const updated = getMetricNumber(metrics, 'posts_updated')
  const jobsSaved = getMetricNumber(metrics, 'jobs_saved')
  const aiPosts = getMetricNumber(metrics, 'ai_posts')
  return buildLiveProgressMeta(
    buildProgressCountLabel('本轮已检查', scanned, total),
    [
      updated !== null ? `更新 ${updated} 条帖子` : '',
      jobsSaved !== null ? `写入 ${jobsSaved} 个岗位` : '',
      useAi && aiPosts !== null ? `AI 参与 ${aiPosts} 条` : ''
    ]
  )
}

const buildAiAnalysisLiveMeta = (taskRuns = []) => {
  const run = findLatestTaskByMatcher(taskRuns, (item) => (item?.task_type || item?.taskType) === 'ai_analysis' && isRunningTaskStatus(item?.status))
  if (!run) return []
  const metrics = getRunMetricSource(run)
  const scanned = getMetricNumber(metrics, 'posts_scanned')
  const total = getMetricNumber(metrics, 'posts_total')
  const success = getMetricNumber(metrics, 'success_count')
  const insightSuccess = getMetricNumber(metrics, 'insight_success_count')
  return buildLiveProgressMeta(
    buildProgressCountLabel('本轮已处理', scanned, total),
    [
      success !== null ? `AI 成功 ${success} 条` : '',
      insightSuccess !== null ? `关键信息字段完成 ${insightSuccess} 条` : ''
    ]
  )
}

export function buildTaskRunsPresentation({
  taskRuns = [],
  nowTs = Date.now(),
  heartbeatStaleMs = DEFAULT_HEARTBEAT_STALE_MS,
  maxCurrentRuns = 4,
  maxRecentResultRuns = 4
} = {}) {
  const normalizedRuns = taskRuns.map((run) => normalizeAdminTaskSnapshot(run))
  const currentRunsAll = normalizedRuns.filter((run) => isRunningTaskStatus(run?.status))
  const cancelledRunsAll = normalizedRuns.filter((run) => run?.status === 'cancelled')
  const failedRunsAll = normalizedRuns.filter((run) => run?.status === 'failed')
  const successRunsAll = normalizedRuns.filter((run) => run?.status === 'success')
  const resultRunsAll = normalizedRuns.filter((run) => ['failed', 'success', 'cancelled'].includes(run?.status))
  const currentRuns = currentRunsAll
  const recentResultRuns = resultRunsAll.slice(0, maxRecentResultRuns)
  const featuredRunKeys = new Set([...currentRuns, ...recentResultRuns].map((run) => getTaskRunKey(run)))
  const historyRuns = normalizedRuns.filter((run) => !featuredRunKeys.has(getTaskRunKey(run)))
  const stuckCount = currentRunsAll.filter((run) => isTaskRunPossiblyStuck(run, nowTs, heartbeatStaleMs)).length
  const queuedCount = normalizedRuns.filter((run) => run?.status === 'queued').length
  const processingCount = normalizedRuns.filter((run) => ['running', 'cancel_requested'].includes(run?.status)).length

  return {
    summaryCards: [
      buildStat('当前任务', formatCount(currentRunsAll.length, ' 条'), 'amber', {
        description: currentRunsAll.length > 0 ? '正在排队或处理中的任务' : '当前没有进行中的任务',
        meta: [
          processingCount > 0 ? `${processingCount} 条正在处理` : '',
          queuedCount > 0 ? `${queuedCount} 条等待开始` : '',
          stuckCount > 0 ? `${stuckCount} 条进度停滞` : ''
        ]
      }),
      buildStat('未完成', formatCount(failedRunsAll.length, ' 条'), 'rose', {
        description: failedRunsAll.length > 0 ? '最近未完成的任务需要重新处理' : '最近没有未完成记录',
        meta: failedRunsAll.length > 0 ? `${failedRunsAll.length} 条未完成` : ''
      }),
      buildStat('已完成', formatCount(successRunsAll.length, ' 条'), 'emerald', {
        description: successRunsAll.length > 0 ? '可以在最近结果里查看刚完成的处理' : '当前还没有完成记录',
        meta: recentResultRuns.length > 0 ? `最近结果展示 ${recentResultRuns.length} 条` : ''
      }),
      buildStat('历史记录', formatCount(historyRuns.length, ' 条'), 'slate', {
        description: historyRuns.length > 0 ? '保留更早的结果，方便回看和核对。' : '当前没有更早的历史记录'
      })
    ],
    attentionRuns: [...failedRunsAll, ...currentRunsAll].slice(0, maxCurrentRuns),
    currentRuns,
    recentResultRuns,
    recentSuccessRuns: successRunsAll.slice(0, 3),
    historyRuns,
    counts: {
      attention: failedRunsAll.length + currentRunsAll.length,
      cancelled: cancelledRunsAll.length,
      current: currentRunsAll.length,
      failed: failedRunsAll.length,
      processing: processingCount,
      queued: queuedCount,
      results: resultRunsAll.length,
      running: currentRunsAll.length,
      success: successRunsAll.length,
      history: historyRuns.length,
      stuck: stuckCount
    }
  }
}

const findLatestTask = (taskRuns = [], taskTypes = [], status = 'success') => {
  return taskRuns.find((run) => {
    const taskType = run?.task_type || run?.taskType
    return taskTypes.includes(taskType) && run?.status === status
  })
}

const getSourceScopeLabel = (sourceOptions = []) => {
  const activeSources = sourceOptions.filter((source) => source?.isActive !== false)

  if (countItems(activeSources) === 0) {
    return '默认数据源'
  }
  if (activeSources.length === 1) {
    return activeSources[0].label || '默认数据源'
  }
  return `${activeSources.length} 个数据源`
}
const getOpenAiReadinessLabel = ({ openaiReady, analysisRuntime }) => {
  if (openaiReady) {
    return '可用'
  }

  if (analysisRuntime?.analysis_enabled === false) {
    return '未开启'
  }

  return '未就绪'
}

const resolveAiDisabledReason = ({ openaiReady, disabledReason, analysisRuntime }) => {
  if (openaiReady) {
    return ''
  }

  if (disabledReason) {
    return disabledReason
  }

  const runtimeCopy = getAdminRuntimeCopy(analysisRuntime)
  return runtimeCopy.emphasis || DEFAULT_AI_DISABLED_REASON
}

export function buildDataProcessingPanels({
  sourceOptions = [],
  taskRuns = [],
  analysisOverview = null,
  insightOverview = null,
  jobsOverview = null,
  duplicateOverview = null,
  duplicateLatestCheckedAt = '',
  analysisLatestAnalyzedAt = '',
  insightLatestAnalyzedAt = '',
  jobLatestExtractedAt = ''
} = {}) {
  const scrapeTask = findLatestTask(taskRuns, ['manual_scrape', 'scheduled_scrape'])
  const attachmentBackfillTask = findLatestTask(taskRuns, ['attachment_backfill'])
  const scrapeLiveMeta = buildScrapeLiveMeta(taskRuns)
  const attachmentLiveMeta = buildAttachmentLiveMeta(taskRuns)
  const duplicateLiveMeta = buildDuplicateLiveMeta(taskRuns)
  const jobLiveMeta = buildJobExtractionLiveMeta(taskRuns)

  return [
    {
      id: 'collect-and-backfill',
      title: '采集与补处理',
      description: '抓取新公告，并补齐历史附件。',
      note: '常规更新可以直接使用当前设置。',
      stats: [
        buildStat('最近抓取成功', formatAdminDateTime(scrapeTask?.finished_at || scrapeTask?.finishedAt), 'sky', { meta: scrapeLiveMeta }),
        buildStat('最近补处理成功', formatAdminDateTime(attachmentBackfillTask?.finished_at || attachmentBackfillTask?.finishedAt), 'amber', { meta: attachmentLiveMeta }),
        buildStat('待补处理', formatCount(analysisOverview?.base_pending_posts ?? insightOverview?.pending_insight_posts, ' 条'), 'slate'),
        buildStat('数据源范围', getSourceScopeLabel(sourceOptions), 'slate')
      ]
    },
    {
      id: 'duplicate-governance',
      title: '重复记录整理',
      description: '检查重复帖子并整理列表展示。',
      note: '运行后会保留更稳定的主要记录。',
      stats: [
        buildStat('重复组数', formatCount(duplicateOverview?.duplicate_groups), 'rose', { meta: duplicateLiveMeta }),
        buildStat('折叠帖子', formatCount(duplicateOverview?.duplicate_posts), 'amber'),
        buildStat('未检查', formatCount(duplicateOverview?.unchecked_posts), 'slate'),
        buildStat('最近检查', formatAdminDateTime(duplicateLatestCheckedAt), 'slate')
      ]
    },
    {
      id: 'content-analysis',
      title: '关键信息整理',
      description: '补齐摘要、分类和关键信息。',
      note: '整理完成后，再决定是否追加智能整理。',
      stats: [
        buildStat('关键信息完成', formatCount(analysisOverview?.base_ready_posts ?? analysisOverview?.analyzed_posts, ' 条'), 'sky'),
        buildStat('关键信息字段完成', formatCount(insightOverview?.insight_posts, ' 条'), 'fuchsia'),
        buildStat('待补齐', formatCount(analysisOverview?.base_pending_posts ?? insightOverview?.pending_insight_posts, ' 条'), 'slate'),
        buildStat('最近完成', formatAdminDateTime(insightLatestAnalyzedAt || analysisLatestAnalyzedAt), 'slate')
      ]
    },
    {
      id: 'job-index',
      title: '岗位整理',
      description: '从正文和附件整理岗位信息。',
      note: '新增岗位会在写入后陆续计入总数。',
      stats: [
        buildStat('岗位总数', formatCount(jobsOverview?.total_jobs, ' 个'), 'cyan', { meta: jobLiveMeta }),
        buildStat('含岗位帖子', formatCount(jobsOverview?.posts_with_jobs, ' 条'), 'cyan'),
        buildStat('待补齐', formatCount(jobsOverview?.pending_posts, ' 条'), 'amber'),
        buildStat('辅导员岗位', formatCount(jobsOverview?.counselor_jobs, ' 个'), 'emerald'),
        buildStat('最近完成', formatAdminDateTime(jobLatestExtractedAt), 'slate')
      ]
    }
  ]
}

export function buildAiEnhancementPanels({
  openaiReady = false,
  disabledReason = '',
  analysisRuntime = null,
  analysisOverview = null,
  jobsOverview = null,
  taskRuns = []
} = {}) {
  const runtimeCopy = getAdminRuntimeCopy(analysisRuntime)
  const readinessLabel = getOpenAiReadinessLabel({ openaiReady, analysisRuntime })
  const resolvedDisabledReason = resolveAiDisabledReason({
    openaiReady,
    disabledReason,
    analysisRuntime
  })
  const modelLabel = openaiReady
    ? (analysisRuntime?.model_name || NOT_FETCHED_LABEL)
    : '未配置'
  const modelHelper = openaiReady
    ? '当前会使用这个模型补充摘要和岗位识别。'
    : '完成智能服务设置后即可使用。'
  const modelMeta = openaiReady
    ? '不会影响基础处理结果。'
    : '不会影响抓取、关键信息整理和岗位整理。'
  const aiAnalysisLiveMeta = buildAiAnalysisLiveMeta(taskRuns)
  const aiJobLiveMeta = buildJobExtractionLiveMeta(taskRuns, { useAi: true })

  return [
    {
      id: 'ai-runtime-status',
      title: '当前可用能力',
      value: readinessLabel,
      helper: runtimeCopy.description,
      meta: runtimeCopy.emphasis,
      disabled: !openaiReady,
      disabledReason: resolvedDisabledReason
    },
    {
      id: 'ai-models',
      title: '当前模型',
      value: modelLabel,
      helper: modelHelper,
      meta: modelMeta,
      disabled: !openaiReady,
      disabledReason: resolvedDisabledReason
    },
    {
      id: 'ai-analysis-coverage',
      title: '智能摘要覆盖率',
      value: formatAdminPercent(analysisOverview?.openai_analyzed_posts, analysisOverview?.total_posts),
      helper: `已覆盖 ${formatCount(analysisOverview?.openai_analyzed_posts, ' 条')}`,
      meta: [`待补充 ${formatCount(analysisOverview?.openai_pending_posts, ' 条')}`, ...aiAnalysisLiveMeta],
      disabled: !openaiReady,
      disabledReason: resolvedDisabledReason
    },
    {
      id: 'ai-job-extraction-coverage',
      title: '智能岗位识别覆盖率',
      value: formatAdminPercent(jobsOverview?.ai_job_posts, jobsOverview?.posts_with_jobs),
      helper: `智能识别帖子 ${formatCount(jobsOverview?.ai_job_posts, ' 条')}`,
      meta: [`附件/本地岗位帖子 ${formatCount(jobsOverview?.attachment_job_posts, ' 条')}`, ...aiJobLiveMeta],
      disabled: !openaiReady,
      disabledReason: resolvedDisabledReason
    }
  ]
}
