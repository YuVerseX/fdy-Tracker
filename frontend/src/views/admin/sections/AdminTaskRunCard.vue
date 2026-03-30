<template>
  <article class="rounded-lg border border-gray-200 bg-gray-50 p-4">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <div class="flex flex-wrap items-center gap-2">
          <h3 class="text-base font-semibold text-sky-900">{{ getTaskTypeLabel(run.task_type || run.taskType) }}</h3>
          <span class="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium" :class="getTaskStatusClass(run.status, run)">
            {{ getTaskStatusLabel(run.status, run) }}
          </span>
        </div>
        <p class="mt-1 text-sm text-gray-600">{{ run.summary }}</p>
        <div class="mt-2 space-y-2">
          <div class="flex items-center justify-between gap-3 text-xs text-gray-500">
            <span>{{ run.phase || getDefaultTaskPhase(run) }}</span>
            <span>{{ getTaskProgressLabel(run) }}</span>
          </div>
          <div class="h-2 rounded-full bg-gray-200" role="progressbar" :aria-valuemin="0" :aria-valuemax="100" :aria-valuenow="getTaskProgress(run)" :aria-label="`${getTaskTypeLabel(run.task_type || run.taskType)} 进度`">
            <div class="h-2 rounded-full transition-all duration-300" :class="getTaskProgressBarClass(run)" :style="getTaskProgressBarStyle(run)" />
          </div>
          <div v-if="getTaskMetricsSummary(run)" class="text-xs text-gray-500">{{ getTaskMetricsSummary(run) }}</div>
          <div v-if="isRunningTaskStatus(run.status)" class="text-xs text-gray-500">已运行 {{ formatDuration(run) }}，最近心跳 {{ formatAdminDateTime(getTaskHeartbeatAt(run)) }}</div>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <div class="text-sm text-gray-500">{{ formatAdminDateTime(run.finished_at || run.started_at) }}</div>
        <button type="button" :disabled="retryingTaskId === run.id || !canRetryTask(run.task_type)" class="inline-flex items-center rounded-lg border border-sky-300 bg-sky-50 px-3 py-1.5 text-xs font-medium text-sky-700 transition-colors duration-200 hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-60" @click="retryTaskRun(run)">
          {{ retryingTaskId === run.id ? '重试中...' : '重试任务' }}
        </button>
        <button type="button" class="inline-flex items-center rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors duration-200 hover:bg-gray-100" @click="toggleTaskExpanded(run.id)">
          {{ isTaskExpanded(run.id) ? '收起详情' : '展开详情' }}
        </button>
      </div>
    </div>

    <div v-if="isTaskExpanded(run.id)" class="mt-4 space-y-4">
      <div v-if="isTaskRunPossiblyStuck(run, nowTs, heartbeatStaleMs)" class="rounded-lg border border-amber-300 bg-amber-50 px-3 py-3 text-sm text-amber-800">
        这个任务超过 10 分钟没有心跳，可能卡住了。可以先刷新状态，再决定是否重试。
      </div>

      <div class="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
        <div class="rounded-lg bg-white px-3 py-3"><div class="text-gray-500">开始时间</div><div class="mt-1 font-semibold text-gray-900">{{ formatAdminDateTime(run.started_at) }}</div></div>
        <div class="rounded-lg bg-white px-3 py-3"><div class="text-gray-500">结束时间</div><div class="mt-1 font-semibold text-gray-900">{{ formatAdminDateTime(run.finished_at) }}</div></div>
        <div class="rounded-lg bg-white px-3 py-3"><div class="text-gray-500">耗时</div><div class="mt-1 font-semibold text-gray-900">{{ formatDuration(run) }}</div></div>
        <div class="rounded-lg bg-white px-3 py-3"><div class="text-gray-500">最近心跳</div><div class="mt-1 font-semibold text-gray-900">{{ formatAdminDateTime(getTaskHeartbeatAt(run)) }}</div></div>
      </div>

      <div class="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2 xl:grid-cols-3">
        <div class="rounded-lg bg-white px-3 py-3"><div class="text-gray-500">参数 source_id</div><div class="mt-1 font-semibold text-gray-900">{{ formatSourceParam(run) }}</div></div>
        <div class="rounded-lg bg-white px-3 py-3"><div class="text-gray-500">参数 max_pages</div><div class="mt-1 font-semibold text-gray-900">{{ getTaskParam(run, 'max_pages', 'maxPages') ?? '--' }}</div></div>
        <div class="rounded-lg bg-white px-3 py-3"><div class="text-gray-500">参数 limit</div><div class="mt-1 font-semibold text-gray-900">{{ getTaskParam(run, 'limit') ?? '--' }}</div></div>
      </div>

      <div class="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
        <div class="rounded-lg bg-white px-3 py-3"><div class="text-gray-500">处理帖子</div><div class="mt-1 font-semibold text-gray-900">{{ getDetailValue(run.details, 'posts_updated', 'processed_records') }}</div></div>
        <div class="rounded-lg bg-white px-3 py-3"><div class="text-gray-500">发现附件</div><div class="mt-1 font-semibold text-gray-900">{{ getDetailValue(run.details, 'attachments_discovered') }}</div></div>
        <div class="rounded-lg bg-white px-3 py-3"><div class="text-gray-500">下载附件</div><div class="mt-1 font-semibold text-gray-900">{{ getDetailValue(run.details, 'attachments_downloaded') }}</div></div>
        <div class="rounded-lg bg-white px-3 py-3"><div class="text-gray-500">补字段</div><div class="mt-1 font-semibold text-gray-900">{{ getDetailValue(run.details, 'fields_added') }}</div></div>
      </div>

      <div v-if="getTaskFailureReason(run)" class="rounded-lg border border-red-200 bg-red-50 px-3 py-3 text-sm text-red-700">
        <span class="font-medium">失败原因：</span>{{ getTaskFailureReason(run) }}
      </div>
    </div>
  </article>
