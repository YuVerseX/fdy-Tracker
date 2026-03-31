<template>
  <section class="rounded-[28px] border border-slate-200 bg-white/90 p-6 shadow-sm">
    <div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
      <div>
        <AppSectionHeader
          title="任务中心"
          description="查看正在执行、刚完成和历史任务记录。"
        >
          <template #badge>
            <AppStatusBadge
              :label="presentation.counts.attention > 0 ? `${presentation.counts.attention} 项待处理` : '状态稳定'"
              :tone="presentation.counts.attention > 0 ? 'warning' : 'success'"
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

    <div v-if="loadingRuns || !taskRunsLoaded" class="py-10 text-center text-sm text-gray-500">正在加载任务记录...</div>
    <AppEmptyState
      v-else-if="taskRuns.length === 0"
      title="还没有任务记录"
      description="先运行一次任务，这里会显示最新进度和结果。"
    />

    <div v-else class="mt-6 space-y-6">
      <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <AppStatCard
          v-for="card in presentation.summaryCards"
          :key="card.label"
          :label="card.label"
          :value="card.value"
          size="sm"
          class="border-0 bg-slate-50"
        />
      </div>

      <section v-if="presentation.attentionRuns.length > 0" class="space-y-3">
        <div class="flex flex-wrap items-center gap-3">
          <h3 class="text-base font-semibold text-slate-900">需要关注</h3>
          <span class="rounded-full bg-rose-50 px-3 py-1 text-xs font-medium text-rose-700">
            {{ presentation.counts.attention }} 条任务需要处理
          </span>
          <span v-if="presentation.counts.stuck > 0" class="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
            {{ presentation.counts.stuck }} 条可能卡住
          </span>
        </div>
        <div class="space-y-4">
          <AdminTaskRunCard
            v-for="run in presentation.attentionRuns"
            :key="run.id"
            :run="run"
            :retrying-task-id="retryingTaskId"
            :retrying-task-action-key="retryingTaskActionKey"
            :expanded-task-ids="expandedTaskIds"
            :now-ts="nowTs"
            :source-options="sourceOptions"
            :heartbeat-stale-ms="heartbeatStaleMs"
            :retry-task-run="retryTaskRun"
            :toggle-task-expanded="toggleTaskExpanded"
            :can-retry-task="canRetryTask"
          />
        </div>
      </section>

      <section class="space-y-3">
        <div class="flex flex-wrap items-center gap-3">
          <h3 class="text-base font-semibold text-slate-900">最近完成</h3>
          <span class="rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">
            {{ presentation.counts.success }} 条完成记录
          </span>
        </div>
        <div v-if="presentation.recentSuccessRuns.length === 0" class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-sm text-gray-500">
          当前还没有最近完成记录，先运行一次任务。
        </div>
        <div v-else class="space-y-4">
          <AdminTaskRunCard
            v-for="run in presentation.recentSuccessRuns"
            :key="run.id"
            :run="run"
            :retrying-task-id="retryingTaskId"
            :retrying-task-action-key="retryingTaskActionKey"
            :expanded-task-ids="expandedTaskIds"
            :now-ts="nowTs"
            :source-options="sourceOptions"
            :heartbeat-stale-ms="heartbeatStaleMs"
            :retry-task-run="retryTaskRun"
            :toggle-task-expanded="toggleTaskExpanded"
            :can-retry-task="canRetryTask"
          />
        </div>
      </section>

      <AppDisclosure
        v-if="presentation.historyRuns.length > 0"
        :summary="`查看其余历史记录（${presentation.historyRuns.length} 条）`"
      >
        <div class="space-y-4">
          <AdminTaskRunCard
            v-for="run in presentation.historyRuns"
            :key="run.id"
            :run="run"
            :retrying-task-id="retryingTaskId"
            :retrying-task-action-key="retryingTaskActionKey"
            :expanded-task-ids="expandedTaskIds"
            :now-ts="nowTs"
            :source-options="sourceOptions"
            :heartbeat-stale-ms="heartbeatStaleMs"
            :retry-task-run="retryTaskRun"
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
  expandedTaskIds: { type: Array, required: true },
  nowTs: { type: Number, required: true },
  sourceOptions: { type: Array, required: true },
  heartbeatStaleMs: { type: Number, required: true },
  refreshTaskStatus: { type: Function, required: true },
  retryTaskRun: { type: Function, required: true },
  toggleTaskExpanded: { type: Function, required: true },
  canRetryTask: { type: Function, required: true }
})

const presentation = computed(() => buildTaskRunsPresentation({
  taskRuns: props.taskRuns,
  nowTs: props.nowTs,
  heartbeatStaleMs: props.heartbeatStaleMs
}))
</script>
