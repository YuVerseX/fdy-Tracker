<template>
  <article class="app-surface app-surface--padding-md task-run-card" :class="surfaceToneClass">
    <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div class="min-w-0 flex-1 space-y-4">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div class="min-w-0 space-y-2">
            <div class="flex flex-wrap items-center gap-2">
              <h3 class="text-base font-semibold text-slate-900">{{ cardPresentation.title }}</h3>
              <AppStatusBadge :label="cardPresentation.statusLabel" :tone="cardPresentation.statusTone" />
            </div>
            <p v-if="cardPresentation.summaryText" class="text-sm leading-6 text-slate-600">
              {{ cardPresentation.summaryText }}
            </p>
          </div>

          <div class="shrink-0 text-xs text-slate-500 lg:text-right">
            {{ cardPresentation.timelineText }}
          </div>
        </div>

        <div class="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
          <section class="task-run-card__panel space-y-3">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <h4 class="text-sm font-semibold text-slate-900">{{ cardPresentation.stageTitle }}</h4>
                <p class="mt-1 text-sm leading-6 text-slate-600">{{ cardPresentation.progressView.stageLabel }}</p>
              </div>
              <div class="shrink-0 text-left lg:text-right">
                <p class="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">
                  {{ cardPresentation.progressView.modeLabel }}
                </p>
                <p v-if="cardPresentation.progressView.progressPercentLabel" class="mt-1 text-sm font-semibold text-slate-900">
                  {{ cardPresentation.progressView.progressPercentLabel }}
                </p>
              </div>
            </div>

            <AdminTaskStageTimeline :items="cardPresentation.stageTimelineItems" />

            <p v-if="cardPresentation.progressView.progressLabel" class="text-sm leading-6 text-slate-600">
              {{ cardPresentation.progressView.progressLabel }}
            </p>

            <div
              v-if="cardPresentation.progressView.showProgressBar"
              class="h-2 rounded-full bg-slate-100"
              role="progressbar"
              :aria-valuemin="cardPresentation.progressView.mode === 'determinate' ? 0 : undefined"
              :aria-valuemax="cardPresentation.progressView.mode === 'determinate' ? 100 : undefined"
              :aria-valuenow="cardPresentation.progressView.mode === 'determinate' ? cardPresentation.progressView.percent : undefined"
              :aria-valuetext="`${cardPresentation.title} ${cardPresentation.progressView.stageLabel}`"
            >
              <div class="h-2 rounded-full transition-all duration-300" :class="progressBarClass" :style="progressBarStyle" />
            </div>

            <AppFactList
              :items="cardPresentation.stageFacts"
              :columns="2"
              tone="muted"
              compact
            />
          </section>

          <section class="task-run-card__panel space-y-3">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <h4 class="text-sm font-semibold text-slate-900">{{ cardPresentation.resultTitle }}</h4>
                <p v-if="showResultHint" class="mt-1 text-sm leading-6 text-slate-500">{{ cardPresentation.resultHint }}</p>
              </div>
              <AppMetricPill
                v-if="primaryActionDefinition?.scopeLabel"
                label="处理范围"
                :value="primaryActionDefinition.scopeLabel"
                tone="muted"
              />
            </div>

            <div v-if="cardPresentation.resultItems.length > 0" class="flex flex-wrap gap-2">
              <AppMetricPill
                v-for="item in cardPresentation.resultItems"
                :key="item.key"
                :label="item.label"
                :value="item.value"
                tone="muted"
              />
            </div>
            <p v-else-if="cardPresentation.resultEmptyText" class="text-sm leading-6 text-slate-500">
              {{ cardPresentation.resultEmptyText }}
            </p>

            <div
              v-if="primaryActionDefinition"
              class="rounded-2xl border border-slate-200/80 bg-white/90 px-3 py-3"
            >
              <div class="flex flex-wrap items-center gap-2">
                <span class="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">建议操作</span>
                <AppStatusBadge :label="primaryActionDefinition.label" tone="neutral" />
              </div>
              <p v-if="primaryActionDefinition.description" class="mt-2 text-sm leading-6 text-slate-600">
                {{ primaryActionDefinition.description }}
              </p>
            </div>
          </section>
        </div>

        <AppNotice
          v-if="cardPresentation.cancellationNotice"
          tone="warning"
          :title="cardPresentation.cancellationNotice.title"
          :description="cardPresentation.cancellationNotice.description"
        />

        <AppNotice
          v-if="cardPresentation.stuckNotice"
          tone="warning"
          :title="cardPresentation.stuckNotice.title"
          :description="cardPresentation.stuckNotice.description"
        />

        <AppNotice
          v-if="cardPresentation.failureNotice"
          tone="danger"
          :title="cardPresentation.failureNotice.title"
          :description="cardPresentation.failureNotice.description"
        />
      </div>

      <div class="flex shrink-0 flex-wrap items-center gap-2 lg:max-w-[320px] lg:justify-end">
        <AppActionButton
          v-if="primaryActionDefinition"
          :label="primaryActionDefinition.label"
          :busy-label="primaryActionDefinition.busyLabel"
          :busy="isActionSubmitting(primaryActionDefinition.key)"
          :disabled="isAnyActionSubmitting"
          :variant="getActionButtonVariant(primaryActionDefinition.key)"
          size="sm"
          @click="handleTaskAction(primaryActionDefinition.key)"
        />
        <AppActionButton
          v-if="hasDetailContent"
          :label="isTaskExpanded(run.id) ? '收起详情' : '查看详情'"
          variant="neutral"
          size="sm"
          @click="toggleTaskExpanded(run.id)"
        />
      </div>
    </div>

    <div v-if="isTaskExpanded(run.id) && hasDetailContent" class="mt-4 space-y-4">
      <section v-for="section in cardPresentation.detailSections" :key="section.id" class="space-y-3">
        <div class="flex items-center justify-between gap-3">
          <h4 class="text-sm font-semibold text-slate-900">{{ section.title }}</h4>
          <p class="text-xs text-slate-500">
            {{ section.id === 'facts' ? '用于确认任务范围和运行时间。' : '这里显示本次任务的补充结果。' }}
          </p>
        </div>

        <AppFactList
          :items="section.items"
          :columns="3"
          tone="muted"
        />
      </section>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'

