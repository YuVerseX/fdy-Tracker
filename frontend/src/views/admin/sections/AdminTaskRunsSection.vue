<template>
  <section class="app-surface app-surface--padding-lg">
    <div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
      <div>
        <AppSectionHeader
          title="任务中心"
          description="按当前任务、最近结果和历史记录查看处理状态。"
        >
          <template #badge>
            <AppStatusBadge
              :label="headerBadge.label"
              :tone="headerBadge.tone"
            />
          </template>
        </AppSectionHeader>
      </div>
      <AppActionButton
        label="刷新状态"
        busy-label="刷新中..."
        :busy="loadingRuns"
        @click="refreshTaskStatus"
      />
    </div>

    <div class="mt-4 rounded-3xl border border-slate-200 bg-slate-50/85 p-4">
      <div class="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div class="flex flex-wrap items-center gap-2">
          <AppStatusBadge
            :label="resolvedSyncStatus.badgeLabel"
            :tone="resolvedSyncStatus.badgeTone"
          />
          <AppMetricPill label="同步频率" :value="resolvedSyncStatus.intervalLabel" tone="muted" />
          <AppMetricPill label="最近同步" :value="resolvedSyncStatus.lastSyncedLabel" tone="muted" />
          <AppMetricPill label="活跃任务" :value="resolvedSyncStatus.runningCountLabel" tone="muted" />
        </div>
        <p class="text-sm leading-6 text-slate-500">
          {{ resolvedSyncStatus.summary }}
        </p>
      </div>
    </div>

    <div v-if="loadingRuns || !taskRunsLoaded" class="py-10 text-center text-sm text-gray-500">正在加载任务记录...</div>
    <AppEmptyState
      v-else-if="taskRuns.length === 0"
      title="还没有任务记录"
      description="先运行一次任务，这里会按当前记录展示进度和结果。"
    />

    <div v-else class="mt-5 space-y-5 lg:space-y-6">
      <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <AppStatCard
          v-for="card in presentation.summaryCards"
          :key="card.label"
          :label="card.label"
          :value="card.value"
          :value-tone="getSummaryCardValueTone(card.tone)"
          :description="card.description"
          :meta="card.meta"
          size="sm"
          :class="getSummaryCardClass(card.tone)"
        />
      </div>

      <section class="space-y-3">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h3 class="text-base font-semibold text-slate-900">当前任务</h3>
            <p class="text-sm leading-6 text-slate-500">
              这里显示正在排队或处理中的任务，按当前同步状态刷新阶段和结果。
            </p>
          </div>
          <div class="flex flex-wrap gap-2">
            <AppMetricPill label="当前任务" :value="`${presentation.counts.current} 条`" tone="muted" />
            <AppMetricPill v-if="presentation.counts.processing > 0" label="正在处理" :value="`${presentation.counts.processing} 条`" tone="muted" />
            <AppMetricPill v-if="presentation.counts.queued > 0" label="等待开始" :value="`${presentation.counts.queued} 条`" tone="muted" />
            <AppMetricPill v-if="presentation.counts.stuck > 0" label="进度停滞" :value="`${presentation.counts.stuck} 条`" tone="muted" />
          </div>
        </div>

        <AppNotice
          v-if="presentation.currentRuns.length === 0"
          title="当前没有活跃任务"
          tone="info"
          description="发起新的处理后，这里会按当前同步状态展示排队状态、当前阶段和结果。"
        />
        <div v-else class="space-y-4">
          <AdminTaskRunCard
            v-for="run in presentation.currentRuns"
            :key="run.id"
            :run="run"
            :retrying-task-id="retryingTaskId"
            :retrying-task-action-key="retryingTaskActionKey"
            :canceling-task-id="cancelingTaskId"
            :expanded-task-ids="expandedTaskIds"
            :now-ts="nowTs"
            :source-options="sourceOptions"
            :heartbeat-stale-ms="heartbeatStaleMs"
            :retry-task-run="retryTaskRun"
            :cancel-task-run="cancelTaskRun"
            :toggle-task-expanded="toggleTaskExpanded"
            :can-retry-task="canRetryTask"
          />
        </div>
      </section>

      <section class="space-y-3">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h3 class="text-base font-semibold text-slate-900">最近结果</h3>
            <p class="text-sm leading-6 text-slate-500">
              查看刚结束任务的结果和状态。
            </p>
          </div>
          <div class="flex flex-wrap gap-2">
            <AppMetricPill label="最近结果" :value="`${presentation.counts.results} 条`" tone="muted" />
            <AppMetricPill v-if="presentation.counts.failed > 0" label="未完成" :value="`${presentation.counts.failed} 条`" tone="muted" />
            <AppMetricPill v-if="presentation.counts.success > 0" label="已完成" :value="`${presentation.counts.success} 条`" tone="muted" />
            <AppMetricPill v-if="presentation.counts.cancelled > 0" label="已终止" :value="`${presentation.counts.cancelled} 条`" tone="muted" />
          </div>
        </div>

        <AppNotice
          v-if="presentation.recentResultRuns.length === 0"
          title="最近还没有结果记录"
          tone="info"
          description="有新的完成记录后，这里会展示结果和状态。"
        />
        <div v-else class="space-y-4">
          <AdminTaskRunCard
            v-for="run in presentation.recentResultRuns"
            :key="run.id"
            :run="run"
            :retrying-task-id="retryingTaskId"
            :retrying-task-action-key="retryingTaskActionKey"
            :canceling-task-id="cancelingTaskId"
            :expanded-task-ids="expandedTaskIds"
            :now-ts="nowTs"
            :source-options="sourceOptions"
            :heartbeat-stale-ms="heartbeatStaleMs"
            :retry-task-run="retryTaskRun"
            :cancel-task-run="cancelTaskRun"
            :toggle-task-expanded="toggleTaskExpanded"
            :can-retry-task="canRetryTask"
          />
        </div>
      </section>

      <AppDisclosure
        v-if="presentation.historyRuns.length > 0"
        :summary="`查看历史记录（${presentation.historyRuns.length} 条）`"
      >
        <div class="mb-4 text-sm leading-6 text-slate-500">
          更早的完成和未完成记录会保留在这里，方便回看处理范围与结果。
        </div>
        <div class="space-y-4">
          <AdminTaskRunCard
            v-for="run in presentation.historyRuns"
            :key="run.id"
            :run="run"
            :retrying-task-id="retryingTaskId"
            :retrying-task-action-key="retryingTaskActionKey"
            :canceling-task-id="cancelingTaskId"
            :expanded-task-ids="expandedTaskIds"
            :now-ts="nowTs"
            :source-options="sourceOptions"
            :heartbeat-stale-ms="heartbeatStaleMs"
            :retry-task-run="retryTaskRun"
            :cancel-task-run="cancelTaskRun"
            :toggle-task-expanded="toggleTaskExpanded"
            :can-retry-task="canRetryTask"
          />
        </div>
      </AppDisclosure>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

