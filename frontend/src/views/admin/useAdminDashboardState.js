import { computed, onMounted, onUnmounted, proxyRefs, reactive, ref } from 'vue'

import { adminApi } from '../../api/posts.js'
import {
  ADMIN_PROCESSING_TAB_OPTIONS,
  ADMIN_SECTION_LEGACY_ALIASES,
  ADMIN_SECTION_OPTIONS,
  getAdminRuntimeCopy
} from '../../utils/adminDashboardMeta.js'
import { buildAiEnhancementPanels, buildDataProcessingPanels, formatAdminDateTime, getTaskTypeLabel } from '../../utils/adminDashboardViewModels.js'
import { createAdminDashboardDataService } from './adminDashboardDataService.js'
import { buildAdminHealthState } from './adminDashboardHealth.js'
import {
  buildAiEnhancementSectionModel,
  buildDataProcessingSectionModel,
  buildOverviewSectionModel,
  buildProcessingSectionModel,
  buildSystemSectionModel,
  buildTaskRunsSectionModel
} from './adminDashboardSectionAdapters.js'
import { canRetryTask } from './adminDashboardTaskActions.js'
import { buildRecentTaskState } from './adminDashboardTaskSummary.js'

const TASK_HEARTBEAT_STALE_MS = 10 * 60 * 1000
const TASK_POLL_INTERVAL_MS = 15 * 1000
export const ADMIN_SECTION_ORDER = ADMIN_SECTION_OPTIONS.map((item) => item.value)
export const PROCESSING_MODE_ORDER = ADMIN_PROCESSING_TAB_OPTIONS.map((item) => item.value)

const ADMIN_SECTION_SET = new Set(ADMIN_SECTION_ORDER)
const PROCESSING_MODE_SET = new Set(PROCESSING_MODE_ORDER)

export const normalizeAdminDashboardBindings = (bindings) => proxyRefs(bindings)
export const normalizeAdminSection = (value) => {
  const aliasedValue = value === 'ai-enhancement'
    ? 'processing'
    : (ADMIN_SECTION_LEGACY_ALIASES[value] || value)
  return ADMIN_SECTION_SET.has(aliasedValue) ? aliasedValue : ADMIN_SECTION_ORDER[0]
}
export const normalizeProcessingMode = (value) => (
  PROCESSING_MODE_SET.has(value) ? value : PROCESSING_MODE_ORDER[0]
)

