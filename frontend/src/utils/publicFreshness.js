export function getPublicFreshnessHeadline(task) {
  if (!task?.finishedAt) {
    return '最近抓取记录暂时不可用。'
  }
  if (task.scope === 'source') {
    return '当前数据源最近一次成功抓取'
  }
  return '当前公开范围最近一次成功抓取'
}