import AppActionButton from '../../../components/ui/AppActionButton.vue'
import AppDisclosure from '../../../components/ui/AppDisclosure.vue'
import AppEmptyState from '../../../components/ui/AppEmptyState.vue'
import AppMetricPill from '../../../components/ui/AppMetricPill.vue'
import AppNotice from '../../../components/ui/AppNotice.vue'
import AppSectionHeader from '../../../components/ui/AppSectionHeader.vue'
import AppStatCard from '../../../components/ui/AppStatCard.vue'
import AppStatusBadge from '../../../components/ui/AppStatusBadge.vue'
import { buildTaskRunsPresentation } from '../../../utils/adminDashboardViewModels.js'
import AdminTaskRunCard from './AdminTaskRunCard.vue'

const props = defineProps({
  taskRuns: { type: Array, required: true },
  taskRunsLoaded: { type: Boolean, required: true },
  loadingRuns: { type: Boolean, required: true },
  retryingTaskId: { type: String, required: true },
  retryingTaskActionKey: { type: String, required: true },
  cancelingTaskId: { type: String, required: true },
  expandedTaskIds: { type: Array, required: true },
  nowTs: { type: Number, required: true },
  sourceOptions: { type: Array, required: true },
  heartbeatStaleMs: { type: Number, required: true },
  syncStatus: { type: Object, required: true },
  refreshTaskStatus: { type: Function, required: true },
  retryTaskRun: { type: Function, required: true },
  cancelTaskRun: { type: Function, required: true },
  toggleTaskExpanded: { type: Function, required: true },
  canRetryTask: { type: Function, required: true }
})

const AUTO_REFRESH_BADGE_LABEL = '自动刷新中'
const MANUAL_REFRESH_SUMMARY = '当前无自动刷新，仅支持手动刷新。'

const resolvedSyncStatus = computed(() => ({
  badgeLabel: props.syncStatus?.badgeLabel || (props.syncStatus?.autoRefreshActive ? AUTO_REFRESH_BADGE_LABEL : '手动刷新'),
  badgeTone: props.syncStatus?.badgeTone || 'neutral',
  intervalLabel: props.syncStatus?.intervalLabel || '15 秒',
  lastSyncedLabel: props.syncStatus?.lastSyncedLabel || '尚未同步',
  runningCountLabel: props.syncStatus?.runningCountLabel || '0 条',
  summary: props.syncStatus?.summary || MANUAL_REFRESH_SUMMARY
}))

const presentation = computed(() => buildTaskRunsPresentation({
  taskRuns: props.taskRuns,
  nowTs: props.nowTs,
  heartbeatStaleMs: props.heartbeatStaleMs
}))

const headerBadge = computed(() => {
  if (presentation.value.counts.current > 0) {
    return { label: `${presentation.value.counts.current} 项活跃`, tone: 'warning' }
  }
  if (presentation.value.counts.failed > 0) {
    return { label: `${presentation.value.counts.failed} 项未完成`, tone: 'danger' }
  }
  return { label: '状态稳定', tone: 'success' }
})

const summaryCardClassMap = {
  amber: 'border-amber-100 bg-amber-50/80 shadow-none',
  emerald: 'border-emerald-100 bg-emerald-50/80 shadow-none',
  rose: 'border-rose-100 bg-rose-50/80 shadow-none',
  slate: 'border-slate-200 bg-slate-50 shadow-none'
}

const summaryCardValueToneMap = {
  amber: 'warning',
  emerald: 'success',
  rose: 'warning',
  slate: 'default'
}

const getSummaryCardClass = (tone) => summaryCardClassMap[tone] || summaryCardClassMap.slate
const getSummaryCardValueTone = (tone) => summaryCardValueToneMap[tone] || summaryCardValueToneMap.slate
</script>
