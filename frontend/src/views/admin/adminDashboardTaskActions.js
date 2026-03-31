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

const JOB_API_UNAVAILABLE_MESSAGE = '岗位整理功能暂时不可用，请稍后再试。'
const RETRYABLE_TASK_TYPES = new Set(Object.keys(TASK_REFRESH_OPTIONS))
const INCREMENTAL_ACTION_TASK_TYPES = new Set([
  'base_analysis_backfill',
  'ai_analysis',
  'job_extraction',
  'ai_job_extraction'
])

const ACTION_COPY = Object.freeze({
  retry: {
    key: 'retry',
    label: '按原条件重试',
    busyLabel: '提交中...',
    description: '沿用上一轮的处理条件，再提交一次这项任务。',
    scopeLabel: '沿用上一轮范围'
  },
  rerun: {
    key: 'rerun',
    label: '再次运行',
    busyLabel: '提交中...',
    description: '按这条记录的条件重新完整运行一轮。',
    scopeLabel: '重新处理当前范围'
  },
  incremental: {
    key: 'incremental',
    label: '只补剩余',
    busyLabel: '提交中...',
    description: '只补还没处理完的内容，已经完成的结果会尽量保留。',
    scopeLabel: '仅补剩余内容'
  }
})

const ACTION_GUIDE_COPY = Object.freeze({
  title: '操作前说明',
  description: '先看每个按钮会处理哪些内容，再决定是重新运行这项任务，还是只补齐剩余部分。'
})

