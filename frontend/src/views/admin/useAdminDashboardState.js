import { computed, onMounted, onUnmounted, proxyRefs, reactive, ref } from 'vue'

import { adminApi } from '../../api/posts.js'
import { ADMIN_SECTION_LEGACY_ALIASES, ADMIN_SECTION_OPTIONS, getAdminRuntimeCopy } from '../../utils/adminDashboardMeta.js'
import { buildAiEnhancementPanels, buildDataProcessingPanels, formatAdminDateTime, getTaskTypeLabel } from '../../utils/adminDashboardViewModels.js'
import { createAdminDashboardDataService } from './adminDashboardDataService.js'
import { buildAdminHealthState } from './adminDashboardHealth.js'
import {
  buildAiEnhancementSectionModel,
  buildDataProcessingSectionModel,
  buildOverviewSectionModel,
  buildSystemSectionModel,
  buildTaskRunsSectionModel
} from './adminDashboardSectionAdapters.js'
import { canRetryTask } from './adminDashboardTaskActions.js'
import { buildRecentTaskState } from './adminDashboardTaskSummary.js'

const TASK_HEARTBEAT_STALE_MS = 10 * 60 * 1000
const TASK_POLL_INTERVAL_MS = 15 * 1000

export const normalizeAdminDashboardBindings = (bindings) => proxyRefs(bindings)

export function useAdminDashboardState() {
  const adminAuthorized = ref(false)
  const adminAuthChecking = ref(false)
  const adminAuthError = ref('')
  const adminAuthForm = reactive({ username: '', password: '' })
  const activeAdminSection = ref(ADMIN_SECTION_OPTIONS[0].value)
  const feedback = ref({ type: '', message: '' })
  const sourceOptions = ref([{ label: '江苏省人社厅（source_id=1）', value: 1, isActive: true }])
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
    if (!loaded.analysis || !analysisRuntime.value) return 'AI 增强当前不可用，基础模式仍可继续补齐。'
    if (!analysisRuntime.value.analysis_enabled) return 'AI 增强当前不可用，AI 增强开关还没有开启，基础模式仍可继续补齐。'
    if (!analysisRuntime.value.openai_configured) return 'AI 增强当前不可用，后端还没配置 OPENAI_API_KEY。'
    if (!analysisRuntime.value.openai_sdk_available) return 'AI 增强当前不可用，当前运行环境里还没装 openai SDK。'
    return 'AI 增强当前不可用，基础模式仍可继续补齐。'
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
    if (taskBusy.value.baseAnalysis) hints.push('补齐基础分析')
    if (taskBusy.value.aiAnalysis) hints.push('启动 AI 增强分析')
    if (taskBusy.value.jobIndex) hints.push('补齐岗位索引 / AI 岗位补抽')
    backendRunningTasks.value.forEach((run) => hints.push(`后台执行：${getTaskTypeLabel(run.task_type || run.taskType)}`))
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
    jobsOverview: jobsOverview.value
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
  const dataProcessingSection = computed(() => buildDataProcessingSectionModel({ panels: dataProcessingPanels.value, sourceOptions: sourceOptions.value, jobsSummaryUnavailable: state.jobsSummaryUnavailable, forms, busy: taskBusy.value, loading }))
  const aiEnhancementSection = computed(() => buildAiEnhancementSectionModel({
    runtimeCopy: runtimeCopy.value,
    openaiReady: openaiReady.value,
    disabledReason: openaiUnavailableReason.value,
    panels: aiEnhancementPanels.value,
    sourceOptions: sourceOptions.value,
    forms: { analysis: forms.aiAnalysis, jobs: forms.aiJob },
    busy: { analysis: taskBusy.value.aiAnalysis, jobs: taskBusy.value.jobIndex },
    loading: { analysis: loading.analysis, jobs: loading.jobs },
    jobsSummaryUnavailable: state.jobsSummaryUnavailable,
    latestLabels: { analysis: formatAdminDateTime(analysisLatestAnalyzedAt.value), jobs: formatAdminDateTime(jobLatestExtractedAt.value) }
  }))
  const systemSection = computed(() => buildSystemSectionModel({ schedulerForm: forms.scheduler, schedulerLoaded: loaded.scheduler, schedulerLoading: loading.scheduler, schedulerSaving: loading.schedulerSaving, sourceOptions: sourceOptions.value }))
  const taskRunsSection = computed(() => buildTaskRunsSectionModel({ taskRuns: state.taskRuns, taskRunsLoaded: loaded.taskRuns, loadingRuns: loading.taskRuns, retryingTaskId: state.retryingTaskId, expandedTaskIds: state.expandedTaskIds, nowTs: state.nowTs, sourceOptions: sourceOptions.value, heartbeatStaleMs: TASK_HEARTBEAT_STALE_MS }))

  const setActiveSection = (value) => { activeAdminSection.value = ADMIN_SECTION_LEGACY_ALIASES[value] || value }

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
    overviewSection,
    dataProcessingSection,
    aiEnhancementSection,
    systemSection,
    taskRunsSection,
    canRetryTask,
    ...dataService
  }
}
