const EMPTY_TASK_STATE = Object.freeze({
  latestSuccessTask: null,
  latestFailedTask: null,
  recentTaskLoaded: false,
  isDegraded: false,
  fallbackNotice: ''
})

const getRunTime = (run) => {
  const timestamp = run?.finishedAt || run?.startedAt
  if (!timestamp) return Number.NEGATIVE_INFINITY
  const value = new Date(timestamp).getTime()
  return Number.isFinite(value) ? value : Number.NEGATIVE_INFINITY
}

export const normalizeTaskRun = (run) => {
  if (!run) return null

  return {
    id: run.id || '',
    taskType: run.task_type || run.taskType || '',
    status: run.status || '',
    summary: run.summary || '',
    startedAt: run.started_at || run.startedAt || '',
    finishedAt: run.finished_at || run.finishedAt || run.last_success_at || run.lastSuccessAt || run.started_at || run.startedAt || '',
    failureReason: run.failure_reason || run.error || run.details?.failure_reason || run.details?.error || ''
  }
}

const findLatestTask = (taskRuns = [], status) => {
  return taskRuns
    .map(normalizeTaskRun)
    .filter((run) => run && run.status === status)
    .sort((left, right) => getRunTime(right) - getRunTime(left))[0] || null
}

export function buildRecentTaskState({
  taskSummary = null,
  taskSummaryLoaded = false,
  taskSummaryUnavailable = false,
  taskRuns = [],
  taskRunsLoaded = false
} = {}) {
  const latestSuccessFromSummary = normalizeTaskRun(
    taskSummary?.latest_success_run
    || taskSummary?.latest_success_task
    || taskSummary?.latest_success
    || taskSummary?.last_success
  )
  const latestSuccessFromRuns = findLatestTask(taskRuns, 'success')
  const latestFailedTask = findLatestTask(taskRuns, 'failed')
  const isDegraded = Boolean(taskSummaryUnavailable && taskRunsLoaded)
  const recentTaskLoaded = Boolean(taskSummaryLoaded || isDegraded)

  if (!recentTaskLoaded) {
    return EMPTY_TASK_STATE
  }

  return {
    latestSuccessTask: latestSuccessFromSummary || latestSuccessFromRuns,
    latestFailedTask,
    recentTaskLoaded: true,
    isDegraded,
    fallbackNotice: isDegraded ? '任务摘要接口不可用，已回退到最近任务记录。' : ''
  }
}
