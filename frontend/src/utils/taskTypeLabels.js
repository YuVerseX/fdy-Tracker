const PUBLIC_TASK_TYPE_LABELS = {
  manual_scrape: '手动抓取',
  scheduled_scrape: '定时抓取',
  attachment_backfill: '历史附件补处理',
  job_extraction: '岗位整理',
  ai_job_extraction: '岗位整理'
}

export const getPublicTaskTypeLabel = (taskType) => (
  PUBLIC_TASK_TYPE_LABELS[taskType] || '后台任务'
)
