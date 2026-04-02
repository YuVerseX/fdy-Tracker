import {
  buildTaskRequestConfig,
  getTaskActionDefinitions
} from './adminDashboardTaskActions.js'
import { normalizeAdminUiMessage, normalizeAdminUiText } from '../../utils/adminCopySanitizers.js'

const TASK_ACTION_FEEDBACK = Object.freeze({
  retry: {
    success: '重试任务已提交',
    error: '重试任务失败'
  },
  rerun: {
    success: '再次运行已提交',
    error: '再次运行失败'
  },
  incremental: {
    success: '补处理任务已提交',
    error: '补处理任务失败'
  },
  cancel: {
    success: '终止请求已提交',
    error: '提交终止请求失败'
  }
})
const TASK_SUMMARY_FETCH_SUCCESS = 'success'
const TASK_SUMMARY_FETCH_DEGRADED = 'degraded'

const resolveTaskType = (run = {}) => run?.task_type || run?.taskType || ''

const resolveTaskParams = (run = {}) => {
  const sources = [
    run?.params,
    run?.details?.params,
    run?.details?.request_params,
    run?.details?.requestParams
  ]
  for (const source of sources) {
    if (source && typeof source === 'object') return source
  }
  return {}
}

export function createAdminDashboardDataService({
  adminApi, adminAuthorized, adminAuthChecking, adminAuthError, adminAuthForm, feedback, sourceOptions, state, loading, loaded, requests, forms
} = {}) {
  const latestRequestIds = {
    taskRuns: 0,
    taskSummary: 0,
    scheduler: 0,
    analysis: 0,
    insight: 0,
    jobs: 0,
    duplicate: 0
  }
  let latestTaskCenterRefreshId = 0
  let runtimeGeneration = 0
  const setFeedback = (type, message) => { feedback.value = { type, message } }
  const isTaskSummaryFetchSuccessful = (result) => result === TASK_SUMMARY_FETCH_SUCCESS
  const isTaskSummaryFetchContinuable = (result) => (
    result === TASK_SUMMARY_FETCH_SUCCESS || result === TASK_SUMMARY_FETCH_DEGRADED
  )
  const shouldMarkTaskStatusSync = (taskRunsResult, taskSummaryResult) => (
    adminAuthorized.value && taskRunsResult === true && isTaskSummaryFetchContinuable(taskSummaryResult)
  )
  const isTaskCenterRefreshSuccessful = (taskRunsResult, taskSummaryResult) => (
    adminAuthorized.value && taskRunsResult === true && isTaskSummaryFetchContinuable(taskSummaryResult)
  )
  const createTaskCenterRefreshGuard = () => {
    const refreshId = ++latestTaskCenterRefreshId
    const generation = runtimeGeneration
    return () => generation === runtimeGeneration && refreshId === latestTaskCenterRefreshId
  }
  const createRequestGuard = (key, externalGuard = () => true) => {
    const requestId = ++latestRequestIds[key]
    const generation = runtimeGeneration
    return () => generation === runtimeGeneration && externalGuard() && requestId === latestRequestIds[key]
  }
  const getCurrentTaskRunsResult = () => loaded.taskRuns === true
  const getCurrentTaskSummaryResult = () => {
    if (loaded.taskSummary) return TASK_SUMMARY_FETCH_SUCCESS
    if (state.taskSummaryUnavailable) return TASK_SUMMARY_FETCH_DEGRADED
    return false
  }
  const clearAdminRuntimeState = () => {
    runtimeGeneration += 1
    Object.assign(state, { taskRuns: [], taskSummary: null, taskSummaryUnavailable: false, analysisSummary: null, insightSummary: null, jobSummary: null, duplicateSummary: null, expandedTaskIds: [], retryingTaskId: '', retryingTaskActionKey: '', cancelingTaskId: '', jobsSummaryUnavailable: false, taskStatusLastSyncedAt: '' })
    Object.keys(loaded).forEach((key) => { loaded[key] = false })
  }
  const markTaskStatusSynced = () => {
    state.taskStatusLastSyncedAt = new Date().toISOString()
  }
  const handleAdminAccessError = (error) => {
    const status = error?.response?.status
    if (status !== 401 && status !== 503) return false
    adminAuthorized.value = false
    adminAuthForm.password = ''
    clearAdminRuntimeState()
    adminAuthError.value = normalizeAdminUiMessage(
      error?.response?.data?.detail,
      status === 401 ? '登录状态已失效，请重新登录。' : '暂时无法验证登录状态，请稍后再试。'
    )
    return true
  }
  const getErrorMessage = (error, fallback) => normalizeAdminUiMessage(error?.response?.data?.detail, fallback)
  const isTaskConflictError = (error) => {
    const detail = normalizeAdminUiMessage(error?.response?.data?.detail, '')
    return error?.response?.status === 409 && /已经在运行|刷新记录|确认后台状态/.test(detail)
  }
  const getTaskSubmissionFeedback = (error, fallback) => {
    if (error?.code === 'ECONNABORTED') {
      return {
        type: 'warning',
        message: '请求超时，已刷新当前状态，请在任务中心确认是否已受理。',
        shouldRefresh: true
      }
    }

    if (isTaskConflictError(error)) {
      return {
        type: 'warning',
        message: '已有同类任务在运行，已为你刷新当前状态。',
        shouldRefresh: true
      }
    }

    return {
      type: 'error',
      message: getErrorMessage(error, fallback),
      shouldRefresh: false
    }
  }
  const applySchedulerConfig = (payload = {}) => {
    Object.assign(forms.scheduler, { enabled: payload.enabled ?? true, intervalSeconds: Number(payload.interval_seconds ?? payload.intervalSeconds ?? 7200), defaultSourceId: Number(payload.default_source_id ?? payload.defaultSourceId ?? forms.scrape.sourceId ?? 1), defaultMaxPages: Number(payload.default_max_pages ?? payload.defaultMaxPages ?? forms.scrape.maxPages ?? 5), nextRunAt: payload.next_run_at || payload.nextRunAt || '', updatedAt: payload.updated_at || payload.updatedAt || '' })
    forms.scrape.sourceId = forms.scheduler.defaultSourceId
    forms.scrape.maxPages = forms.scheduler.defaultMaxPages
  }
  const verifyAdminAccess = async () => {
    adminAuthChecking.value = true
    adminAuthError.value = ''
    try {
      const response = await adminApi.getSession()
      adminAuthorized.value = true
      adminAuthForm.username = response?.data?.username || adminAuthForm.username
      return true
    } catch (error) {
      if (!handleAdminAccessError(error)) setFeedback('error', getErrorMessage(error, '验证登录状态失败'))
      return false
    } finally {
      adminAuthChecking.value = false
    }
  }
  const fetchTaskRuns = async ({ isCurrentRequest = () => true } = {}) => {
    const isCurrent = createRequestGuard('taskRuns', isCurrentRequest)
    loading.taskRuns = true
    try {
      const response = await adminApi.getTaskRuns({ limit: 10 })
      if (!isCurrent()) return getCurrentTaskRunsResult()
      state.taskRuns = response.data.items || []
      loaded.taskRuns = true
      return true
    } catch (error) {
      if (!isCurrent()) return getCurrentTaskRunsResult()
      state.taskRuns = []
      loaded.taskRuns = false
      if (!handleAdminAccessError(error)) setFeedback('error', getErrorMessage(error, '加载任务记录失败'))
      return false
    } finally {
      if (isCurrent()) loading.taskRuns = false
    }
  }
  const fetchTaskSummary = async ({ isCurrentRequest = () => true } = {}) => {
    const isCurrent = createRequestGuard('taskSummary', isCurrentRequest)
    loading.taskSummary = true
    try {
      const response = await adminApi.getTaskSummary()
      if (!isCurrent()) return getCurrentTaskSummaryResult()
      state.taskSummary = response.data || null
      state.taskSummaryUnavailable = false
      loaded.taskSummary = true
      return TASK_SUMMARY_FETCH_SUCCESS
    } catch (error) {
      if (!isCurrent()) return getCurrentTaskSummaryResult()
      state.taskSummary = null
      loaded.taskSummary = false
      if (handleAdminAccessError(error)) return false
      state.taskSummaryUnavailable = true
      console.warn('获取任务摘要失败，继续回退到任务记录:', error)
      return TASK_SUMMARY_FETCH_DEGRADED
    } finally {
      if (isCurrent()) loading.taskSummary = false
    }
  }
  const fetchSources = async () => {
    try {
      const response = await adminApi.getSources()
      const items = response.data.items || []
      if (items.length) {
        sourceOptions.value = items.map((source) => ({
          label: `${source.name}${source.is_active ? '' : ' / 已停用'}`,
          value: source.id,
          isActive: source.is_active
        }))
      }
    } catch (error) {
      if (!handleAdminAccessError(error)) console.warn('获取数据源列表失败，继续使用默认选项:', error)
    }
  }
  const fetchSchedulerConfig = async ({ isCurrentRequest = () => true } = {}) => {
    const isCurrent = createRequestGuard('scheduler', isCurrentRequest)
    loading.scheduler = true
    try {
      const response = await adminApi.getSchedulerConfig()
      if (!isCurrent()) return loaded.scheduler === true
      applySchedulerConfig(response.data || {})
      loaded.scheduler = true
      return true
    } catch (error) {
      if (!isCurrent()) return loaded.scheduler === true
      loaded.scheduler = false
      if (!handleAdminAccessError(error)) setFeedback('error', getErrorMessage(error, '加载定时抓取配置失败'))
      return false
    } finally {
      if (isCurrent()) loading.scheduler = false
    }
  }
  const fetchAnalysisSummary = async ({ suppressFeedback = false, isCurrentRequest = () => true } = {}) => {
    const isCurrent = createRequestGuard('analysis', isCurrentRequest)
    loading.analysis = true
    try {
      const response = await adminApi.getAnalysisSummary()
      if (!isCurrent()) return loaded.analysis === true
      state.analysisSummary = response.data || null
      loaded.analysis = true
      return true
    } catch (error) {
      if (!isCurrent()) return loaded.analysis === true
      state.analysisSummary = null
      loaded.analysis = false
      if (!handleAdminAccessError(error) && !suppressFeedback) setFeedback('error', getErrorMessage(error, '加载分析摘要失败'))
      return false
    } finally {
      if (isCurrent()) loading.analysis = false
    }
  }
  const fetchInsightSummary = async ({ suppressFeedback = false, isCurrentRequest = () => true } = {}) => {
    const isCurrent = createRequestGuard('insight', isCurrentRequest)
    loading.insight = true
    try {
      const response = await adminApi.getInsightSummary()
      if (!isCurrent()) return loaded.insight === true
      state.insightSummary = response.data || null
      loaded.insight = true
      return true
    } catch (error) {
      if (!isCurrent()) return loaded.insight === true
      state.insightSummary = null
      if (handleAdminAccessError(error)) return false
      loaded.insight = error?.response?.status === 404 || error?.response?.status === 405
      if (!loaded.insight && !suppressFeedback) setFeedback('error', getErrorMessage(error, '加载关键信息字段摘要失败'))
      return loaded.insight
    } finally {
      if (isCurrent()) loading.insight = false
    }
  }
  const fetchJobSummary = async ({ suppressFeedback = false, isCurrentRequest = () => true } = {}) => {
    const isCurrent = createRequestGuard('jobs', isCurrentRequest)
    loading.jobs = true
    state.jobsSummaryUnavailable = false
    try {
      const response = await adminApi.getJobSummary()
      if (!isCurrent()) return loaded.jobs === true
      state.jobSummary = response.data || null
      loaded.jobs = true
      return true
    } catch (error) {
      if (!isCurrent()) return loaded.jobs === true
      state.jobSummary = null
      if (handleAdminAccessError(error)) return false
      loaded.jobs = error?.response?.status === 404 || error?.response?.status === 405
      state.jobsSummaryUnavailable = loaded.jobs
      if (!loaded.jobs && !suppressFeedback) setFeedback('error', getErrorMessage(error, '加载岗位摘要失败'))
      return loaded.jobs
    } finally {
      if (isCurrent()) loading.jobs = false
    }
  }
  const fetchDuplicateSummary = async ({ suppressFeedback = false, isCurrentRequest = () => true } = {}) => {
    const isCurrent = createRequestGuard('duplicate', isCurrentRequest)
    loading.duplicate = true
    try {
      const response = await adminApi.getDuplicateSummary()
      if (!isCurrent()) return loaded.duplicate === true
      state.duplicateSummary = response.data || null
      loaded.duplicate = true
      return true
    } catch (error) {
      if (!isCurrent()) return loaded.duplicate === true
      state.duplicateSummary = null
      loaded.duplicate = false
      if (!handleAdminAccessError(error) && !suppressFeedback) setFeedback('error', getErrorMessage(error, '加载重复整理概览失败'))
      return false
    } finally {
      if (isCurrent()) loading.duplicate = false
    }
  }
  const refreshOverview = async () => {
    if (!adminAuthorized.value) return false
    loading.overview = true
    try {
      const isCurrentTaskCenterRequest = createTaskCenterRefreshGuard()
      const results = await Promise.all([
        fetchTaskSummary({ isCurrentRequest: isCurrentTaskCenterRequest }),
        fetchTaskRuns({ isCurrentRequest: isCurrentTaskCenterRequest }),
        fetchSchedulerConfig(),
        fetchAnalysisSummary(),
        fetchInsightSummary(),
        fetchJobSummary(),
        fetchDuplicateSummary()
      ])
      const [taskSummaryResult, taskRunsResult, ...otherResults] = results
      if (isCurrentTaskCenterRequest() && shouldMarkTaskStatusSync(taskRunsResult, taskSummaryResult)) markTaskStatusSynced()
      return isTaskCenterRefreshSuccessful(taskRunsResult, taskSummaryResult) && otherResults.every((result) => result === true)
    } finally {
      loading.overview = false
    }
  }
  const refreshAfterTask = async ({ includeAnalysis = false, includeInsight = false, includeJobs = false, includeDuplicate = false } = {}) => {
    if (!adminAuthorized.value) return false
    const isCurrentTaskCenterRequest = createTaskCenterRefreshGuard()
    const tasks = [
      fetchTaskRuns({ isCurrentRequest: isCurrentTaskCenterRequest }),
      fetchTaskSummary({ isCurrentRequest: isCurrentTaskCenterRequest })
    ]
    if (includeAnalysis) tasks.push(fetchAnalysisSummary({ suppressFeedback: true }))
    if (includeInsight) tasks.push(fetchInsightSummary({ suppressFeedback: true }))
    if (includeJobs) tasks.push(fetchJobSummary({ suppressFeedback: true }))
    if (includeDuplicate) tasks.push(fetchDuplicateSummary({ suppressFeedback: true }))
    const results = await Promise.all(tasks)
    const [taskRunsResult, taskSummaryResult] = results
    if (isCurrentTaskCenterRequest() && shouldMarkTaskStatusSync(taskRunsResult, taskSummaryResult)) markTaskStatusSynced()
    return isTaskCenterRefreshSuccessful(taskRunsResult, taskSummaryResult)
  }
  const runNamedTask = async (taskType, busyKey, params = {}) => {
    const config = buildTaskRequestConfig(taskType, { params, forms })
    if (!config) return
    requests[busyKey] = true
    try {
      const response = await adminApi[config.apiAction](config.payload)
      setFeedback('success', normalizeAdminUiText(response?.data?.message || '任务已提交', '任务已提交'))
      await refreshAfterTask(config.refreshOptions)
    } catch (error) {
      if (handleAdminAccessError(error)) return

      const submissionFeedback = getTaskSubmissionFeedback(
        error,
        config.errorMessage
      )

      if (submissionFeedback.shouldRefresh) {
        const refreshSucceeded = await refreshAfterTask(config.refreshOptions)
        if (!refreshSucceeded) return
      }

      const feedbackMessage = submissionFeedback.type === 'error'
        ? (config.resolveError?.(error) || submissionFeedback.message)
        : submissionFeedback.message

      setFeedback(submissionFeedback.type, feedbackMessage)
    } finally {
      requests[busyKey] = false
    }
  }
  const retryTaskRun = async (run, actionKey = 'retry') => {
    const taskType = resolveTaskType(run)
    const taskParams = resolveTaskParams(run)
    const actionDefinition = getTaskActionDefinitions(run).find((item) => item.key === actionKey)
    const config = buildTaskRequestConfig(taskType, {
      actionKey,
      params: taskParams,
      forms,
      rerunOfTaskId: run?.id || ''
    })
    if (!config || !actionDefinition) {
      setFeedback('error', '当前记录暂不支持这个操作。')
      return
    }
    state.retryingTaskId = run?.id || ''
    state.retryingTaskActionKey = actionKey
    try {
      const response = await adminApi[config.apiAction](config.payload)
      setFeedback('success', normalizeAdminUiText(response?.data?.message || TASK_ACTION_FEEDBACK[actionKey]?.success || '任务已提交', '任务已提交'))
      await refreshAfterTask(config.refreshOptions)
    } catch (error) {
      if (handleAdminAccessError(error)) return

      const retryErrorFallback = TASK_ACTION_FEEDBACK[actionKey]?.error || config.errorMessage || '任务提交失败'
      const submissionFeedback = getTaskSubmissionFeedback(
        error,
        retryErrorFallback
      )

      if (submissionFeedback.shouldRefresh) {
        const refreshSucceeded = await refreshAfterTask(config.refreshOptions)
        if (!refreshSucceeded) return
      }

      const feedbackMessage = submissionFeedback.type === 'error'
        ? (config.resolveError?.(error) || submissionFeedback.message)
        : submissionFeedback.message

      setFeedback(submissionFeedback.type, feedbackMessage)
    } finally {
      state.retryingTaskId = ''
      state.retryingTaskActionKey = ''
    }
  }
  const cancelTaskRun = async (run) => {
    if (!run?.id) return
    state.cancelingTaskId = run.id
    try {
      const response = await adminApi.cancelTaskRun(run.id)
      setFeedback('success', normalizeAdminUiText(response?.data?.message || TASK_ACTION_FEEDBACK.cancel.success, TASK_ACTION_FEEDBACK.cancel.success))
      await refreshTaskStatus()
    } catch (error) {
      if (handleAdminAccessError(error)) return
      if (error?.response?.status === 409) await refreshTaskStatus()
      setFeedback('error', getErrorMessage(error, TASK_ACTION_FEEDBACK.cancel.error))
    } finally {
      state.cancelingTaskId = ''
    }
  }
  const toggleTaskExpanded = (taskId) => {
    state.expandedTaskIds = state.expandedTaskIds.includes(taskId)
      ? state.expandedTaskIds.filter((id) => id !== taskId)
      : [...state.expandedTaskIds, taskId]
  }
  const submitAdminLogin = async () => {
    if (!String(adminAuthForm.username || '').trim() || !String(adminAuthForm.password || '')) {
      adminAuthError.value = '请输入账号和密码。'
      return
    }
    adminAuthChecking.value = true
    adminAuthError.value = ''
    try {
      const response = await adminApi.login(String(adminAuthForm.username).trim(), String(adminAuthForm.password))
      adminAuthorized.value = true
      adminAuthForm.username = response?.data?.username || String(adminAuthForm.username).trim()
      adminAuthForm.password = ''
      await fetchSources()
      await refreshOverview()
    } catch (error) {
      if (!handleAdminAccessError(error)) adminAuthError.value = getErrorMessage(error, '登录失败')
    } finally {
      adminAuthChecking.value = false
    }
  }
  const logoutAdmin = async () => {
    try {
      await adminApi.logout()
      setFeedback('success', '已退出登录')
    } catch (error) {
      setFeedback('error', getErrorMessage(error, '退出失败，请稍后再试。'))
      adminAuthError.value = '退出请求未完成，当前已清除本地状态。刷新后若仍显示已登录，请再试一次。'
    } finally {
      adminAuthorized.value = false
      adminAuthForm.password = ''
      clearAdminRuntimeState()
    }
  }
  const saveSchedulerConfig = async () => {
    loading.schedulerSaving = true
    try {
      const payload = { enabled: forms.scheduler.enabled, interval_seconds: forms.scheduler.intervalSeconds, default_source_id: forms.scheduler.defaultSourceId, default_max_pages: forms.scheduler.defaultMaxPages }
      const response = await adminApi.updateSchedulerConfig(payload)
      applySchedulerConfig(response.data?.config || payload)
      loaded.scheduler = true
      setFeedback('success', response.data?.message || '定时抓取配置已更新')
    } catch (error) {
      if (!handleAdminAccessError(error)) setFeedback('error', getErrorMessage(error, '保存定时抓取配置失败'))
    } finally {
      loading.schedulerSaving = false
    }
  }
  const refreshTaskStatus = async () => {
    if (!adminAuthorized.value) return false
    const isCurrentTaskCenterRequest = createTaskCenterRefreshGuard()
    const [taskRunsResult, taskSummaryResult] = await Promise.all([
      fetchTaskRuns({ isCurrentRequest: isCurrentTaskCenterRequest }),
      fetchTaskSummary({ isCurrentRequest: isCurrentTaskCenterRequest })
    ])
    if (isCurrentTaskCenterRequest() && shouldMarkTaskStatusSync(taskRunsResult, taskSummaryResult)) markTaskStatusSynced()
    return isTaskCenterRefreshSuccessful(taskRunsResult, taskSummaryResult)
  }
  return {
    verifyAdminAccess, fetchTaskRuns, fetchTaskSummary, fetchSources, fetchSchedulerConfig, fetchAnalysisSummary, fetchInsightSummary, fetchJobSummary, fetchDuplicateSummary,
    refreshSchedulerConfig: fetchSchedulerConfig,
    refreshAnalysisSummary: fetchAnalysisSummary,
    refreshStructuredSummary: fetchInsightSummary,
    refreshJobSummary: fetchJobSummary,
    refreshDuplicateSummary: fetchDuplicateSummary,
    refreshOverview, refreshTaskStatus, submitAdminLogin, logoutAdmin, saveSchedulerConfig, retryTaskRun, cancelTaskRun, toggleTaskExpanded,
    runScrapeTask: () => runNamedTask('manual_scrape', 'scrape'),
    runBackfillTask: () => runNamedTask('attachment_backfill', 'backfill'),
    runDuplicateBackfillTask: () => runNamedTask('duplicate_backfill', 'duplicate'),
    runBaseAnalysisTask: () => runNamedTask('base_analysis_backfill', 'baseAnalysis'),
    runAiAnalysisTask: () => runNamedTask('ai_analysis', 'aiAnalysis'),
    runJobIndexTask: () => runNamedTask('job_extraction', 'jobExtraction'),
    runAiJobExtractionTask: () => runNamedTask('ai_job_extraction', 'jobExtraction')
  }
}
