<template>
  <article class="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
    <div class="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
      <div class="min-w-0 flex-1 space-y-3">
        <div class="flex flex-wrap items-center gap-2">
          <h3 class="text-base font-semibold text-slate-900">{{ taskTitle }}</h3>
          <AppStatusBadge :label="statusLabel" :tone="statusTone" />
        </div>

        <p v-if="summaryText" class="text-sm leading-6 text-slate-600">{{ summaryText }}</p>

        <div class="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div class="space-y-1">
              <div class="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">当前阶段</div>
              <div class="text-sm font-medium text-slate-900">{{ progressView.stageLabel }}</div>
              <div class="text-sm text-slate-600">{{ progressView.progressLabel }}</div>
            </div>
            <div v-if="progressView.progressPercentLabel" class="text-sm font-semibold text-slate-900">
              {{ progressView.progressPercentLabel }}
            </div>
          </div>

          <div
            v-if="progressView.showProgressBar"
            class="mt-3 h-2 rounded-full bg-slate-100"
            role="progressbar"
            :aria-valuemin="progressView.mode === 'determinate' ? 0 : undefined"
            :aria-valuemax="progressView.mode === 'determinate' ? 100 : undefined"
            :aria-valuenow="progressView.mode === 'determinate' ? progressView.percent : undefined"
            :aria-valuetext="`${taskTitle} ${progressView.stageLabel}`"
          >
            <div class="h-2 rounded-full transition-all duration-300" :class="progressBarClass" :style="progressBarStyle" />
          </div>

          <div v-if="!progressView.showProgressBar || headlineMetricItems.length > 0" class="mt-3 flex flex-wrap gap-2">
            <AppMetricPill
              v-if="!progressView.showProgressBar"
              label="进度方式"
              :value="progressView.modeLabel"
              tone="muted"
            />
            <AppMetricPill
              v-for="item in headlineMetricItems"
              :key="item.key"
              :label="item.label"
              :value="item.value"
              tone="muted"
            />
          </div>

          <div v-if="isRunningTaskStatus(run.status)" class="mt-3 text-xs text-slate-500">
            已运行 {{ formatDuration(run) }}，最近更新 {{ formatAdminDateTime(getTaskHeartbeatAt(run)) }}
          </div>
        </div>
      </div>

      <div class="flex shrink-0 flex-wrap items-center gap-2 xl:max-w-[300px] xl:justify-end">
        <div class="text-xs text-slate-500 xl:w-full xl:text-right">{{ formatAdminDateTime(run.finished_at || run.started_at) }}</div>
        <AppActionButton
          v-for="action in actionDefinitions"
          :key="action.key"
          :label="action.label"
          :busy-label="action.busyLabel"
          :busy="isActionSubmitting(action.key)"
          :disabled="isAnyActionSubmitting"
          :variant="getActionButtonVariant(action.key)"
          size="sm"
          @click="handleTaskAction(action.key)"
        />
        <AppActionButton
          :label="isTaskExpanded(run.id) ? '收起详情' : '查看详情'"
          variant="neutral"
          size="sm"
          @click="toggleTaskExpanded(run.id)"
        />
      </div>
    </div>

    <div v-if="actionGuide" class="mt-4 rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
      <div class="flex flex-col gap-3">
        <AppNotice
          :title="actionGuide.title"
          :description="actionGuide.description"
        />

        <div v-if="actionGuide.contextBadge" class="flex flex-wrap gap-2">
          <AppMetricPill
            :label="actionGuide.contextBadge.label"
            :value="actionGuide.contextBadge.value"
            tone="muted"
          />
        </div>

        <div class="grid grid-cols-1 gap-3 xl:grid-cols-3">
          <div
            v-for="action in actionGuide.actions"
            :key="`${action.key}-guide`"
            class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"
          >
            <div class="flex flex-wrap items-center gap-2">
              <AppStatusBadge :label="action.label" tone="neutral" />
              <AppMetricPill
                v-if="action.scopeLabel"
                label="处理范围"
                :value="action.scopeLabel"
                tone="muted"
              />
            </div>
            <p v-if="action.description" class="mt-2 text-sm leading-6 text-slate-600">
              {{ action.description }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <div v-if="isTaskExpanded(run.id)" class="mt-4 space-y-4">
      <div v-if="progressView.isStuck" class="rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        这个任务超过 10 分钟没有新的阶段更新。先刷新状态；如果仍然没有变化，再决定是否重新提交。
      </div>

      <section v-for="section in detailSections" :key="section.id" class="space-y-3">
        <div class="flex items-center justify-between gap-3">
          <h4 class="text-sm font-semibold text-slate-900">{{ section.title }}</h4>
          <p class="text-xs text-slate-500">
            {{ section.id === 'facts' ? '用于确认任务范围和运行时间。' : '这里显示本次任务额外写入或处理结果。' }}
          </p>
        </div>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2" :class="section.id === 'facts' ? 'xl:grid-cols-4' : 'xl:grid-cols-3'">
          <AppStatCard
            v-for="item in section.items"
            :key="`${section.id}-${item.label}`"
            :label="item.label"
            :value="item.value"
            size="sm"
            class="shadow-sm"
          />
        </div>
      </section>

      <div v-if="failureReason" class="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
        <span class="font-medium">未完成原因：</span>{{ failureReason }}
      </div>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'

import AppActionButton from '../../../components/ui/AppActionButton.vue'
import AppMetricPill from '../../../components/ui/AppMetricPill.vue'
import AppNotice from '../../../components/ui/AppNotice.vue'
import AppStatCard from '../../../components/ui/AppStatCard.vue'
import AppStatusBadge from '../../../components/ui/AppStatusBadge.vue'
import { normalizeAdminUiMessage, normalizeAdminUiText } from '../../../utils/adminCopySanitizers.js'
import {
  formatAdminDateTime,
  formatAdminDurationMs,
  getTaskHeartbeatAt,
  getTaskTypeLabel,
  isRunningTaskStatus,
  isTaskRunPossiblyStuck
} from '../../../utils/adminDashboardViewModels.js'
import { buildTaskActionGuide } from '../adminDashboardTaskActions.js'
import {
  buildTaskDetailSections,
  buildTaskMetricItems,
  buildTaskProgressView
} from '../adminTaskRunPresentation.js'

const props = defineProps({
  run: { type: Object, required: true },
  retryingTaskId: { type: String, required: true },
  retryingTaskActionKey: { type: String, required: true },
  expandedTaskIds: { type: Array, required: true },
  nowTs: { type: Number, required: true },
  sourceOptions: { type: Array, required: true },
  heartbeatStaleMs: { type: Number, required: true },
  retryTaskRun: { type: Function, required: true },
  toggleTaskExpanded: { type: Function, required: true },
  canRetryTask: { type: Function, required: true }
})

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

const taskTitle = computed(() => props.run.display_name || getTaskTypeLabel(props.run.task_type || props.run.taskType))
const progressView = computed(() => buildTaskProgressView(props.run, {
  nowTs: props.nowTs,
  heartbeatStaleMs: props.heartbeatStaleMs
}))
const metricItems = computed(() => buildTaskMetricItems(props.run))
const headlineMetricItems = computed(() => metricItems.value.slice(0, 4))
const detailSections = computed(() => buildTaskDetailSections(props.run, {
  sourceOptions: props.sourceOptions,
  nowTs: props.nowTs
}))
const actionGuide = computed(() => buildTaskActionGuide(props.run))
const actionDefinitions = computed(() => actionGuide.value?.actions || [])
const isAnyActionSubmitting = computed(() => props.retryingTaskId === props.run.id)
const failureReason = computed(() => normalizeAdminUiMessage(
  getTaskFailureReason(props.run),
  '这次处理没有完成，请稍后重试；如果问题持续存在，请查看后台日志。'
))
const summaryText = computed(() => normalizeAdminUiText(props.run.summary || ''))

const statusLabel = computed(() => {
  if (isTaskRunPossiblyStuck(props.run, props.nowTs, props.heartbeatStaleMs)) return '进度停滞'
  if (props.run.status_label) return props.run.status_label
  if (props.run.status === 'success') return '完成'
  if (props.run.status === 'failed') return '失败'
  if (props.run.status === 'queued' || props.run.status === 'pending') return '排队中'
  if (isRunningTaskStatus(props.run.status)) return '运行中'
  return '--'
})

const statusTone = computed(() => {
  if (props.run.status === 'success') return 'success'
  if (isTaskRunPossiblyStuck(props.run, props.nowTs, props.heartbeatStaleMs)) return 'danger'
  if (props.run.status === 'queued' || props.run.status === 'pending') return 'neutral'
  if (isRunningTaskStatus(props.run.status)) return 'warning'
  return 'danger'
})

const progressBarClass = computed(() => {
  if (progressView.value.mode === 'determinate') {
    if (props.run.status === 'success') return 'bg-emerald-500'
    if (props.run.status === 'failed' || progressView.value.isStuck) return 'bg-rose-500'
    return 'bg-sky-500'
  }

  if (props.run.status === 'success') return 'bg-emerald-400'
  if (props.run.status === 'failed' || progressView.value.isStuck) return 'bg-rose-400'
  if (props.run.status === 'queued' || props.run.status === 'pending') return 'bg-slate-300'
  return 'animate-pulse bg-sky-300'
})

const progressBarStyle = computed(() => ({
  width: `${progressView.value.mode === 'determinate' ? progressView.value.visualPercent : 100}%`
}))

const isActionSubmitting = (actionKey) => props.retryingTaskId === props.run.id && props.retryingTaskActionKey === actionKey

const getActionButtonVariant = (actionKey) => (actionKey === 'incremental' ? 'neutral' : 'sky-soft')

const handleTaskAction = (actionKey) => {
  props.retryTaskRun(props.run, actionKey)
}
</script>
