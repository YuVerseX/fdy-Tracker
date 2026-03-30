import { getAdminRuntimeCopy } from './adminDashboardMeta.js'

const EMPTY_LABEL = '--'
const NOT_FETCHED_LABEL = '未获取'
const DEFAULT_AI_DISABLED_REASON = 'AI 增强当前不可用，基础模式仍可继续补齐。'

const TASK_TYPE_LABELS = {
  manual_scrape: '手动抓取最新数据',
  scheduled_scrape: '定时抓取',
  attachment_backfill: '补处理历史附件',
  duplicate_backfill: '补齐去重检查',
  base_analysis_backfill: '补齐基础分析',
  ai_analysis: '启动 AI 增强分析',
  job_extraction: '补齐岗位索引',
  ai_job_extraction: '启动 AI 岗位补抽'
}

const countItems = (items = []) => items.filter(Boolean).length

const normalizeNumber = (value) => {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

const formatCount = (value, suffix = '') => {
  const numeric = normalizeNumber(value)
  return numeric === null ? EMPTY_LABEL : `${numeric}${suffix}`
}

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
  const normalized = normalizeNumber(durationMs)
  if (normalized === null || normalized < 0) return EMPTY_LABEL
  if (normalized < 1000) return `${Math.round(normalized)}ms`

  const seconds = Math.floor(normalized / 1000)
  if (seconds < 60) return `${seconds}秒`

  const minutes = Math.floor(seconds / 60)
  const restSeconds = seconds % 60
  return `${minutes}分${restSeconds}秒`
}

export const getTaskTypeLabel = (taskType) => TASK_TYPE_LABELS[taskType] || taskType || EMPTY_LABEL

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

const buildStat = (label, value, tone = 'slate') => ({ label, value, tone })

const getOpenAiReadinessLabel = ({ openaiReady, analysisRuntime }) => {
  if (openaiReady) {
    return '已就绪'
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

  return [
    {
      id: 'collect-and-backfill',
      title: '采集与补处理',
      description: '负责把新帖子拉进来，并把历史附件补到可用。',
      note: '抓取负责新数据进入；补处理负责给旧数据补质量。',
      stats: [
        buildStat('最近抓取成功', formatAdminDateTime(scrapeTask?.finished_at || scrapeTask?.finishedAt), 'sky'),
        buildStat('最近补处理成功', formatAdminDateTime(attachmentBackfillTask?.finished_at || attachmentBackfillTask?.finishedAt), 'amber'),
        buildStat('待补处理', formatCount(analysisOverview?.base_pending_posts ?? insightOverview?.pending_insight_posts, ' 条'), 'slate'),
        buildStat('数据源范围', getSourceScopeLabel(sourceOptions), 'slate')
      ]
    },
    {
      id: 'duplicate-governance',
      title: '重复治理',
      description: '负责重复识别和主记录折叠，不和别的动作混在一起。',
      note: '这个入口只回答前台当前是不是主记录集合。',
      stats: [
        buildStat('重复组数', formatCount(duplicateOverview?.duplicate_groups), 'rose'),
        buildStat('折叠帖子', formatCount(duplicateOverview?.duplicate_posts), 'amber'),
        buildStat('未检查', formatCount(duplicateOverview?.unchecked_posts), 'slate'),
        buildStat('最近检查', formatAdminDateTime(duplicateLatestCheckedAt), 'slate')
      ]
    },
    {
      id: 'content-analysis',
      title: '内容分析',
      description: '补齐基础结构化结果，不把 AI 能力混成前提。',
      note: '无 AI 时也可以执行，优先补齐基础字段和统计口径。',
      stats: [
        buildStat('基础分析完成', formatCount(analysisOverview?.base_ready_posts ?? analysisOverview?.analyzed_posts, ' 条'), 'sky'),
        buildStat('结构化字段完成', formatCount(insightOverview?.insight_posts, ' 条'), 'fuchsia'),
        buildStat('待补齐', formatCount(analysisOverview?.base_pending_posts ?? insightOverview?.pending_insight_posts, ' 条'), 'slate'),
        buildStat('最近完成', formatAdminDateTime(insightLatestAnalyzedAt || analysisLatestAnalyzedAt), 'slate')
      ]
    },
    {
      id: 'job-index',
      title: '岗位索引',
      description: '基于正文和附件补齐岗位明细，AI 只是附加增强。',
      note: '默认补本地可恢复的岗位信息，不依赖 OpenAI 才能成立。',
      stats: [
        buildStat('岗位总数', formatCount(jobsOverview?.total_jobs, ' 个'), 'cyan'),
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
  jobsOverview = null
} = {}) {
  const runtimeCopy = getAdminRuntimeCopy(analysisRuntime)
  const readinessLabel = getOpenAiReadinessLabel({ openaiReady, analysisRuntime })
  const resolvedDisabledReason = resolveAiDisabledReason({
    openaiReady,
    disabledReason,
    analysisRuntime
  })
  const baseUrl = analysisRuntime?.base_url_configured ? analysisRuntime?.base_url || NOT_FETCHED_LABEL : 'OpenAI 官方默认'

  return [
    {
      id: 'ai-runtime-status',
      title: 'OpenAI 就绪状态',
      value: readinessLabel,
      helper: runtimeCopy.description,
      meta: runtimeCopy.emphasis,
      disabled: !openaiReady,
      disabledReason: resolvedDisabledReason
    },
    {
      id: 'ai-models',
      title: '模型',
      value: analysisRuntime?.model_name || NOT_FETCHED_LABEL,
      helper: `provider ${analysisRuntime?.provider || NOT_FETCHED_LABEL}`,
      meta: `接口 ${baseUrl}`,
      disabled: !openaiReady,
      disabledReason: resolvedDisabledReason
    },
    {
      id: 'ai-analysis-coverage',
      title: 'AI 分析覆盖率',
      value: formatAdminPercent(analysisOverview?.openai_analyzed_posts, analysisOverview?.total_posts),
      helper: `已覆盖 ${formatCount(analysisOverview?.openai_analyzed_posts, ' 条')}`,
      meta: `待增强 ${formatCount(analysisOverview?.openai_pending_posts, ' 条')}`,
      disabled: !openaiReady,
      disabledReason: resolvedDisabledReason
    },
    {
      id: 'ai-job-extraction-coverage',
      title: 'AI 岗位补抽覆盖率',
      value: formatAdminPercent(jobsOverview?.ai_job_posts, jobsOverview?.posts_with_jobs),
      helper: `AI 补抽帖子 ${formatCount(jobsOverview?.ai_job_posts, ' 条')}`,
      meta: `附件/本地岗位帖子 ${formatCount(jobsOverview?.attachment_job_posts, ' 条')}`,
      disabled: !openaiReady,
      disabledReason: resolvedDisabledReason
    }
  ]
}
