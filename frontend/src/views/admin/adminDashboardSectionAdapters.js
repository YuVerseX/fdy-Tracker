import {
  formatAdminDateTime,
  formatAdminInterval,
  formatAdminPercent,
  getTaskTypeLabel
} from '../../utils/adminDashboardViewModels.js'

const EMPTY_LABEL = '--'
const LOADING_LABEL = '加载中'
const NOT_FETCHED_LABEL = '未获取'

const showCount = (loaded, value, suffix = '') => {
  if (!loaded) return LOADING_LABEL
  const normalized = Number(value)
  return Number.isFinite(normalized) ? `${normalized}${suffix}` : EMPTY_LABEL
}

const showText = (loaded, value, empty = EMPTY_LABEL) => {
  if (!loaded) return LOADING_LABEL
  const normalized = String(value ?? '').trim()
  return normalized || empty
}

const showBoolean = (loaded, value, truthy, falsy) => {
  if (!loaded) return LOADING_LABEL
  return value ? truthy : falsy
}

const getRelativeTimeLabel = (value) => {
  if (!value) return EMPTY_LABEL
  const diffMs = Date.now() - new Date(value).getTime()
  if (diffMs < 60_000) return '刚刚'
  if (diffMs < 3_600_000) return `${Math.floor(diffMs / 60_000)} 分钟前`
  if (diffMs < 86_400_000) return `${Math.floor(diffMs / 3_600_000)} 小时前`
  if (diffMs < 604_800_000) return `${Math.floor(diffMs / 86_400_000)} 天前`
  return formatAdminDateTime(value)
}

const getPanel = (panels = [], panelId) => panels.find((panel) => panel.id === panelId) || { stats: [] }
const getSourceLabel = (sourceOptions = [], sourceId) => {
  const matched = sourceOptions.find((source) => Number(source.value) === Number(sourceId))
  return matched?.label || '默认数据源'
}
const buildOverviewFocusItems = ({ health, runtimeCopy, recentTaskState } = {}) => {
  const latestSuccessTask = recentTaskState?.latestSuccessTask
  const latestSuccessLabel = latestSuccessTask ? getTaskTypeLabel(latestSuccessTask.taskType) : ''
  const primaryDescription = health?.alerts?.[0]
    || recentTaskState?.fallbackNotice
    || (latestSuccessLabel
      ? `最近任务是 ${latestSuccessLabel}，当前主链路稳定，可以继续查看处理任务或任务中心。`
      : '先运行一次任务后，这里会给出下一步建议。')

  return [
    {
      id: 'next-step',
      title: '接下来优先处理',
      description: primaryDescription
    },
    {
      id: 'latest-result',
      title: '最近完成情况',
      description: latestSuccessLabel
        ? `${latestSuccessLabel} 已完成，可以继续查看任务中心了解细节。`
        : '当前还没有最近完成记录。'
    },
    {
      id: 'runtime',
      title: '当前处理能力',
      description: runtimeCopy?.emphasis || '当前能力信息正在更新。'
    }
  ]
}

export function buildOverviewSectionModel({
  health,
  refreshing,
  runtimeCopy,
  schedulerLoaded,
  schedulerForm,
  jobsLoaded,
  jobsOverview,
  recentTaskState,
  analysisLoaded,
  analysisOverview,
  insightLoaded,
  insightOverview,
  structureRefreshing
} = {}) {
  const latestSuccessTask = recentTaskState?.latestSuccessTask
  const latestFailedTask = recentTaskState?.latestFailedTask

  return {
    health,
    refreshing,
    runtimeCopy,
    focusItems: buildOverviewFocusItems({ health, runtimeCopy, recentTaskState }),
    cards: [
      {
        id: 'scheduler',
        label: '定时抓取',
        value: showBoolean(schedulerLoaded, schedulerForm?.enabled, '已启用', '已关闭'),
        meta: [
          `间隔 ${schedulerLoaded ? formatAdminInterval(schedulerForm?.intervalSeconds) : LOADING_LABEL}`,
          schedulerLoaded
            ? `下次 ${schedulerForm?.nextRunAt ? formatAdminDateTime(schedulerForm.nextRunAt) : NOT_FETCHED_LABEL}`
            : '下次 加载中'
        ]
      },
      {
        id: 'runtime',
        label: '当前能力',
        value: runtimeCopy?.badge || LOADING_LABEL,
        meta: [runtimeCopy?.description || '', runtimeCopy?.emphasis || '']
      },
      {
        id: 'jobs',
        label: '岗位整理',
        value: jobsLoaded ? `${showCount(true, jobsOverview?.total_jobs)} 个岗位` : LOADING_LABEL,
        meta: [
          `含岗位帖子 ${showCount(jobsLoaded, jobsOverview?.posts_with_jobs)} 条`,
          `待补齐 ${showCount(jobsLoaded, jobsOverview?.pending_posts)} 条`
        ]
      },
      {
        id: 'recent-task',
        label: '最近任务',
        value: recentTaskState?.recentTaskLoaded
          ? (latestSuccessTask ? getTaskTypeLabel(latestSuccessTask.taskType) : '还没有成功记录')
          : LOADING_LABEL,
        meta: [
          recentTaskState?.recentTaskLoaded
            ? (latestSuccessTask?.finishedAt
                ? `${formatAdminDateTime(latestSuccessTask.finishedAt)}（${getRelativeTimeLabel(latestSuccessTask.finishedAt)}）`
                : '先跑一次任务后再看这里')
            : '最近任务信息加载中',
          recentTaskState?.fallbackNotice || '',
          latestFailedTask?.finishedAt
            ? `最近失败：${getTaskTypeLabel(latestFailedTask.taskType)}，${getRelativeTimeLabel(latestFailedTask.finishedAt)}`
            : ''
        ].filter(Boolean)
      }
    ],
    structuredFieldCards: [
      { label: '关键信息整理完成', value: showCount(analysisLoaded, analysisOverview?.base_ready_posts ?? analysisOverview?.analyzed_posts) },
      { label: '关键信息字段完成', value: showCount(insightLoaded, insightOverview?.insight_posts) },
      { label: '智能摘要覆盖率', value: analysisLoaded ? formatAdminPercent(analysisOverview?.openai_analyzed_posts, analysisOverview?.total_posts) : LOADING_LABEL },
      { label: '智能岗位识别覆盖率', value: jobsLoaded ? formatAdminPercent(jobsOverview?.ai_job_posts, jobsOverview?.posts_with_jobs) : LOADING_LABEL }
    ],
    structureRefreshLabel: structureRefreshing ? '刷新中...' : '刷新整理结果'
  }
}

