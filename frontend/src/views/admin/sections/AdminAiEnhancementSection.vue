<template>
  <div class="space-y-6">
    <section class="rounded-[28px] border border-slate-200 bg-white/90 p-6 shadow-sm">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <AppSectionHeader
          title="智能整理"
          description="在已有基础结果上继续补充摘要和岗位识别。"
          aside="基础处理未完成时，建议先回到“基础处理”继续补齐。"
        >
          <template #badge>
            <AppStatusBadge
              :label="runtimeCopy.badge"
              :tone="openaiReady ? 'success' : 'warning'"
            />
          </template>
        </AppSectionHeader>
      </div>

      <div class="mt-5">
        <AppNotice
          :tone="openaiReady ? 'success' : 'warning'"
          :title="openaiReady ? '智能服务已就绪' : '智能服务还未就绪'"
          :description="openaiReady ? runtimeCopy.emphasis : disabledReason"
        />
      </div>

      <div class="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <AppStatCard
          v-for="panel in panels"
          :key="panel.id"
          :label="panel.title"
          :value="panel.value"
          :description="panel.helper"
          :meta="panel.meta"
          size="lg"
          :class="panel.disabled ? 'border-slate-200 bg-slate-50' : 'border-emerald-200 bg-emerald-50/60'"
        >
          <template #badge>
            <span class="inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-medium" :class="panel.disabled ? 'bg-slate-200 text-slate-700' : 'bg-emerald-100 text-emerald-700'">
              {{ panel.disabled ? '未开启' : '可用' }}
            </span>
          </template>
          <template #footer>
            <p v-if="panel.disabledReason" class="text-xs text-amber-700">{{ panel.disabledReason }}</p>
          </template>
        </AppStatCard>
      </div>
    </section>

    <section class="rounded-[28px] border border-slate-200 bg-white/90 p-6 shadow-sm">
      <AppSectionHeader
        title="可选智能任务"
        description="基础结果准备好后，再决定是否继续补充智能整理。"
        aside="默认范围已经覆盖最常见场景；只有在需要缩小或放宽范围时再展开高级设置。"
      />

      <div class="mt-6 grid grid-cols-1 gap-5 xl:grid-cols-2">
        <AdminTaskActionCard
          v-for="card in cards"
          :key="card.id"
          :card="card"
        />
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'

import AppNotice from '../../../components/ui/AppNotice.vue'
import AppSectionHeader from '../../../components/ui/AppSectionHeader.vue'
import AppStatCard from '../../../components/ui/AppStatCard.vue'
import AppStatusBadge from '../../../components/ui/AppStatusBadge.vue'
import { buildAiProcessingCards } from '../adminProcessingActionCards.js'
import AdminTaskActionCard from './AdminTaskActionCard.vue'

const props = defineProps({
  runtimeCopy: { type: Object, required: true },
  openaiReady: { type: Boolean, required: true },
  disabledReason: { type: String, required: true },
  panels: { type: Array, required: true },
  sourceOptions: { type: Array, required: true },
  analysisForm: { type: Object, required: true },
  jobsForm: { type: Object, required: true },
  analysisBusy: { type: Boolean, required: true },
  jobsBusy: { type: Boolean, required: true },
  analysisLoading: { type: Boolean, required: true },
  jobsLoading: { type: Boolean, required: true },
  jobsSummaryUnavailable: { type: Boolean, required: true },
  latestAnalysisLabel: { type: String, required: true },
  latestJobsLabel: { type: String, required: true },
  runAiAnalysisTask: { type: Function, required: true },
  runAiJobExtractionTask: { type: Function, required: true },
  refreshAnalysisSummary: { type: Function, required: true },
  refreshJobSummary: { type: Function, required: true }
})

const cards = computed(() => buildAiProcessingCards(props))
</script>
