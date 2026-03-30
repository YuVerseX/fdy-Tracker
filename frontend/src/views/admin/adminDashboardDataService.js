import { buildTaskRequestConfig, canRetryTask } from './adminDashboardTaskActions.js'

export function createAdminDashboardDataService({
  adminApi, adminAuthorized, adminAuthChecking, adminAuthError, adminAuthForm, feedback, sourceOptions, state, loading, loaded, requests, forms
} = {}) {
  const setFeedback = (type, message) => { feedback.value = { type, message } }
  const clearAdminRuntimeState = () => {
    Object.assign(state, { taskRuns: [], taskSummary: null, taskSummaryUnavailable: false, analysisSummary: null, insightSummary: null, jobSummary: null, duplicateSummary: null, expandedTaskIds: [], retryingTaskId: '', jobsSummaryUnavailable: false })
    Object.keys(loaded).forEach((key) => { loaded[key] = false })
  }
  const handleAdminAccessError = (error) => {
    const status = error?.response?.status
    if (status !== 401 && status !== 503) return false
    adminAuthorized.value = false
    adminAuthForm.password = ''
    clearAdminRuntimeState()
    adminAuthError.value = error?.response?.data?.detail || (status === 401 ? '后台登录状态已失效，请重新登录。' : '后台会话鉴权暂不可用，请稍后再试。')
    return true
  }
  const getErrorMessage = (error, fallback) => error?.response?.status >= 500 ? '后端执行任务失败了，请稍后再试' : (error?.code === 'ECONNABORTED' ? '请求超时了，任务可能还在后台继续跑，我已经帮你刷新了任务记录' : (error?.response?.data?.detail || fallback))
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
      if (!handleAdminAccessError(error)) setFeedback('error', getErrorMessage(error, '后台登录验证失败'))
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
          label: `${source.name}（source_id=${source.id}）${source.is_active ? '' : ' / 已停用'}`,
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
      if (!loaded.insight) setFeedback('error', getErrorMessage(error, '加载结构化字段摘要失败'))
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
      if (!handleAdminAccessError(error)) setFeedback('error', getErrorMessage(error, '加载重复治理摘要失败'))
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
      setFeedback('success', response?.data?.message || '任务已提交')
      await refreshAfterTask(config.refreshOptions)
    } catch (error) {
      if (handleAdminAccessError(error)) return
      if (error?.code === 'ECONNABORTED' || error?.response?.status === 409) await refreshAfterTask(config.refreshOptions)
      setFeedback('error', config.resolveError?.(error) || getErrorMessage(error, config.errorMessage))
    } finally {
      requests[busyKey] = false
    }
  }
  const retryTaskRun = async (run) => {
    const taskType = run?.task_type
    const config = buildTaskRequestConfig(taskType, { params: run?.params || {}, forms })
    if (!config || !canRetryTask(taskType)) {
      setFeedback('error', '这个任务类型暂时不支持一键重试')
      return
    }
    state.retryingTaskId = run?.id || ''
    try {
      const response = await adminApi[config.apiAction](config.payload)
      setFeedback('success', response?.data?.message || '重试任务已提交')
      await refreshAfterTask(config.refreshOptions)
    } catch (error) {
      if (handleAdminAccessError(error)) return
      if (error?.code === 'ECONNABORTED' || error?.response?.status === 409) await refreshAfterTask(config.refreshOptions)
      setFeedback('error', config.resolveError?.(error) || getErrorMessage(error, '重试任务失败'))
    } finally {
      state.retryingTaskId = ''
    }
  }
  const toggleTaskExpanded = (taskId) => {
    state.expandedTaskIds = state.expandedTaskIds.includes(taskId)
      ? state.expandedTaskIds.filter((id) => id !== taskId)
      : [...state.expandedTaskIds, taskId]
  }
  const submitAdminLogin = async () => {
    if (!String(adminAuthForm.username || '').trim() || !String(adminAuthForm.password || '')) {
      adminAuthError.value = '请输入后台账号和密码。'
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
      if (!handleAdminAccessError(error)) adminAuthError.value = getErrorMessage(error, '后台登录失败')
    } finally {
      adminAuthChecking.value = false
    }
  }
  const logoutAdmin = async () => {
    try {
      await adminApi.logout()
      setFeedback('success', '已退出后台登录')
    } catch (error) {
      setFeedback('error', getErrorMessage(error, '退出后台登录失败，请稍后再试。'))
      adminAuthError.value = '退出请求未完成，已清空当前页面状态。刷新后若仍是已登录，请重试退出。'
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