const TASK_ACTION_COPY_OVERRIDES = Object.freeze({
  manual_scrape: Object.freeze({
    retry: Object.freeze({
      key: 'retry',
      label: '按当前抓取范围重试',
      busyLabel: '提交中...',
      description: '沿用这次的数据源和页数，再抓一轮最新公告。',
      scopeLabel: '沿用当前抓取范围'
    }),
    rerun: Object.freeze({
      key: 'rerun',
      label: '重新抓取当前范围',
      busyLabel: '提交中...',
      description: '按这次的数据源和页数重新抓取，并刷新这批公告的最新状态。',
      scopeLabel: '重新抓取当前范围'
    })
  }),
  scheduled_scrape: Object.freeze({
    retry: Object.freeze({
      key: 'retry',
      label: '按当前抓取范围重试',
      busyLabel: '提交中...',
      description: '沿用这次的数据源和页数，再抓一轮最新公告。',
      scopeLabel: '沿用当前抓取范围'
    }),
    rerun: Object.freeze({
      key: 'rerun',
      label: '重新抓取当前范围',
      busyLabel: '提交中...',
      description: '按这次的数据源和页数重新抓取，并刷新这批公告的最新状态。',
      scopeLabel: '重新抓取当前范围'
    })
  }),
  attachment_backfill: Object.freeze({
    retry: Object.freeze({
      key: 'retry',
      label: '继续补齐当前范围附件',
      busyLabel: '提交中...',
      description: '沿用这次的数据源和批量，再提交一次附件补处理。',
      scopeLabel: '沿用当前补处理范围'
    }),
    rerun: Object.freeze({
      key: 'rerun',
      label: '重新补处理当前范围',
      busyLabel: '提交中...',
      description: '按这次范围重新检查附件，并刷新附件和字段整理结果。',
      scopeLabel: '重新补处理当前范围'
    })
  }),
  duplicate_backfill: Object.freeze({
    retry: Object.freeze({
      key: 'retry',
      label: '继续检查未检查记录',
      busyLabel: '提交中...',
      description: '继续补齐还没检查过的帖子，已经确认过的结果会保留。',
      scopeLabel: '仅处理未检查记录'
    }),
    rerun: Object.freeze({
      key: 'rerun',
      label: '重新检查当前范围',
      busyLabel: '提交中...',
      description: '按这次任务的范围重新检查最近一批帖子，并刷新这批记录的重复结果。',
      scopeLabel: '重新检查最近一批记录'
    })
  }),
  base_analysis_backfill: Object.freeze({
    retry: Object.freeze({
      key: 'retry',
      label: '按当前范围继续整理',
      busyLabel: '提交中...',
      description: '沿用这次的数据源、批量和筛选条件，再提交一次关键信息整理。',
      scopeLabel: '沿用当前整理范围'
    }),
    rerun: Object.freeze({
      key: 'rerun',
      label: '重新整理当前范围',
      busyLabel: '提交中...',
      description: '按这次范围重新整理关键信息，并刷新已有结果。',
      scopeLabel: '重新整理当前范围'
    }),
    incremental: Object.freeze({
      key: 'incremental',
      label: '只补未整理内容',
      busyLabel: '提交中...',
      description: '只补这次范围里还没完成关键信息整理的内容。',
      scopeLabel: '仅补未整理内容'
    })
  }),
  ai_analysis: Object.freeze({
    retry: Object.freeze({
      key: 'retry',
      label: '按当前范围继续补充',
      busyLabel: '提交中...',
      description: '沿用这次的数据源、批量和筛选条件，再提交一次智能摘要整理。',
      scopeLabel: '沿用当前整理范围'
    }),
    rerun: Object.freeze({
      key: 'rerun',
      label: '重新整理当前范围',
      busyLabel: '提交中...',
      description: '按这次范围重新补充智能摘要，并刷新已有结果。',
      scopeLabel: '重新整理当前范围'
    }),
    incremental: Object.freeze({
      key: 'incremental',
      label: '只补未补充内容',
      busyLabel: '提交中...',
      description: '只补这次范围里还没做智能整理的内容。',
      scopeLabel: '仅补未补充内容'
    })
  }),
  job_extraction: Object.freeze({
    retry: Object.freeze({
      key: 'retry',
      label: '按当前范围继续整理',
      busyLabel: '提交中...',
      description: '沿用这次的数据源、批量和筛选条件，再提交一次岗位整理。',
      scopeLabel: '沿用当前整理范围'
    }),
    rerun: Object.freeze({
      key: 'rerun',
      label: '重新整理当前范围岗位',
      busyLabel: '提交中...',
      description: '按这次范围重新整理岗位信息，并刷新已有结果。',
      scopeLabel: '重新整理当前范围岗位'
    }),
    incremental: Object.freeze({
      key: 'incremental',
      label: '只补未整理岗位',
      busyLabel: '提交中...',
      description: '只补这次范围里还没完成岗位整理的内容。',
      scopeLabel: '仅补未整理岗位'
    })
  }),
  ai_job_extraction: Object.freeze({
    retry: Object.freeze({
      key: 'retry',
      label: '按当前范围继续识别',
      busyLabel: '提交中...',
      description: '沿用这次的数据源、批量和筛选条件，再提交一次智能岗位识别。',
      scopeLabel: '沿用当前识别范围'
    }),
    rerun: Object.freeze({
      key: 'rerun',
      label: '重新识别当前范围岗位',
      busyLabel: '提交中...',
      description: '按这次范围重新识别岗位信息，并刷新已有结果。',
      scopeLabel: '重新识别当前范围岗位'
    }),
    incremental: Object.freeze({
      key: 'incremental',
      label: '只补未识别岗位',
      busyLabel: '提交中...',
      description: '只补这次范围里还没完成智能岗位识别的内容。',
      scopeLabel: '仅补未识别岗位'
    })
  })
})

const TASK_ACTION_GUIDE_COPY_OVERRIDES = Object.freeze({
  manual_scrape: Object.freeze({
    title: '操作前说明',
    description: '重试会沿用这次抓取范围；重新抓取会按当前范围再抓一轮最新公告。'
  }),
  attachment_backfill: Object.freeze({
    title: '操作前说明',
    description: '继续补齐会沿用这次范围补处理附件；重新补处理会刷新当前范围的附件和字段结果。'
  }),
  duplicate_backfill: Object.freeze({
    title: '操作前说明',
    description: '继续检查只会补齐还没检查过的帖子；重新检查会刷新当前范围内最近一批记录的重复结果。'
  }),
  base_analysis_backfill: Object.freeze({
    title: '操作前说明',
    description: '继续整理会沿用当前条件；重新整理会刷新当前范围；只补未整理内容只会补缺口。'
  }),
  ai_analysis: Object.freeze({
    title: '操作前说明',
    description: '继续补充会沿用当前条件；重新整理会刷新当前范围；只补未补充内容只会补缺口。'
  }),
  job_extraction: Object.freeze({
    title: '操作前说明',
    description: '继续整理会沿用当前条件；重新整理会刷新当前范围的岗位结果；只补未整理岗位只会补缺口。'
  }),
  ai_job_extraction: Object.freeze({
    title: '操作前说明',
    description: '继续识别会沿用当前条件；重新识别会刷新当前范围；只补未识别岗位只会补缺口。'
  })
})

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

