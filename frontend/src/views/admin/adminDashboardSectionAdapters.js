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
        label: '运行模式',
        value: runtimeCopy?.badge || LOADING_LABEL,
        meta: [runtimeCopy?.description || '', runtimeCopy?.emphasis || '']
      },
      {
        id: 'jobs',
        label: '岗位索引',
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
      { label: '基础分析完成', value: showCount(analysisLoaded, analysisOverview?.base_ready_posts ?? analysisOverview?.analyzed_posts) },
      { label: '结构化字段完成', value: showCount(insightLoaded, insightOverview?.insight_posts) },
      { label: 'AI 分析覆盖率', value: analysisLoaded ? formatAdminPercent(analysisOverview?.openai_analyzed_posts, analysisOverview?.total_posts) : LOADING_LABEL },
      { label: 'AI 岗位补抽覆盖率', value: jobsLoaded ? formatAdminPercent(jobsOverview?.ai_job_posts, jobsOverview?.posts_with_jobs) : LOADING_LABEL }
    ],
    structureRefreshLabel: structureRefreshing ? '刷新中...' : '刷新结构化字段'
  }
}

export const buildDataProcessingSectionModel = ({
  panels,
  sourceOptions,
  jobsSummaryUnavailable,
  forms,
  busy,
  loading
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
  jobsLoading: loading?.jobs
})

export const buildAiEnhancementSectionModel = ({
  runtimeCopy,
  openaiReady,
  disabledReason,
  panels,
  sourceOptions,
  forms,
  busy,
  loading,
  jobsSummaryUnavailable,
  latestLabels
} = {}) => ({
  runtimeCopy,
  openaiReady,
  disabledReason,
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
  latestJobsLabel: latestLabels?.jobs
})

export function buildSystemSectionModel({
  schedulerForm,
  schedulerLoaded,
  schedulerLoading,
  schedulerSaving,
  sourceOptions
} = {}) {
  const noticeClass = schedulerLoaded
    ? (schedulerForm?.enabled ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-gray-200 bg-gray-50 text-gray-700')
    : 'border-slate-200 bg-slate-50 text-slate-700'

  return {
    schedulerForm,
    schedulerLoaded,
    schedulerLoading,
    schedulerSaving,
    sourceOptions,
    noticeClass,
    statusLine: `当前状态：${showBoolean(schedulerLoaded, schedulerForm?.enabled, '已启用定时抓取', '已停用定时抓取')}；间隔 ${schedulerLoaded ? formatAdminInterval(schedulerForm?.intervalSeconds) : LOADING_LABEL}；默认抓 ${showCount(schedulerLoaded, schedulerForm?.defaultMaxPages)} 页。`,
    nextRunLine: `下次预计运行：${showText(schedulerLoaded, schedulerForm?.nextRunAt ? formatAdminDateTime(schedulerForm.nextRunAt) : '', NOT_FETCHED_LABEL)}`
  }
}

export const buildTaskRunsSectionModel = ({
  taskRuns,
  taskRunsLoaded,
  loadingRuns,
  retryingTaskId,
  expandedTaskIds,
  nowTs,
  sourceOptions,
  heartbeatStaleMs
} = {}) => ({
  taskRuns,
  taskRunsLoaded,
  loadingRuns,
  retryingTaskId,
  expandedTaskIds,
  nowTs,
  sourceOptions,
  heartbeatStaleMs
})