</template>

<script setup>
import {
  formatAdminDateTime,
  formatAdminDurationMs,
  getTaskHeartbeatAt,
  getTaskTypeLabel,
  isRunningTaskStatus,
  isTaskRunPossiblyStuck
} from '../../../utils/adminDashboardViewModels.js'

const props = defineProps({
  run: { type: Object, required: true },
  retryingTaskId: { type: String, required: true },
  expandedTaskIds: { type: Array, required: true },
  nowTs: { type: Number, required: true },
  sourceOptions: { type: Array, required: true },
  heartbeatStaleMs: { type: Number, required: true },
  retryTaskRun: { type: Function, required: true },
  toggleTaskExpanded: { type: Function, required: true },
  canRetryTask: { type: Function, required: true }
})

const getTaskProgressMode = (run) => (run?.status === 'success' || run?.status === 'failed' ? 'determinate' : ((run?.details?.progress_mode || run?.progress_mode) === 'determinate' ? 'determinate' : 'indeterminate'))
const getTaskProgress = (run) => {
  const rawValue = Number(run?.progress)
  if (Number.isFinite(rawValue)) return Math.max(0, Math.min(Math.round(rawValue), 100))
  if (run?.status === 'success' || run?.status === 'failed') return 100
  return 0
}
const getTaskProgressLabel = (run) => getTaskProgressMode(run) === 'determinate' ? `${getTaskProgress(run)}%` : (isTaskRunPossiblyStuck(run, props.nowTs, props.heartbeatStaleMs) ? '可能卡住' : (isRunningTaskStatus(run?.status) && getTaskProgress(run) > 0 ? `阶段 ${getTaskProgress(run)}%` : (isRunningTaskStatus(run?.status) ? '运行中' : '--')))
const getTaskProgressBarClass = (run) => (isTaskRunPossiblyStuck(run, props.nowTs, props.heartbeatStaleMs) ? 'bg-red-400' : (getTaskProgressMode(run) === 'determinate' ? 'bg-sky-500' : 'animate-pulse bg-sky-400'))
const getTaskProgressBarStyle = (run) => ({ width: `${getTaskProgressMode(run) === 'determinate' ? getTaskProgress(run) : Math.max(getTaskProgress(run), 12)}%` })
const getTaskMetricsSummary = (run) => {
  const metrics = run?.details?.metrics
  if (!metrics) return getTaskProgressMode(run) === 'indeterminate' && isRunningTaskStatus(run?.status) && getTaskProgress(run) > 0 ? `当前阶段已推进到约 ${getTaskProgress(run)}%` : ''
  const completed = Number(metrics.completed)
  const total = Number(metrics.total)
  if (Number.isFinite(completed) && Number.isFinite(total) && total > 0 && metrics.unit !== 'percent') return `已处理 ${completed} / ${total}${metrics.unit ? ` ${metrics.unit}` : ''}`
  if (Number.isFinite(completed) && Number.isFinite(total) && total > 0 && metrics.unit === 'percent') return `阶段进度 ${completed}%`
  return ''
}
const getDefaultTaskPhase = (run) => (run?.status === 'success' ? '执行完成' : run?.status === 'failed' ? '执行失败' : ((run?.status === 'queued' || run?.status === 'pending') ? '排队等待执行' : (isRunningTaskStatus(run?.status) ? '正在执行' : '')))
const getTaskStatusClass = (status, run) => (status === 'success' ? 'bg-emerald-100 text-emerald-700' : (isTaskRunPossiblyStuck(run, props.nowTs, props.heartbeatStaleMs) ? 'bg-red-100 text-red-700' : (((status === 'queued' || status === 'pending')) ? 'bg-slate-100 text-slate-700' : (isRunningTaskStatus(status) ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'))))
const getTaskStatusLabel = (status, run) => (status === 'success' ? '完成' : (isTaskRunPossiblyStuck(run, props.nowTs, props.heartbeatStaleMs) ? '可能卡住' : (((status === 'queued' || status === 'pending')) ? '排队中' : (isRunningTaskStatus(status) ? '运行中' : '失败'))))
const getTaskParam = (run, ...keys) => {
  const sources = [run?.params, run?.details?.params, run?.details?.request_params, run]
  for (const source of sources) {
    if (!source) continue
    for (const key of keys) {
      if (source[key] !== undefined && source[key] !== null && source[key] !== '') return source[key]
    }
  }
  return null
}
const getDetailValue = (details, ...keys) => {
  for (const key of keys) {
    if (details && details[key] !== undefined && details[key] !== null) return details[key]
  }
  return 0
}
const formatSourceParam = (run) => {
  const sourceId = getTaskParam(run, 'source_id', 'sourceId')
  if (!sourceId) return '全部数据源'
  const matchedSource = props.sourceOptions.find((source) => source.value === Number(sourceId))
  return matchedSource ? matchedSource.label : `source_id=${sourceId}`
}
const getTaskFailureReason = (run) => [run?.failure_reason, run?.error, run?.details?.failure_reason, run?.details?.error].find(Boolean) || ''
const getTaskElapsedMs = (run) => {
  const durationMs = Number(run?.duration_ms)
  if (Number.isFinite(durationMs) && durationMs >= 0) return durationMs
  const startedMs = Date.parse(run?.started_at || run?.startedAt || '')
  if (Number.isNaN(startedMs)) return null
  const finishedMs = Date.parse(run?.finished_at || run?.finishedAt || '')
  return Math.max((Number.isNaN(finishedMs) ? props.nowTs : finishedMs) - startedMs, 0)
}
const formatDuration = (run) => formatAdminDurationMs(getTaskElapsedMs(run))
const isTaskExpanded = (taskId) => props.expandedTaskIds.includes(taskId)
</script>
