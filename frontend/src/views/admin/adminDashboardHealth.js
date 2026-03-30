import { getAdminRuntimeMode } from '../../utils/adminDashboardMeta.js'
import { getTaskTypeLabel } from '../../utils/adminDashboardViewModels.js'

const STATUS_COPY = {
  unknown: {
    label: '加载中',
    panelClass: 'border-slate-200 bg-slate-100/80',
    badgeClass: 'bg-slate-200 text-slate-700',
    textClass: 'text-slate-700'
  },
  warning: {
    label: '需处理',
    panelClass: 'border-red-200 bg-red-50/80',
    badgeClass: 'bg-red-100 text-red-700',
    textClass: 'text-red-700'
  },
  attention: {
    label: '需关注',
    panelClass: 'border-amber-200 bg-amber-50/80',
    badgeClass: 'bg-amber-100 text-amber-800',
    textClass: 'text-amber-800'
  },
  healthy: {
    label: '正常',
    panelClass: 'border-emerald-200 bg-emerald-50/80',
    badgeClass: 'bg-emerald-100 text-emerald-700',
    textClass: 'text-emerald-800'
  }
}

const getCount = (value) => {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : 0
}

const hasFreshFailure = (latestFailedTask, latestSuccessTask) => {
  const failedAt = latestFailedTask?.finishedAt ? new Date(latestFailedTask.finishedAt).getTime() : Number.NEGATIVE_INFINITY
  const successAt = latestSuccessTask?.finishedAt ? new Date(latestSuccessTask.finishedAt).getTime() : Number.NEGATIVE_INFINITY
  return Number.isFinite(failedAt) && failedAt > successAt
}

const buildSummary = ({ level, runtimeMode, hasBaseBacklog, hasAiBacklog }) => {
  if (level === 'unknown') return '总览数据加载中，稍后再显示真实健康状态。'
  if (level === 'warning') return '当前有会影响持续更新的项，建议优先处理。'
  if (runtimeMode === 'disabled') return 'AI 增强当前未开启，基础处理链路仍可继续推进。'
  if (hasBaseBacklog) return '系统能跑，但基础处理链路还有积压需要处理。'
  if (hasAiBacklog) return '基础处理已就绪，但 AI 增强还有待处理积压。'
  if (runtimeMode === 'basic') return '基础处理链路正常，当前运行在基础模式。'
  return '抓取、分析和岗位索引都在正常状态。'
}

export function buildAdminHealthState({
  overviewReady = false,
  schedulerEnabled = false,
  latestFailedTask = null,
  latestSuccessTask = null,
  analysisRuntime = null,
  analysisOverview = null,
  insightOverview = null,
  jobsOverview = null
} = {}) {
  const runtimeMode = getAdminRuntimeMode(analysisRuntime)
  const hasBaseBacklog = getCount(analysisOverview?.base_pending_posts) > 0
    || getCount(insightOverview?.pending_insight_posts) > 0
    || getCount(jobsOverview?.pending_posts) > 0
  const shouldTrackAiBacklog = runtimeMode === 'ai_enhanced'
  const hasAiBacklog = shouldTrackAiBacklog && getCount(analysisOverview?.openai_pending_posts) > 0
  const latestFailureIsFresh = hasFreshFailure(latestFailedTask, latestSuccessTask)

  let level = 'healthy'
  if (!overviewReady) level = 'unknown'
  else if (!schedulerEnabled || latestFailureIsFresh) level = 'warning'
  else if (hasBaseBacklog || hasAiBacklog) level = 'attention'

  const alerts = []
  if (overviewReady && !schedulerEnabled) {
    alerts.push('定时抓取现在是关闭的，前台不会自动更新。')
  }
  if (overviewReady && latestFailedTask) {
    const detail = latestFailedTask.summary || latestFailedTask.failureReason || '请检查后台日志。'
    alerts.push(`最近失败任务：${getTaskTypeLabel(latestFailedTask.taskType)}。${detail}`)
  }
  if (overviewReady && getCount(analysisOverview?.base_pending_posts) > 0) {
    alerts.push(`还有 ${analysisOverview?.base_pending_posts} 条帖子待补齐基础分析。`)
  }
  if (overviewReady && getCount(insightOverview?.pending_insight_posts) > 0) {
    alerts.push(`还有 ${insightOverview?.pending_insight_posts} 条帖子待补齐结构化字段。`)
  }
  if (overviewReady && shouldTrackAiBacklog && getCount(analysisOverview?.openai_pending_posts) > 0) {
    alerts.push(`还有 ${analysisOverview?.openai_pending_posts} 条帖子待 AI 增强分析。`)
  }
  if (overviewReady && getCount(jobsOverview?.pending_posts) > 0) {
    alerts.push(`还有 ${jobsOverview?.pending_posts} 条帖子待补齐岗位索引。`)
  }

  return {
    level,
    ...STATUS_COPY[level],
    summary: buildSummary({ level, runtimeMode, hasBaseBacklog, hasAiBacklog }),
    alerts
  }
}
