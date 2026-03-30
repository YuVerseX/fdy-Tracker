const TASK_REFRESH_OPTIONS = Object.freeze({
  manual_scrape: { includeAnalysis: true, includeInsight: true, includeJobs: true, includeDuplicate: true },
  scheduled_scrape: { includeAnalysis: true, includeInsight: true, includeJobs: true, includeDuplicate: true },
  attachment_backfill: { includeAnalysis: true, includeInsight: true, includeJobs: true, includeDuplicate: true },
  duplicate_backfill: { includeDuplicate: true },
  base_analysis_backfill: { includeAnalysis: true, includeInsight: true },
  ai_analysis: { includeAnalysis: true, includeInsight: true },
  job_extraction: { includeJobs: true, includeDuplicate: true },
  ai_job_extraction: { includeJobs: true, includeDuplicate: true }
})

const JOB_API_UNAVAILABLE_MESSAGE = '后端还没开放岗位索引接口，请先完成后端对接。'
const RETRYABLE_TASK_TYPES = new Set(Object.keys(TASK_REFRESH_OPTIONS))

const toNumber = (value, fallback) => {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : fallback
}

const toOptionalSourceId = (value) => {
  if (value === '' || value === null || value === undefined) return undefined
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : undefined
}

const toBoolean = (value, fallback) => {
  if (typeof value === 'boolean') return value
  if (value === 'true' || value === '1') return true
  if (value === 'false' || value === '0') return false
  return fallback
}

const getJobActionError = (error) => {
  return error?.response?.status === 404 || error?.response?.status === 405
    ? JOB_API_UNAVAILABLE_MESSAGE
    : ''
}

const TASK_REQUEST_BUILDERS = {
  manual_scrape: ({ params = {}, forms = {} }) => ({
    apiAction: 'runScrape',
    payload: {
      source_id: toNumber(params.source_id, toNumber(forms.scrape?.sourceId, 1)),
      max_pages: toNumber(params.max_pages, toNumber(forms.scrape?.maxPages, 5))
    },
    errorMessage: '手动抓取失败'
  }),
  scheduled_scrape: ({ params = {}, forms = {} }) => ({
    apiAction: 'runScrape',
    payload: {
      source_id: toNumber(params.source_id, toNumber(forms.scrape?.sourceId, 1)),
      max_pages: toNumber(params.max_pages, toNumber(forms.scrape?.maxPages, 5))
    },
    errorMessage: '手动抓取失败'
  }),
  attachment_backfill: ({ params = {}, forms = {} }) => ({
    apiAction: 'backfillAttachments',
    payload: {
      source_id: toOptionalSourceId(params.source_id ?? forms.backfill?.sourceId),
      limit: toNumber(params.limit, toNumber(forms.backfill?.limit, 100))
    },
    errorMessage: '历史附件补处理失败'
  }),
  duplicate_backfill: ({ params = {}, forms = {} }) => ({
    apiAction: 'backfillDuplicates',
    payload: {
      limit: toNumber(params.limit, toNumber(forms.duplicate?.limit, 200))
    },
    errorMessage: '历史去重补齐失败'
  }),
  base_analysis_backfill: ({ params = {}, forms = {} }) => ({
    apiAction: 'backfillBaseAnalysis',
    payload: {
      source_id: toOptionalSourceId(params.source_id ?? forms.baseAnalysis?.sourceId),
      limit: toNumber(params.limit, toNumber(forms.baseAnalysis?.limit, 100)),
      only_pending: toBoolean(params.only_pending, Boolean(forms.baseAnalysis?.onlyPending ?? true))
    },
    errorMessage: '基础分析补齐失败'
  }),
  ai_analysis: ({ params = {}, forms = {} }) => ({
    apiAction: 'runAiAnalysis',
    payload: {
      source_id: toOptionalSourceId(params.source_id ?? forms.aiAnalysis?.sourceId),
      limit: toNumber(params.limit, toNumber(forms.aiAnalysis?.limit, 100)),
      only_unanalyzed: toBoolean(params.only_unanalyzed, Boolean(forms.aiAnalysis?.onlyUnanalyzed ?? true))
    },
    errorMessage: 'AI 增强分析失败'
  }),
  job_extraction: ({ params = {}, forms = {} }) => ({
    apiAction: 'runJobExtraction',
    payload: {
      source_id: toOptionalSourceId(params.source_id ?? forms.jobIndex?.sourceId),
      limit: toNumber(params.limit, toNumber(forms.jobIndex?.limit, 100)),
      only_unindexed: toBoolean(
        params.only_unindexed ?? params.only_pending,
        Boolean(forms.jobIndex?.onlyPending ?? true)
      ),
      use_ai: false
    },
    errorMessage: '岗位索引补齐失败',
    resolveError: getJobActionError
  }),
  ai_job_extraction: ({ params = {}, forms = {} }) => ({
    apiAction: 'runJobExtraction',
    payload: {
      source_id: toOptionalSourceId(params.source_id ?? forms.aiJob?.sourceId),
      limit: toNumber(params.limit, toNumber(forms.aiJob?.limit, 100)),
      only_unindexed: toBoolean(
        params.only_unindexed ?? params.only_pending,
        Boolean(forms.aiJob?.onlyPending ?? true)
      ),
      use_ai: true
    },
    errorMessage: 'AI 岗位补抽失败',
    resolveError: getJobActionError
  })
}

export const canRetryTask = (taskType) => RETRYABLE_TASK_TYPES.has(taskType)

export const getTaskRefreshOptions = (taskType) => ({ ...(TASK_REFRESH_OPTIONS[taskType] || {}) })

export function buildTaskRequestConfig(taskType, options = {}) {
  const builder = TASK_REQUEST_BUILDERS[taskType]
  if (!builder) return null

  return {
    ...builder(options),
    refreshOptions: getTaskRefreshOptions(taskType)
  }
}