export const buildDataProcessingSectionModel = ({
  panels,
  sourceOptions,
  jobsSummaryUnavailable,
  forms,
  busy,
  loading,
  runScrapeTask,
  runBackfillTask,
  runDuplicateBackfillTask,
  runBaseAnalysisTask,
  runJobIndexTask,
  refreshDuplicateSummary,
  refreshAnalysisSummary,
  refreshJobSummary
} = {}) => ({
  collectPanel: getPanel(panels, 'collect-and-backfill'),
  duplicatePanel: getPanel(panels, 'duplicate-governance'),
  analysisPanel: getPanel(panels, 'content-analysis'),
  jobsPanel: getPanel(panels, 'job-index'),
  sourceOptions,
  jobsSummaryUnavailable,
  scrapeForm: forms?.scrape,
  backfillForm: forms?.backfill,
  duplicateForm: forms?.duplicate,
  baseAnalysisForm: forms?.baseAnalysis,
  jobIndexForm: forms?.jobIndex,
  scrapeBusy: busy?.scrape,
  backfillBusy: busy?.backfill,
  duplicateBusy: busy?.duplicate,
  baseAnalysisBusy: busy?.baseAnalysis,
  jobIndexBusy: busy?.jobIndex,
  duplicateLoading: loading?.duplicate,
  analysisLoading: loading?.analysis,
  jobsLoading: loading?.jobs,
  runScrapeTask,
  runBackfillTask,
  runDuplicateBackfillTask,
  runBaseAnalysisTask,
  runJobIndexTask,
  refreshDuplicateSummary,
  refreshAnalysisSummary,
  refreshJobSummary
})

export const buildAiEnhancementSectionModel = ({
  runtimeCopy,
  openaiReady,
  disabledReason,
  jobsBlockedReason,
  panels,
  sourceOptions,
  forms,
  busy,
  loading,
  jobsSummaryUnavailable,
  latestLabels,
  runAiAnalysisTask,
  runAiJobExtractionTask,
  refreshAnalysisSummary,
  refreshJobSummary
} = {}) => ({
  runtimeCopy,
  openaiReady,
  disabledReason,
  jobsBlockedReason,
  panels,
  sourceOptions,
  analysisForm: forms?.analysis,
  jobsForm: forms?.jobs,
  analysisBusy: busy?.analysis,
  jobsBusy: busy?.jobs,
  analysisLoading: loading?.analysis,
  jobsLoading: loading?.jobs,
  jobsSummaryUnavailable,
  latestAnalysisLabel: latestLabels?.analysis,
  latestJobsLabel: latestLabels?.jobs,
  runAiAnalysisTask,
  runAiJobExtractionTask,
  refreshAnalysisSummary,
  refreshJobSummary
})

export const buildProcessingSectionModel = ({
  mode = 'base',
  tabOptions = [],
  baseSection = {},
  aiSection = {}
} = {}) => ({
  mode,
  tabOptions,
  baseSection,
  aiSection
})