const attachRerunOfTaskId = (payload, rerunOfTaskId) => (
  rerunOfTaskId ? { ...payload, rerun_of_task_id: rerunOfTaskId } : payload
)

const resolveDuplicateScopeMode = (actionKey, value) => {
  if (actionKey === 'rerun') return 'recheck_recent'
  if (actionKey === 'retry') return 'unchecked'
  return value === 'recheck_recent' ? 'recheck_recent' : 'unchecked'
}

const resolveIncrementalFlag = (actionKey, value, fallback) => (
  actionKey === 'incremental'
    ? true
    : actionKey === 'rerun'
      ? false
      : toBoolean(value, fallback)
)

const resolveActionDefinition = (taskType, actionKey, label = '') => {
  const overrideCopy = TASK_ACTION_COPY_OVERRIDES[taskType]?.[actionKey]
  const copy = overrideCopy || ACTION_COPY[actionKey]
  if (!copy) return null
  return {
    ...copy,
    label: overrideCopy ? copy.label : (label || copy.label)
  }
}

const buildTaskContextBadge = (run = {}) => {
  const rerunOfTaskId = run?.rerun_of_task_id || run?.rerunOfTaskId
  return rerunOfTaskId
    ? {
        label: '当前记录',
        value: '来自之前一次继续处理'
      }
    : null
}

const getBaseActionDefinitions = (run = {}) => {
  const taskType = run?.task_type || run?.taskType
  const backendActions = Array.isArray(run.actions)
    ? run.actions
        .map((item) => resolveActionDefinition(taskType, item?.key, item?.label))
        .filter(Boolean)
    : []
  if (backendActions.length > 0) return backendActions
  if (run?.status === 'failed') return [resolveActionDefinition(taskType, 'retry')].filter(Boolean)
  if (run?.status === 'success') return [resolveActionDefinition(taskType, 'rerun')].filter(Boolean)
  return []
}

const getJobActionError = (error) => {
  return error?.response?.status === 404 || error?.response?.status === 405
    ? JOB_API_UNAVAILABLE_MESSAGE
    : ''
}

