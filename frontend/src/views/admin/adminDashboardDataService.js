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
  }
})

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
  const setFeedback = (type, message) => { feedback.value = { type, message } }
  const clearAdminRuntimeState = () => {
    Object.assign(state, { taskRuns: [], taskSummary: null, taskSummaryUnavailable: false, analysisSummary: null, insightSummary: null, jobSummary: null, duplicateSummary: null, expandedTaskIds: [], retryingTaskId: '', retryingTaskActionKey: '', jobsSummaryUnavailable: false })
    Object.keys(loaded).forEach((key) => { loaded[key] = false })
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
  const getErrorMessage = (error, fallback) => {
    if (error?.response?.status >= 500) return '任务处理失败，请稍后再试。'
    if (error?.code === 'ECONNABORTED') return '请求已发出，结果正在更新，请稍后刷新任务中心。'
    return normalizeAdminUiMessage(error?.response?.data?.detail, fallback)
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
  const fetchTaskRuns = async () => {
    loading.taskRuns = true
    try {
      const response = await adminApi.getTaskRuns({ limit: 10 })
      state.taskRuns = response.data.items || []
      loaded.taskRuns = true
    } catch (error) {
      state.taskRuns = []
      loaded.taskRuns = false
      if (!handleAdminAccessError(error)) setFeedback('error', getErrorMessage(error, '加载任务记录失败'))
    } finally {
      loading.taskRuns = false
    }
  }
  const fetchTaskSummary = async () => {
    loading.taskSummary = true
    try {
      const response = await adminApi.getTaskSummary()
      state.taskSummary = response.data || null
      state.taskSummaryUnavailable = false
      loaded.taskSummary = true
    } catch (error) {
      state.taskSummary = null
      loaded.taskSummary = false
      if (handleAdminAccessError(error)) return
      state.taskSummaryUnavailable = true
      console.warn('获取任务摘要失败，继续回退到任务记录:', error)
    } finally {
      loading.taskSummary = false
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
  const fetchSchedulerConfig = async () => {
    loading.scheduler = true
    try {
      const response = await adminApi.getSchedulerConfig()
      applySchedulerConfig(response.data || {})
      loaded.scheduler = true
    } catch (error) {
      loaded.scheduler = false
      if (!handleAdminAccessError(error)) setFeedback('error', getErrorMessage(error, '加载定时抓取配置失败'))
    } finally {
      loading.scheduler = false
    }
  }
  const fetchAnalysisSummary = async () => {
    loading.analysis = true
    try {
      const response = await adminApi.getAnalysisSummary()
      state.analysisSummary = response.data || null
      loaded.analysis = true
    } catch (error) {
      state.analysisSummary = null
      loaded.analysis = false
      if (!handleAdminAccessError(error)) setFeedback('error', getErrorMessage(error, '加载分析摘要失败'))
    } finally {
      loading.analysis = false
    }
  }
  const fetchInsightSummary = async () => {
    loading.insight = true
    try {
      const response = await adminApi.getInsightSummary()
      state.insightSummary = response.data || null
      loaded.insight = true
    } catch (error) {
      state.insightSummary = null
      if (handleAdminAccessError(error)) return
      loaded.insight = error?.response?.status === 404 || error?.response?.status === 405
      if (!loaded.insight) setFeedback('error', getErrorMessage(error, '加载关键信息字段摘要失败'))
    } finally {
      loading.insight = false
    }
  }
  const fetchJobSummary = async () => {
    loading.jobs = true
    state.jobsSummaryUnavailable = false
    try {
      const response = await adminApi.getJobSummary()
      state.jobSummary = response.data || null
      loaded.jobs = true
    } catch (error) {
      state.jobSummary = null
      if (handleAdminAccessError(error)) return
      loaded.jobs = error?.response?.status === 404 || error?.response?.status === 405
      state.jobsSummaryUnavailable = loaded.jobs
      if (!loaded.jobs) setFeedback('error', getErrorMessage(error, '加载岗位摘要失败'))
    } finally {
      loading.jobs = false
    }
  }
  const fetchDuplicateSummary = async () => {
    loading.duplicate = true
    try {
      const response = await adminApi.getDuplicateSummary()
      state.duplicateSummary = response.data || null
      loaded.duplicate = true
    } catch (error) {
      state.duplicateSummary = null
      loaded.duplicate = false
      if (!handleAdminAccessError(error)) setFeedback('error', getErrorMessage(error, '加载重复整理概览失败'))
    } finally {
      loading.duplicate = false
    }
  }
  const refreshOverview = async () => {
    if (!adminAuthorized.value) return
    loading.overview = true
    try {
      await Promise.all([fetchTaskSummary(), fetchTaskRuns(), fetchSchedulerConfig(), fetchAnalysisSummary(), fetchInsightSummary(), fetchJobSummary(), fetchDuplicateSummary()])
    } finally {
      loading.overview = false
    }
  }
  const refreshAfterTask = async ({ includeAnalysis = false, includeInsight = false, includeJobs = false, includeDuplicate = false } = {}) => {
    if (!adminAuthorized.value) return
    const tasks = [fetchTaskRuns(), fetchTaskSummary()]
    if (includeAnalysis) tasks.push(fetchAnalysisSummary())
    if (includeInsight) tasks.push(fetchInsightSummary())
    if (includeJobs) tasks.push(fetchJobSummary())
    if (includeDuplicate) tasks.push(fetchDuplicateSummary())
    await Promise.all(tasks)
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
      if (error?.code === 'ECONNABORTED' || error?.response?.status === 409) await refreshAfterTask(config.refreshOptions)
      setFeedback('error', config.resolveError?.(error) || getErrorMessage(error, config.errorMessage))
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
      if (error?.code === 'ECONNABORTED' || error?.response?.status === 409) await refreshAfterTask(config.refreshOptions)
      setFeedback('error', config.resolveError?.(error) || getErrorMessage(error, TASK_ACTION_FEEDBACK[actionKey]?.error || '任务提交失败'))
    } finally {
      state.retryingTaskId = ''
      state.retryingTaskActionKey = ''
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
    if (adminAuthorized.value) {
      await Promise.all([fetchTaskRuns(), fetchTaskSummary()])
    }
  }
  return {
    verifyAdminAccess, fetchTaskRuns, fetchTaskSummary, fetchSources, fetchSchedulerConfig, fetchAnalysisSummary, fetchInsightSummary, fetchJobSummary, fetchDuplicateSummary,
    refreshSchedulerConfig: fetchSchedulerConfig,
    refreshAnalysisSummary: fetchAnalysisSummary,
    refreshStructuredSummary: fetchInsightSummary,
    refreshJobSummary: fetchJobSummary,
    refreshDuplicateSummary: fetchDuplicateSummary,
    refreshOverview, refreshTaskStatus, submitAdminLogin, logoutAdmin, saveSchedulerConfig, retryTaskRun, toggleTaskExpanded,
    runScrapeTask: () => runNamedTask('manual_scrape', 'scrape'),
    runBackfillTask: () => runNamedTask('attachment_backfill', 'backfill'),
    runDuplicateBackfillTask: () => runNamedTask('duplicate_backfill', 'duplicate'),
    runBaseAnalysisTask: () => runNamedTask('base_analysis_backfill', 'baseAnalysis'),
    runAiAnalysisTask: () => runNamedTask('ai_analysis', 'aiAnalysis'),
    runJobIndexTask: () => runNamedTask('job_extraction', 'jobExtraction'),
    runAiJobExtractionTask: () => runNamedTask('ai_job_extraction', 'jobExtraction')
  }
}