export function buildSystemSectionModel({
  schedulerForm,
  schedulerLoaded,
  schedulerLoading,
  schedulerSaving,
  schedulerConfigError,
  sourceOptions,
  analysisRuntime
} = {}) {
  const hasSchedulerSnapshot = schedulerLoaded
  const hasRuntimeSnapshot = Boolean(analysisRuntime)
  const saveBlockedReason = hasSchedulerSnapshot || schedulerLoading
    ? ''
    : `${schedulerConfigError || '定时抓取配置尚未成功加载'}，请先刷新配置后再保存。`
  const saveDisabled = schedulerSaving || (!hasSchedulerSnapshot && schedulerLoading) || Boolean(saveBlockedReason)
  const schedulerRefreshNotice = hasSchedulerSnapshot && schedulerConfigError
    ? {
        tone: 'warning',
        title: '配置刷新失败',
        description: `${schedulerConfigError}，当前仍显示上次成功加载的配置，你可以继续保存或稍后重试刷新。`
      }
    : null
  const noticeClass = schedulerLoaded
    ? (schedulerForm?.enabled ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-gray-200 bg-gray-50 text-gray-700')
    : 'border-slate-200 bg-slate-50 text-slate-700'

  const statusBadgeLabel = showBoolean(schedulerLoaded, schedulerForm?.enabled, '自动抓取已启用', '自动抓取已关闭')
  const summaryCards = [
    {
      label: '当前状态',
      value: showBoolean(schedulerLoaded, schedulerForm?.enabled, '已启用', '已关闭'),
      meta: schedulerLoaded ? `间隔 ${formatAdminInterval(schedulerForm?.intervalSeconds)}` : LOADING_LABEL
    },
    {
      label: '下次运行',
      value: showText(
        schedulerLoaded,
        schedulerForm?.nextRunAt ? formatAdminDateTime(schedulerForm.nextRunAt) : '',
        NOT_FETCHED_LABEL
      ),
      meta: schedulerLoaded ? '如需立即处理，可直接去“处理任务”手动运行。' : LOADING_LABEL
    },
    {
      label: '默认范围',
      value: schedulerLoaded
        ? `${getSourceLabel(sourceOptions, schedulerForm?.defaultSourceId)} · ${showCount(true, schedulerForm?.defaultMaxPages)} 页`
        : LOADING_LABEL,
      meta: '新的默认设置会用于后续自动抓取。'
    }
  ]
  if (hasRuntimeSnapshot) {
    summaryCards.push(
      {
        label: '代理状态',
        value: showBoolean(true, analysisRuntime?.proxy_enabled, '已启用', '未启用'),
        meta: '当前应用级出站代理状态。'
      },
      {
        label: '代理出口',
        value: analysisRuntime?.proxy_enabled
          ? [analysisRuntime?.proxy_scheme, analysisRuntime?.proxy_display].filter(Boolean).join(' · ')
          : '未启用应用级代理',
        meta: '抓取与智能链路统一复用该出口。'
      }
    )
  }
  const runtimeFacts = []
  if (hasRuntimeSnapshot && analysisRuntime?.proxy_scope) {
    runtimeFacts.push({
      label: '代理范围',
      value: analysisRuntime.proxy_scope
    })
  }
  const helperNotice = {
    tone: schedulerForm?.enabled ? 'info' : 'warning',
    description: schedulerForm?.enabled
      ? '保存后会在下一次自动抓取时生效；手动运行任务不受影响。'
      : '当前已关闭自动抓取；保存后会更新后台设置，手动运行任务不受影响。'
  }

  return {
    schedulerForm,
    schedulerLoaded,
    schedulerLoading,
    schedulerSaving,
    saveDisabled,
    saveBlockedReason,
    schedulerRefreshNotice,
    sourceOptions,
    noticeClass,
    statusBadgeLabel,
    summaryCards,
    runtimeFacts,
    helperNotice,
    statusLine: `当前状态：${showBoolean(schedulerLoaded, schedulerForm?.enabled, '已启用定时抓取', '已停用定时抓取')}；间隔 ${schedulerLoaded ? formatAdminInterval(schedulerForm?.intervalSeconds) : LOADING_LABEL}；默认抓 ${showCount(schedulerLoaded, schedulerForm?.defaultMaxPages)} 页。`,
    nextRunLine: `下次预计运行：${showText(schedulerLoaded, schedulerForm?.nextRunAt ? formatAdminDateTime(schedulerForm.nextRunAt) : '', NOT_FETCHED_LABEL)}`
  }
}

export const buildTaskRunsSectionModel = ({
  taskRuns,
  taskRunsError,
  taskRunsLoaded,
  loadingRuns,
  retryingTaskId,
  retryingTaskActionKey,
  cancelingTaskId,
  expandedTaskIds,
  nowTs,
  sourceOptions,
  heartbeatStaleMs,
  syncStatus
} = {}) => ({
  taskRuns,
  taskRunsError,
  taskRunsLoaded,
  loadingRuns,
  retryingTaskId,
  retryingTaskActionKey,
  cancelingTaskId,
  expandedTaskIds,
  nowTs,
  sourceOptions,
  heartbeatStaleMs,
  syncStatus
})