const TASK_REQUEST_BUILDERS = {
  manual_scrape: ({ params = {}, forms = {}, rerunOfTaskId }) => ({
    apiAction: 'runScrape',
    payload: attachRerunOfTaskId({
      source_id: toNumber(params.source_id, toNumber(forms.scrape?.sourceId, 1)),
      max_pages: toNumber(params.max_pages, toNumber(forms.scrape?.maxPages, 5))
    }, rerunOfTaskId),
    errorMessage: '手动抓取失败'
  }),
  scheduled_scrape: ({ params = {}, forms = {}, rerunOfTaskId }) => ({
    apiAction: 'runScrape',
    payload: attachRerunOfTaskId({
      source_id: toNumber(params.source_id, toNumber(forms.scrape?.sourceId, 1)),
      max_pages: toNumber(params.max_pages, toNumber(forms.scrape?.maxPages, 5))
    }, rerunOfTaskId),
    errorMessage: '手动抓取失败'
  }),
  attachment_backfill: ({ params = {}, forms = {}, rerunOfTaskId }) => ({
    apiAction: 'backfillAttachments',
    payload: attachRerunOfTaskId({
      source_id: toOptionalSourceId(params.source_id ?? forms.backfill?.sourceId),
      limit: toNumber(params.limit, toNumber(forms.backfill?.limit, 100))
    }, rerunOfTaskId),
    errorMessage: '历史附件补处理失败'
  }),
  duplicate_backfill: ({ actionKey, params = {}, forms = {}, rerunOfTaskId }) => ({
    apiAction: 'backfillDuplicates',
    payload: attachRerunOfTaskId({
      limit: toNumber(params.limit, toNumber(forms.duplicate?.limit, 200)),
      scope_mode: resolveDuplicateScopeMode(actionKey, params.scope_mode)
    }, rerunOfTaskId),
    errorMessage: '历史去重补齐失败'
  }),
  base_analysis_backfill: ({ actionKey = 'retry', params = {}, forms = {}, rerunOfTaskId }) => ({
    apiAction: 'backfillBaseAnalysis',
    payload: attachRerunOfTaskId({
      source_id: toOptionalSourceId(params.source_id ?? forms.baseAnalysis?.sourceId),
      limit: toNumber(params.limit, toNumber(forms.baseAnalysis?.limit, 100)),
      only_pending: resolveIncrementalFlag(
        actionKey,
        params.only_pending,
        Boolean(forms.baseAnalysis?.onlyPending ?? true)
      )
    }, rerunOfTaskId),
    errorMessage: '关键信息整理失败'
  }),
  ai_analysis: ({ actionKey = 'retry', params = {}, forms = {}, rerunOfTaskId }) => ({
    apiAction: 'runAiAnalysis',
    payload: attachRerunOfTaskId({
      source_id: toOptionalSourceId(params.source_id ?? forms.aiAnalysis?.sourceId),
      limit: toNumber(params.limit, toNumber(forms.aiAnalysis?.limit, 100)),
      only_unanalyzed: resolveIncrementalFlag(
        actionKey,
        params.only_unanalyzed,
        Boolean(forms.aiAnalysis?.onlyUnanalyzed ?? true)
      )
    }, rerunOfTaskId),
    errorMessage: '智能摘要整理失败'
  }),
  job_extraction: ({ actionKey = 'retry', params = {}, forms = {}, rerunOfTaskId }) => ({
    apiAction: 'runJobExtraction',
    payload: attachRerunOfTaskId({
      source_id: toOptionalSourceId(params.source_id ?? forms.jobIndex?.sourceId),
      limit: toNumber(params.limit, toNumber(forms.jobIndex?.limit, 100)),
      only_unindexed: resolveIncrementalFlag(
        actionKey,
        params.only_unindexed ?? params.only_pending,
        Boolean(forms.jobIndex?.onlyPending ?? true)
      ),
      use_ai: toBoolean(params.use_ai, false)
    }, rerunOfTaskId),
    errorMessage: '岗位整理失败',
    resolveError: getJobActionError
  }),
  ai_job_extraction: ({ actionKey = 'retry', params = {}, forms = {}, rerunOfTaskId }) => ({
    apiAction: 'runJobExtraction',
    payload: attachRerunOfTaskId({
      source_id: toOptionalSourceId(params.source_id ?? forms.aiJob?.sourceId),
      limit: toNumber(params.limit, toNumber(forms.aiJob?.limit, 100)),
      only_unindexed: resolveIncrementalFlag(
        actionKey,
        params.only_unindexed ?? params.only_pending,
        Boolean(forms.aiJob?.onlyPending ?? true)
      ),
      use_ai: true
    }, rerunOfTaskId),
    errorMessage: '智能岗位识别失败',
    resolveError: getJobActionError
  })
}

export const canRetryTask = (taskType) => RETRYABLE_TASK_TYPES.has(taskType)

export const getTaskRefreshOptions = (taskType) => ({ ...(TASK_REFRESH_OPTIONS[taskType] || {}) })

export const getTaskActionDefinitions = (run = {}) => {
  const taskType = run?.task_type || run?.taskType
  if (!canRetryTask(taskType)) return []

  const actions = getBaseActionDefinitions(run)
  const actionKeys = new Set(actions.map((item) => item.key))

  if (run?.status === 'success' && INCREMENTAL_ACTION_TASK_TYPES.has(taskType) && !actionKeys.has('incremental')) {
    actions.push(resolveActionDefinition(taskType, 'incremental'))
  }

  return actions.filter(Boolean)
}

export const buildTaskActionGuide = (run = {}) => {
  const taskType = run?.task_type || run?.taskType
  const actions = getTaskActionDefinitions(run)
  if (actions.length === 0) return null

  return {
    ...ACTION_GUIDE_COPY,
    ...(TASK_ACTION_GUIDE_COPY_OVERRIDES[taskType] || {}),
    contextBadge: buildTaskContextBadge(run),
    actions
  }
}

export function buildTaskRequestConfig(taskType, options = {}) {
  const builder = TASK_REQUEST_BUILDERS[taskType]
  if (!builder) return null

  return {
    ...builder(options),
    refreshOptions: getTaskRefreshOptions(taskType)
  }
}
