<template>
  <div class="space-y-4 lg:space-y-5">
    <AppSurface padding="lg">
      <div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
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

      <div class="mt-4">
        <AppNotice
          :tone="openaiReady ? 'success' : 'warning'"
          :title="openaiReady ? '智能服务已就绪' : '智能服务还未就绪'"
          :description="openaiReady ? runtimeCopy.emphasis : disabledReason"
        />
      </div>

      <div class="mt-4 flex flex-wrap gap-2">
        <AppMetricPill
          v-for="panel in panels"
          :key="panel.id"
          :label="panel.title"
          :value="panel.value"
          :tone="getPanelTone(panel)"
        />
      </div>

      <div class="mt-3 grid gap-2 md:grid-cols-2">
        <div
          v-for="line in panelContextLines"
          :key="line"
          class="rounded-[14px] border border-[rgba(148,163,184,0.16)] bg-white/72 px-3 py-2 text-[12px] leading-5 text-slate-500"
        >
          {{ line }}
        </div>
      </div>
    </AppSurface>

    <AppSurface padding="lg">
      <AppSectionHeader
        title="可选智能任务"
        description="基础结果准备好后，再决定是否继续补充智能整理。"
        aside="默认范围已经覆盖最常见场景；只有在需要缩小或放宽范围时再展开高级设置。"
      />

      <div class="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <AdminTaskActionCard
          v-for="card in cards"
          :key="card.id"
          :card="card"
        />
      </div>
    </AppSurface>
  </div>
</template>

<script setup>
import { computed } from 'vue'

import AppMetricPill from '../../../components/ui/AppMetricPill.vue'
import AppNotice from '../../../components/ui/AppNotice.vue'
import AppSectionHeader from '../../../components/ui/AppSectionHeader.vue'
import AppStatusBadge from '../../../components/ui/AppStatusBadge.vue'
import AppSurface from '../../../components/ui/AppSurface.vue'
import { buildAiProcessingCards } from '../adminProcessingActionCards.js'
import AdminTaskActionCard from './AdminTaskActionCard.vue'

const props = defineProps({
  runtimeCopy: { type: Object, required: true },
  openaiReady: { type: Boolean, required: true },
  disabledReason: { type: String, required: true },
  jobsBlockedReason: { type: String, required: true },
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

const normalizeMetaLines = (meta) => {
  if (Array.isArray(meta)) return meta.filter(Boolean)
  return meta ? [meta] : []
}

const getPanelTone = (panel) => {
  if (panel.disabled) return 'warning'
  if (panel.id === 'ai-models') return 'info'
  if (panel.id === 'ai-runtime-status') return 'success'
  return 'info'
}

const panelContextLines = computed(() => {
  const uniqueLines = new Set()

  props.panels.forEach((panel) => {
    const lines = [panel.helper, ...normalizeMetaLines(panel.meta).slice(0, 1)]
      .filter(Boolean)
      .map((line) => `${panel.title}：${line}`)

    if (panel.disabledReason) {
      lines.push(`${panel.title}：${panel.disabledReason}`)
    }

    lines.forEach((line) => uniqueLines.add(line))
  })

  return [...uniqueLines]
})
</script>
