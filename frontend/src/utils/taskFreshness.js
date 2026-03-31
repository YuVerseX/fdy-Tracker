export function normalizeLatestSuccessTask(data) {
  if (!data) return null

  const candidate =
    data.latest_success_run ||
    data.latest_success_task ||
    data.latest_success ||
    data.last_success ||
    data

  const finishedAt =
    candidate?.finished_at ||
    candidate?.finishedAt ||
    candidate?.last_success_at ||
    candidate?.lastSuccessAt ||
    candidate?.latest_success_at ||
    candidate?.latestSuccessAt ||
    data.latest_success_at ||
    data.latestSuccessAt

  if (!finishedAt) return null

  return {
    taskType: candidate?.task_type || candidate?.taskType || '',
    taskLabel: candidate?.task_label || candidate?.taskLabel || '',
    finishedAt
  }
}