import AppActionButton from '../../../components/ui/AppActionButton.vue'
import AppFactList from '../../../components/ui/AppFactList.vue'
import AppMetricPill from '../../../components/ui/AppMetricPill.vue'
import AppNotice from '../../../components/ui/AppNotice.vue'
import AppStatusBadge from '../../../components/ui/AppStatusBadge.vue'
import { buildTaskRunCardPresentation } from '../adminTaskRunPresentation.js'
import AdminTaskStageTimeline from './AdminTaskStageTimeline.vue'

const props = defineProps({
  run: { type: Object, required: true },
  retryingTaskId: { type: String, required: true },
  retryingTaskActionKey: { type: String, required: true },
  cancelingTaskId: { type: String, required: true },
  expandedTaskIds: { type: Array, required: true },
  nowTs: { type: Number, required: true },
  sourceOptions: { type: Array, required: true },
  heartbeatStaleMs: { type: Number, required: true },
  retryTaskRun: { type: Function, required: true },
  cancelTaskRun: { type: Function, required: true },
  toggleTaskExpanded: { type: Function, required: true },
  canRetryTask: { type: Function, required: true }
})

const toneClassMap = {
  muted: 'app-surface--muted',
  info: 'app-surface--info',
  success: 'app-surface--success',
  warning: 'app-surface--warning',
  danger: 'app-surface--danger'
}

const cardPresentation = computed(() => buildTaskRunCardPresentation(props.run, {
  sourceOptions: props.sourceOptions,
  nowTs: props.nowTs,
  heartbeatStaleMs: props.heartbeatStaleMs
}))

const primaryActionDefinition = computed(() => (
  props.canRetryTask(props.run.task_type || props.run.taskType)
    ? (cardPresentation.value.actionItems[0] || null)
    : null
))
const isAnyActionSubmitting = computed(() => (
  props.retryingTaskId === props.run.id || props.cancelingTaskId === props.run.id
))
const hasDetailContent = computed(() => cardPresentation.value.detailSections.length > 0)
const showResultHint = computed(() => {
  const { resultHint, resultEmptyText, resultItems } = cardPresentation.value
  if (!resultHint) return false
  if (resultItems.length === 0 && resultHint === resultEmptyText) return false
  return true
})
const surfaceToneClass = computed(() => toneClassMap[cardPresentation.value.surfaceTone] || toneClassMap.muted)
const isTaskExpanded = (taskId) => props.expandedTaskIds.includes(taskId)

const progressBarClass = computed(() => {
  if (props.run.status === 'success') return 'bg-emerald-500'
  if (props.run.status === 'failed' || cardPresentation.value.progressView.isStuck) return 'bg-rose-500'
  return 'bg-sky-500'
})

const progressBarStyle = computed(() => ({
  width: `${cardPresentation.value.progressView.visualPercent}%`
}))

const isActionSubmitting = (actionKey) => (
  actionKey === 'cancel'
    ? props.cancelingTaskId === props.run.id
    : props.retryingTaskId === props.run.id && props.retryingTaskActionKey === actionKey
)

const getActionButtonVariant = (actionKey) => {
  if (actionKey === 'incremental') return 'neutral'
  if (actionKey === 'cancel') return 'warning'
  return 'sky-soft'
}

const handleTaskAction = (actionKey) => {
  if (actionKey === 'cancel') {
    props.cancelTaskRun(props.run)
    return
  }
  props.retryTaskRun(props.run, actionKey)
}
</script>
