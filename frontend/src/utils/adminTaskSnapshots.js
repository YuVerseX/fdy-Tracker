const TASK_STATUS_ALIASES = Object.freeze({
  pending: 'queued',
  processing: 'running'
})

const TASK_SNAPSHOT_META = Object.freeze({
  trusted: Object.freeze({
    label: '当前实例归档结果',
    tone: 'neutral',
    summary: '当前实例已归档的任务结果快照',
    detail: '当前无活跃任务时，只会在手动刷新后更新这些结果。'
  }),
  degraded: Object.freeze({
    label: '包含降级快照',
    tone: 'warning',
    summary: '这是当前实例根据过期心跳自动归档的降级任务快照',
    detail: '该任务因心跳过期被当前实例自动归档，最终状态基于超时推断。'
  }),
  instance_local: Object.freeze({
    label: '当前实例本地快照',
    tone: 'info',
    summary: '仅反映当前实例看到的后台任务状态快照',
    detail: '运行态来自当前实例的本地 JSON 心跳快照，跨实例不可见，不保证强一致实时性。'
  })
})

const getNormalizedText = (value) => String(value ?? '').trim()

const getTaskSnapshotField = (run = {}, key) => {
  const topLevelValue = getNormalizedText(run?.[key])
  if (topLevelValue) return topLevelValue
  const detailValue = getNormalizedText(run?.details?.[key])
  return detailValue || ''
}

export function getAdminTaskParam(run = {}, ...keys) {
  const sources = [
    run?.params,
    run?.details?.params,
    run?.details?.request_params,
    run?.details?.requestParams,
    run
  ]
  for (const source of sources) {
    if (!source || typeof source !== 'object') continue
    for (const key of keys) {
      if (source[key] !== undefined && source[key] !== null && source[key] !== '') {
        return source[key]
      }
    }
  }
  return null
}

const normalizeTaskSnapshotDetails = (run = {}, details = {}) => {
  const normalizedStatus = normalizeAdminTaskStatus(run?.status)
  return {
    ...details,
    status: normalizedStatus || getNormalizedText(details.status),
    snapshot_at: getTaskSnapshotField(run, 'snapshot_at'),
    trust_level: getTaskSnapshotField(run, 'trust_level'),
    degraded_reason: getTaskSnapshotField(run, 'degraded_reason'),
    instance_scope: getTaskSnapshotField(run, 'instance_scope'),
    scope_summary: getTaskSnapshotField(run, 'scope_summary')
  }
}

const collectTaskSnapshotRuns = ({ taskRuns = [], taskSummary = null } = {}) => {
  const items = [
    ...(Array.isArray(taskRuns) ? taskRuns : []),
    ...(Array.isArray(taskSummary?.running_tasks) ? taskSummary.running_tasks : []),
    taskSummary?.latest_task_run,
    taskSummary?.latest_success_run
  ]
  return items
    .filter((item) => item && typeof item === 'object')
    .map((item) => normalizeAdminTaskSnapshot(item))
}

export function normalizeAdminTaskStatus(status) {
  const normalizedStatus = getNormalizedText(status).toLowerCase()
  if (!normalizedStatus) return ''
  return TASK_STATUS_ALIASES[normalizedStatus] || normalizedStatus
}

export function normalizeAdminTaskSnapshot(run = {}) {
  if (!run || typeof run !== 'object') return run

  const details = run?.details && typeof run.details === 'object'
    ? { ...run.details }
    : {}
  const normalizedStatus = normalizeAdminTaskStatus(run.status)

  return {
    ...run,
    status: normalizedStatus || getNormalizedText(run.status),
    snapshot_at: getTaskSnapshotField(run, 'snapshot_at'),
    trust_level: getTaskSnapshotField(run, 'trust_level'),
    degraded_reason: getTaskSnapshotField(run, 'degraded_reason'),
    instance_scope: getTaskSnapshotField(run, 'instance_scope'),
    scope_summary: getTaskSnapshotField(run, 'scope_summary'),
    details: normalizeTaskSnapshotDetails(run, details)
  }
}

export function normalizeAdminTaskSummary(summary = {}) {
  if (!summary || typeof summary !== 'object') return summary

  return {
    ...summary,
    latest_task_run: normalizeAdminTaskSnapshot(summary.latest_task_run || summary.latestTaskRun || null),
    latest_success_run: normalizeAdminTaskSnapshot(summary.latest_success_run || summary.latestSuccessRun || null),
    running_tasks: Array.isArray(summary.running_tasks)
      ? summary.running_tasks.map((run) => normalizeAdminTaskSnapshot(run))
      : []
  }
}

export function getTaskSnapshotTrust(run = {}) {
  const trustLevel = getTaskSnapshotField(run, 'trust_level')
  return TASK_SNAPSHOT_META[trustLevel] ? trustLevel : 'trusted'
}

export function getTaskSnapshotLabel(run = {}) {
  return TASK_SNAPSHOT_META[getTaskSnapshotTrust(run)].label
}

export function getTaskSnapshotTone(run = {}) {
  return TASK_SNAPSHOT_META[getTaskSnapshotTrust(run)].tone
}

export function getTaskSnapshotSummary(run = {}) {
  return getTaskSnapshotField(run, 'scope_summary') || TASK_SNAPSHOT_META[getTaskSnapshotTrust(run)].summary
}

export function getTaskSnapshotDetail(run = {}) {
  return getTaskSnapshotField(run, 'degraded_reason') || TASK_SNAPSHOT_META[getTaskSnapshotTrust(run)].detail
}

export function getTaskSnapshotAt(run = {}) {
  return getTaskSnapshotField(run, 'snapshot_at')
}

export function summarizeTaskSnapshotScope({ taskRuns = [], taskSummary = null } = {}) {
  const normalizedRuns = collectTaskSnapshotRuns({ taskRuns, taskSummary })
  const prioritizedRun = (
    normalizedRuns.find((run) => getTaskSnapshotTrust(run) === 'instance_local')
    || normalizedRuns.find((run) => getTaskSnapshotTrust(run) === 'degraded')
    || normalizedRuns.find((run) => getTaskSnapshotTrust(run) === 'trusted')
    || null
  )

  if (!prioritizedRun) {
    return {
      label: '任务快照未同步',
      tone: 'neutral',
      summary: '任务状态快照尚未同步。',
      detail: ''
    }
  }

  return {
    label: getTaskSnapshotLabel(prioritizedRun),
    tone: getTaskSnapshotTone(prioritizedRun),
    summary: getTaskSnapshotSummary(prioritizedRun),
    detail: getTaskSnapshotDetail(prioritizedRun)
  }
}
