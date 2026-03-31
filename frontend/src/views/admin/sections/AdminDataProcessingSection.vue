<template>
  <div class="space-y-6">
    <AppNotice
      tone="info"
      title="建议顺序"
      description="先抓取最新公告，再按需要补附件、关键信息和岗位；只有在需要缩小范围时再展开更多设置。"
    />

    <section
      v-for="group in groups"
      :key="group.id"
      class="rounded-[28px] border border-slate-200 bg-white/90 p-6 shadow-sm"
    >
      <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <AppSectionHeader
          :title="group.panel.title"
          :description="group.panel.description"
          :aside="group.helper"
        />
        <AppActionButton
          v-if="group.refreshAction"
          :label="group.refreshAction.label"
          :busy-label="group.refreshAction.busyLabel"
          :busy="group.refreshAction.busy"
          :disabled="group.refreshAction.disabled"
          @click="group.refreshAction.onClick?.()"
        />
      </div>

      <div class="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <AppStatCard
          v-for="item in group.panel.stats"
          :key="item.label"
          :label="item.label"
          :value="item.value"
          :description="item.description"
          :meta="item.meta"
          size="sm"
          class="border-0 bg-slate-50"
        />
      </div>

      <div class="mt-6 grid grid-cols-1 gap-5 xl:grid-cols-2">
        <AdminTaskActionCard
          v-for="card in group.cards"
          :key="card.id"
          :card="card"
        />
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'

import AppActionButton from '../../../components/ui/AppActionButton.vue'
import AppNotice from '../../../components/ui/AppNotice.vue'
import AppSectionHeader from '../../../components/ui/AppSectionHeader.vue'
import AppStatCard from '../../../components/ui/AppStatCard.vue'
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
</script>
