<template>
  <div class="space-y-5">
    <AppSurface padding="lg" :class="health.panelClass">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <AppSectionHeader title="当前概况" description="查看最近任务、自动抓取状态和关键结果。">
            <template #badge>
              <AppStatusBadge :label="health.label" :tone="getHealthTone(health.level)" />
            </template>
          </AppSectionHeader>
          <p class="mt-2 text-sm" :class="health.textClass">{{ health.summary }}</p>
        </div>
        <AppActionButton
          label="刷新总览"
          busy-label="刷新中..."
          :busy="refreshing"
          @click="refreshOverview"
        />
      </div>

      <div class="mt-5 flex flex-wrap gap-2">
        <AppMetricPill
          v-for="card in cards"
          :key="card.id"
          :label="card.label"
          :value="card.value"
          :tone="getOverviewMetricTone(card.id)"
        />
      </div>

      <div class="mt-5 grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <AppNotice
          :tone="health.alerts.length > 0 ? 'warning' : 'info'"
          :title="health.alerts.length > 0 ? '当前需要注意' : '当前状态说明'"
          :description="health.alerts[0] || health.summary"
        />

        <div class="rounded-[18px] border border-[rgba(148,163,184,0.18)] bg-white/76 px-4 py-4">
          <div class="text-xs font-medium tracking-[0.12em] text-slate-500 uppercase">接下来建议</div>
          <AppFactList class="mt-3" :items="focusFactItems" :columns="1" compact tone="muted" />
        </div>
      </div>

      <div v-if="health.alerts.length > 1" class="mt-4 flex flex-wrap gap-2">
        <AppMetricPill
          v-for="item in health.alerts.slice(1)"
          :key="item"
          :label="item"
          tone="warning"
        />
      </div>
    </AppSurface>

    <AppSurface padding="lg">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <AppSectionHeader title="整理结果" :description="runtimeCopy.description">
            <template #badge>
              <AppStatusBadge :label="runtimeCopy.badge" tone="info" />
            </template>
          </AppSectionHeader>
          <p class="mt-2 text-xs text-gray-500">{{ runtimeCopy.emphasis }}</p>
        </div>
        <AppActionButton
          label="刷新关键信息字段"
          busy-label="刷新中..."
          :busy="structureRefreshLabel === '刷新中...'"
          @click="refreshStructuredSummary"
        />
      </div>

      <AppNotice
        class="mt-5"
        tone="info"
        title="当前整理能力"
        :description="runtimeCopy.emphasis"
      />

      <AppFactList class="mt-5" :items="structuredFieldItems" compact />
    </AppSurface>
  </div>
</template>

<script setup>
import { computed } from 'vue'

import AppActionButton from '../../../components/ui/AppActionButton.vue'
import AppFactList from '../../../components/ui/AppFactList.vue'
import AppMetricPill from '../../../components/ui/AppMetricPill.vue'
import AppNotice from '../../../components/ui/AppNotice.vue'
import AppSectionHeader from '../../../components/ui/AppSectionHeader.vue'
import AppStatusBadge from '../../../components/ui/AppStatusBadge.vue'
import AppSurface from '../../../components/ui/AppSurface.vue'

const props = defineProps({
  health: { type: Object, required: true },
  refreshing: { type: Boolean, required: true },
  focusItems: { type: Array, required: true },
  cards: { type: Array, required: true },
  runtimeCopy: { type: Object, required: true },
  structuredFieldCards: { type: Array, required: true },
  structureRefreshLabel: { type: String, required: true },
  refreshOverview: { type: Function, required: true },
  refreshStructuredSummary: { type: Function, required: true }
})

const focusFactItems = computed(() => props.focusItems.map((item) => ({
  label: item.title,
  value: item.description
})))

const structuredFieldItems = computed(() => props.structuredFieldCards.map((card) => ({
  label: card.label,
  value: card.value
})))

const getHealthTone = (level) => {
  if (level === 'healthy') return 'success'
  if (level === 'warning') return 'danger'
  if (level === 'attention') return 'warning'
  return 'neutral'
}

const getOverviewMetricTone = (cardId) => {
  if (cardId === 'scheduler') return props.health.level === 'warning' ? 'warning' : 'success'
  if (cardId === 'runtime') return 'info'
  if (cardId === 'jobs') return 'info'
  return 'muted'
}
</script>
