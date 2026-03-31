<template>
  <div class="space-y-4 lg:space-y-5">
    <AppNotice
      tone="info"
      title="建议顺序"
      description="先抓取最新公告，再按需要补附件、关键信息和岗位；只有在需要缩小范围时再展开更多设置。"
    />

    <AppSurface
      v-for="group in groups"
      :key="group.id"
      padding="lg"
    >
      <div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <AppSectionHeader
          :title="group.panel.title"
          :description="group.panel.description"
          :aside="group.helper"
        />
        <AppActionButton
          v-if="group.refreshAction"
          class="md:shrink-0"
          :label="group.refreshAction.label"
          :busy-label="group.refreshAction.busyLabel"
          :busy="group.refreshAction.busy"
          :disabled="group.refreshAction.disabled"
          @click="group.refreshAction.onClick?.()"
        />
      </div>

      <div class="mt-4 flex flex-wrap gap-2">
        <AppMetricPill
          v-for="item in group.panel.stats"
          :key="`${group.id}-${item.label}`"
          :label="item.label"
          :value="item.value"
          :tone="getMetricTone(item.tone)"
        />
      </div>

      <div v-if="buildGroupContext(group).length > 0" class="mt-3 grid gap-2 md:grid-cols-2">
        <div
          v-for="line in buildGroupContext(group)"
          :key="`${group.id}-${line}`"
          class="rounded-[14px] border border-[rgba(148,163,184,0.16)] bg-white/72 px-3 py-2 text-[12px] leading-5 text-slate-500"
        >
          {{ line }}
        </div>
      </div>

      <div class="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <AdminTaskActionCard
          v-for="card in group.cards"
          :key="card.id"
          :card="card"
        />
      </div>
    </AppSurface>
  </div>
</template>

<script setup>
import { computed } from 'vue'

import AppActionButton from '../../../components/ui/AppActionButton.vue'
import AppMetricPill from '../../../components/ui/AppMetricPill.vue'
import AppNotice from '../../../components/ui/AppNotice.vue'
import AppSectionHeader from '../../../components/ui/AppSectionHeader.vue'
import AppSurface from '../../../components/ui/AppSurface.vue'
import { buildBaseProcessingGroups } from '../adminProcessingActionCards.js'
import AdminTaskActionCard from './AdminTaskActionCard.vue'

const props = defineProps({
  collectPanel: { type: Object, required: true },
  duplicatePanel: { type: Object, required: true },
  analysisPanel: { type: Object, required: true },
  jobsPanel: { type: Object, required: true },
  sourceOptions: { type: Array, required: true },
  jobsSummaryUnavailable: { type: Boolean, required: true },
  scrapeForm: { type: Object, required: true },
  backfillForm: { type: Object, required: true },
  duplicateForm: { type: Object, required: true },
  baseAnalysisForm: { type: Object, required: true },
  jobIndexForm: { type: Object, required: true },
  scrapeBusy: { type: Boolean, required: true },
  backfillBusy: { type: Boolean, required: true },
  duplicateBusy: { type: Boolean, required: true },
  baseAnalysisBusy: { type: Boolean, required: true },
  jobIndexBusy: { type: Boolean, required: true },
  duplicateLoading: { type: Boolean, required: true },
  analysisLoading: { type: Boolean, required: true },
  jobsLoading: { type: Boolean, required: true },
  runScrapeTask: { type: Function, required: true },
  runBackfillTask: { type: Function, required: true },
  runDuplicateBackfillTask: { type: Function, required: true },
  runBaseAnalysisTask: { type: Function, required: true },
  runJobIndexTask: { type: Function, required: true },
  refreshDuplicateSummary: { type: Function, required: true },
  refreshAnalysisSummary: { type: Function, required: true },
  refreshJobSummary: { type: Function, required: true }
})

const groups = computed(() => buildBaseProcessingGroups(props))

const toneMap = {
  sky: 'info',
  amber: 'warning',
  slate: 'muted',
  cyan: 'info',
  emerald: 'success'
}

const getMetricTone = (tone) => toneMap[tone] || 'muted'

const normalizeMetaLines = (meta) => {
  if (Array.isArray(meta)) return meta.filter(Boolean)
  return meta ? [meta] : []
}

const buildGroupContext = (group) => {
  const lines = []

  if (group.panel.note) {
    lines.push(group.panel.note)
  }

  group.panel.stats.forEach((item) => {
    const detail = [item.description, ...normalizeMetaLines(item.meta).slice(0, 1)]
      .filter(Boolean)
      .join(' · ')

    if (detail) {
      lines.push(`${item.label}：${detail}`)
    }
  })

  return lines
}
</script>
