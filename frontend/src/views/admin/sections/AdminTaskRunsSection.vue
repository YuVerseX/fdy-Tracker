<template>
  <section class="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
    <div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
      <div>
        <h2 class="text-lg font-semibold text-sky-900">任务记录</h2>
        <p class="mt-1 text-sm text-gray-500">默认先看当前异常和最近结果，历史明细收进下方折叠区，减少旧失败记录的干扰。</p>
      </div>
      <button type="button" :disabled="loadingRuns" class="inline-flex items-center rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition-colors duration-200 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60" @click="refreshTaskStatus">
        {{ loadingRuns ? '刷新中...' : '刷新状态' }}
      </button>
    </div>

    <div v-if="loadingRuns || !taskRunsLoaded" class="py-10 text-center text-sm text-gray-500">正在加载任务记录...</div>
    <div v-else-if="taskRuns.length === 0" class="py-10 text-center text-sm text-gray-500">还没有管理任务记录，先手动跑一次任务。</div>

    <div v-else class="mt-6 space-y-6">
      <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div v-for="card in presentation.summaryCards" :key="card.label" class="rounded-lg bg-slate-50 px-4 py-3">
          <div class="text-xs text-gray-500">{{ card.label }}</div>
          <div class="mt-1 text-lg font-semibold text-slate-900">{{ card.value }}</div>
        </div>
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
          当前还没有最近完成记录，先运行一次治理任务。
        </div>
        <div v-else class="space-y-4">
          <AdminTaskRunCard
            v-for="run in presentation.recentSuccessRuns"
            :key="run.id"
            :run="run"
            :retrying-task-id="retryingTaskId"
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

      <details v-if="presentation.historyRuns.length > 0" class="rounded-lg border border-slate-200 bg-slate-50 p-4">
        <summary class="cursor-pointer list-none text-sm font-medium text-slate-700">
          查看其余历史记录（{{ presentation.historyRuns.length }} 条）
        </summary>
        <div class="mt-4 space-y-4">
          <AdminTaskRunCard
            v-for="run in presentation.historyRuns"
            :key="run.id"
            :run="run"
            :retrying-task-id="retryingTaskId"
            :expanded-task-ids="expandedTaskIds"
            :now-ts="nowTs"
            :source-options="sourceOptions"
            :heartbeat-stale-ms="heartbeatStaleMs"
            :retry-task-run="retryTaskRun"
            :toggle-task-expanded="toggleTaskExpanded"
            :can-retry-task="canRetryTask"
          />
        </div>
      </details>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

import { buildTaskRunsPresentation } from '../../../utils/adminDashboardViewModels.js'
import AdminTaskRunCard from './AdminTaskRunCard.vue'

const props = defineProps({
  taskRuns: { type: Array, required: true },
  taskRunsLoaded: { type: Boolean, required: true },
  loadingRuns: { type: Boolean, required: true },
  retryingTaskId: { type: String, required: true },
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
