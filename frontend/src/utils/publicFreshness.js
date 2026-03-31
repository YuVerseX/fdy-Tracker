export function getPublicFreshnessHeadline(task) {
  if (!task?.finishedAt) {
    return '最近内容更新时间暂时不可用。'
  }
  return '最近内容已更新'
}
