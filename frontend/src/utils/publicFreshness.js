export function getPublicFreshnessHeadline(task) {
  if (!task?.finishedAt) {
    return '最近抓取记录暂时不可用。'
  }
  return '最近一次成功完成'
}