export function useAdminDashboardState() {
  const adminAuthorized = ref(false)
  const adminAuthChecking = ref(false)
  const adminAuthError = ref('')
  const adminAuthForm = reactive({ username: '', password: '' })
  const activeAdminSection = ref(ADMIN_SECTION_ORDER[0])
  const processingMode = ref(PROCESSING_MODE_ORDER[0])
  const feedback = ref({ type: '', message: '' })
  const sourceOptions = ref([{ label: '江苏省人社厅', value: 1, isActive: true }])
  const state = reactive({
    taskRuns: [],
    taskSummary: null,
    taskSummaryUnavailable: false,
    analysisSummary: null,
    insightSummary: null,
    jobSummary: null,
    duplicateSummary: null,
    expandedTaskIds: [],
    retryingTaskId: '',
    retryingTaskActionKey: '',
    cancelingTaskId: '',
    pollingInFlight: false,
    pollingTimerId: null,
    nowTs: Date.now(),
    jobsSummaryUnavailable: false
  })
  const loading = reactive({ scheduler: false, schedulerSaving: false, analysis: false, insight: false, jobs: false, duplicate: false, taskSummary: false, taskRuns: false, overview: false })
  const loaded = reactive({ scheduler: false, analysis: false, insight: false, jobs: false, duplicate: false, taskSummary: false, taskRuns: false })
  const requests = reactive({ scrape: false, backfill: false, duplicate: false, baseAnalysis: false, aiAnalysis: false, jobExtraction: false })
  const forms = reactive({
    scrape: { sourceId: 1, maxPages: 5 },
    backfill: { sourceId: '', limit: 100 },
    duplicate: { limit: 200 },
    baseAnalysis: { sourceId: '', limit: 100, onlyPending: true },
    aiAnalysis: { sourceId: '', limit: 100, onlyUnanalyzed: true },
    jobIndex: { sourceId: '', limit: 100, onlyPending: true },
    aiJob: { sourceId: '', limit: 100, onlyPending: true },
    scheduler: { enabled: true, intervalSeconds: 7200, defaultSourceId: 1, defaultMaxPages: 5, nextRunAt: '', updatedAt: '' }
  })
  const dataService = createAdminDashboardDataService({
    adminApi,
    adminAuthorized,
    adminAuthChecking,
    adminAuthError,
    adminAuthForm,
    feedback,
    sourceOptions,
    state,
    loading,
    loaded,
    requests,
    forms
  })

  const feedbackClass = computed(() => feedback.value.type === 'success' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-red-200 bg-red-50 text-red-700')
  const adminSavedUsername = computed(() => adminAuthForm.username || '')
  const analysisOverview = computed(() => state.analysisSummary?.overview ?? null)
  const analysisRuntime = computed(() => state.analysisSummary?.runtime ?? null)
  const insightOverview = computed(() => state.insightSummary?.overview ?? state.analysisSummary?.insight_overview ?? null)
  const jobsOverview = computed(() => state.jobSummary?.overview ?? null)
  const duplicateOverview = computed(() => state.duplicateSummary?.overview ?? null)
  const analysisLatestAnalyzedAt = computed(() => state.analysisSummary?.latest_analyzed_at || '')
  const insightLatestAnalyzedAt = computed(() => state.insightSummary?.latest_analyzed_at || state.analysisSummary?.latest_insight_at || '')
  const jobLatestExtractedAt = computed(() => state.jobSummary?.latest_extracted_at || '')
  const duplicateLatestCheckedAt = computed(() => state.duplicateSummary?.latest_checked_at || '')
  const runtimeCopy = computed(() => getAdminRuntimeCopy(analysisRuntime.value))
  const openaiReady = computed(() => loaded.analysis && Boolean(analysisRuntime.value?.openai_ready))
  const openaiUnavailableReason = computed(() => {
    if (!loaded.analysis || !analysisRuntime.value) return '智能服务状态正在更新，稍后再试。'
    if (!analysisRuntime.value.analysis_enabled) return '智能整理当前未开启，基础处理仍可继续。'
    if (!analysisRuntime.value.openai_configured) return '请先完成智能服务配置后再运行智能整理。'
    if (!analysisRuntime.value.openai_sdk_available) return '智能服务暂时不可用，请稍后再试。'
    return '智能整理暂时不可用，基础处理仍可继续。'
  })
  const aiJobBlockedReason = computed(() => {
    if (taskBusy.value.jobIndex || !taskBusy.value.aiAnalysis) return ''
    return '智能摘要整理正在运行，需等待这轮处理结束后再补充智能岗位识别。'
  })
  const recentTaskState = computed(() => buildRecentTaskState({
    taskSummary: state.taskSummary,
    taskSummaryLoaded: loaded.taskSummary,
    taskSummaryUnavailable: state.taskSummaryUnavailable,
    taskRuns: state.taskRuns,
    taskRunsLoaded: loaded.taskRuns
  }))
  const backendRunningTasks = computed(() => {
    if (!adminAuthorized.value) return []
    const combined = [...(Array.isArray(state.taskSummary?.running_tasks) ? state.taskSummary.running_tasks : []), ...state.taskRuns.filter((run) => ['queued', 'pending', 'running', 'processing'].includes(run?.status))]
    const seen = new Set()
    return combined.filter((run) => {
      const taskType = run?.task_type || run?.taskType
      const key = run?.id || `${taskType}-${run?.started_at || run?.startedAt || ''}`
      if (!taskType || seen.has(key)) return false
      seen.add(key)
      return true
    })
  })
  const isTaskTypeRunning = (...taskTypes) => backendRunningTasks.value.some((run) => taskTypes.includes(run?.task_type || run?.taskType))
  const taskBusy = computed(() => ({
    scrape: requests.scrape || isTaskTypeRunning('manual_scrape', 'scheduled_scrape'),
    backfill: requests.backfill || isTaskTypeRunning('attachment_backfill'),
    duplicate: requests.duplicate || isTaskTypeRunning('duplicate_backfill'),
    baseAnalysis: requests.baseAnalysis || isTaskTypeRunning('base_analysis_backfill'),
    aiAnalysis: requests.aiAnalysis || isTaskTypeRunning('ai_analysis'),
    jobIndex: requests.jobExtraction || isTaskTypeRunning('job_extraction', 'ai_job_extraction')
  }))
  const activeTaskHints = computed(() => {
    const hints = []
    if (taskBusy.value.scrape) hints.push('立即抓取最新数据')
    if (taskBusy.value.backfill) hints.push('补处理历史附件')
    if (taskBusy.value.duplicate) hints.push('补齐去重检查')
    if (taskBusy.value.baseAnalysis) hints.push('补齐关键信息整理')
    if (taskBusy.value.aiAnalysis) hints.push('补充智能摘要整理')
    if (taskBusy.value.jobIndex) hints.push('补齐岗位整理 / 补充智能岗位识别')
    backendRunningTasks.value.forEach((run) => hints.push(`正在处理：${getTaskTypeLabel(run.task_type || run.taskType)}`))
    return [...new Set(hints)]
  })
  const overviewReady = computed(() => loaded.scheduler && loaded.analysis && loaded.insight && loaded.jobs && loaded.duplicate && recentTaskState.value.recentTaskLoaded)
  const healthState = computed(() => buildAdminHealthState({
    overviewReady: overviewReady.value,
    schedulerEnabled: forms.scheduler.enabled,
    latestFailedTask: recentTaskState.value.latestFailedTask,
    latestSuccessTask: recentTaskState.value.latestSuccessTask,
    analysisRuntime: analysisRuntime.value,
    analysisOverview: analysisOverview.value,
    insightOverview: insightOverview.value,
    jobsOverview: jobsOverview.value
  }))
  const dataProcessingPanels = computed(() => buildDataProcessingPanels({
    sourceOptions: sourceOptions.value,
    taskRuns: state.taskRuns,
    analysisOverview: analysisOverview.value,
    insightOverview: insightOverview.value,
    jobsOverview: jobsOverview.value,
    duplicateOverview: duplicateOverview.value,
    duplicateLatestCheckedAt: duplicateLatestCheckedAt.value,
    analysisLatestAnalyzedAt: analysisLatestAnalyzedAt.value,
    insightLatestAnalyzedAt: insightLatestAnalyzedAt.value,
    jobLatestExtractedAt: jobLatestExtractedAt.value
  }))
  const aiEnhancementPanels = computed(() => buildAiEnhancementPanels({
    openaiReady: openaiReady.value,
    disabledReason: openaiUnavailableReason.value,
    analysisRuntime: analysisRuntime.value,
    analysisOverview: analysisOverview.value,
    jobsOverview: jobsOverview.value,
    taskRuns: state.taskRuns
  }))
  const overviewSection = computed(() => buildOverviewSectionModel({
    health: healthState.value,
    refreshing: loading.overview,
    runtimeCopy: runtimeCopy.value,
    schedulerLoaded: loaded.scheduler,
    schedulerForm: forms.scheduler,
    jobsLoaded: loaded.jobs,
    jobsOverview: jobsOverview.value,
    recentTaskState: recentTaskState.value,
    analysisLoaded: loaded.analysis,
    analysisOverview: analysisOverview.value,
    insightLoaded: loaded.insight,
    insightOverview: insightOverview.value,
    structureRefreshing: loading.insight
  }))
  const dataProcessingSection = computed(() => buildDataProcessingSectionModel({
    panels: dataProcessingPanels.value,
    sourceOptions: sourceOptions.value,
    jobsSummaryUnavailable: state.jobsSummaryUnavailable,
    forms,
    busy: taskBusy.value,
    loading,
    runScrapeTask: dataService.runScrapeTask,
    runBackfillTask: dataService.runBackfillTask,
    runDuplicateBackfillTask: dataService.runDuplicateBackfillTask,
    runBaseAnalysisTask: dataService.runBaseAnalysisTask,
    runJobIndexTask: dataService.runJobIndexTask,
    refreshDuplicateSummary: dataService.refreshDuplicateSummary,
    refreshAnalysisSummary: dataService.refreshAnalysisSummary,
    refreshJobSummary: dataService.refreshJobSummary
  }))
  const aiEnhancementSection = computed(() => buildAiEnhancementSectionModel({
    runtimeCopy: runtimeCopy.value,
    openaiReady: openaiReady.value,
    disabledReason: openaiUnavailableReason.value,
    jobsBlockedReason: aiJobBlockedReason.value,
    panels: aiEnhancementPanels.value,
    sourceOptions: sourceOptions.value,
    forms: { analysis: forms.aiAnalysis, jobs: forms.aiJob },
    busy: { analysis: taskBusy.value.aiAnalysis, jobs: taskBusy.value.jobIndex },
    loading: { analysis: loading.analysis, jobs: loading.jobs },
    jobsSummaryUnavailable: state.jobsSummaryUnavailable,
    latestLabels: { analysis: formatAdminDateTime(analysisLatestAnalyzedAt.value), jobs: formatAdminDateTime(jobLatestExtractedAt.value) },
    runAiAnalysisTask: dataService.runAiAnalysisTask,
    runAiJobExtractionTask: dataService.runAiJobExtractionTask,
    refreshAnalysisSummary: dataService.refreshAnalysisSummary,
    refreshJobSummary: dataService.refreshJobSummary
  }))
  const processingSection = computed(() => buildProcessingSectionModel({
    mode: processingMode.value,
    tabOptions: ADMIN_PROCESSING_TAB_OPTIONS,
    baseSection: dataProcessingSection.value,
    aiSection: aiEnhancementSection.value
  }))
  const systemSection = computed(() => buildSystemSectionModel({ schedulerForm: forms.scheduler, schedulerLoaded: loaded.scheduler, schedulerLoading: loading.scheduler, schedulerSaving: loading.schedulerSaving, sourceOptions: sourceOptions.value }))
  const taskRunsSection = computed(() => buildTaskRunsSectionModel({ taskRuns: state.taskRuns, taskRunsLoaded: loaded.taskRuns, loadingRuns: loading.taskRuns, retryingTaskId: state.retryingTaskId, retryingTaskActionKey: state.retryingTaskActionKey, cancelingTaskId: state.cancelingTaskId, expandedTaskIds: state.expandedTaskIds, nowTs: state.nowTs, sourceOptions: sourceOptions.value, heartbeatStaleMs: TASK_HEARTBEAT_STALE_MS }))

  const setActiveSection = (value) => {
    const normalizedValue = normalizeAdminSection(value)
    activeAdminSection.value = normalizedValue
    if (value === 'ai-enhancement') {
      processingMode.value = 'ai'
    }
  }
  const setProcessingMode = (value) => {
    processingMode.value = normalizeProcessingMode(value)
  }

  onMounted(async () => {
    state.pollingTimerId = window.setInterval(async () => {
      state.nowTs = Date.now()
      if (!adminAuthorized.value || backendRunningTasks.value.length === 0 || state.pollingInFlight) return
      state.pollingInFlight = true
      try { await dataService.refreshTaskStatus() } finally { state.pollingInFlight = false }
    }, TASK_POLL_INTERVAL_MS)

    const authorized = await dataService.verifyAdminAccess()
    if (!authorized) return
    await dataService.fetchSources()
    await dataService.refreshOverview()
  })
  onUnmounted(() => { if (state.pollingTimerId) window.clearInterval(state.pollingTimerId) })

  return {
    adminAuthorized,
    adminAuthChecking,
    adminAuthError,
    adminAuthForm,
    adminSavedUsername,
    activeAdminSection,
    adminSectionOptions: ADMIN_SECTION_OPTIONS,
    feedback,
    feedbackClass,
    activeTaskHints,
    setActiveSection,
    setProcessingMode,
    overviewSection,
    processingSection,
    dataProcessingSection,
    aiEnhancementSection,
    systemSection,
    taskRunsSection,
    canRetryTask,
    ...dataService
  }
}
