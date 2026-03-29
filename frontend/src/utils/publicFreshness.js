export function getPublicFreshnessHeadline(task) {
  if (!task?.finishedAt) {
    return '还没有可展示的抓取成功任务记录。'
  }

  return `最近抓取成功任务：${task.taskLabel || task.taskType || '抓取任务'}`
}
