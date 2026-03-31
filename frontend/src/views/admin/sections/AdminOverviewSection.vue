<template>
  <div class="space-y-6">
    <section class="rounded-[28px] border p-6 shadow-sm" :class="health.panelClass">
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

      <div class="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <AppStatCard
          v-for="card in cards"
          :key="card.id"
          :label="card.label"
          :value="card.value"
          :meta="card.meta"
          value-tone="info"
          class="border-0 bg-white/88 shadow-sm ring-1 ring-black/5"
        />
      </div>

      <div class="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <article v-for="item in focusItems" :key="item.id" class="rounded-2xl border border-white/70 bg-white/80 px-4 py-4 shadow-sm">
          <div class="text-xs font-medium tracking-[0.12em] text-slate-500 uppercase">{{ item.title }}</div>
          <p class="mt-2 text-sm leading-6 text-slate-700">{{ item.description }}</p>
        </article>
      </div>

      <div v-if="health.alerts.length > 0" class="mt-4 rounded-lg border border-amber-200 bg-white/80 px-4 py-4 text-sm text-amber-900">
        <div class="font-medium">当前需要注意</div>
        <div class="mt-3 space-y-2">
          <div v-for="item in health.alerts" :key="item" class="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
            {{ item }}
          </div>
        </div>
      </div>
    </section>

    <section class="rounded-[28px] border border-slate-200 bg-white/90 p-6 shadow-sm">
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

      <div class="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <AppStatCard
          v-for="card in structuredFieldCards"
          :key="card.label"
          :label="card.label"
          :value="card.value"
          size="sm"
        />
      </div>
    </section>
  </div>
</template>

<script setup>
import AppActionButton from '../../../components/ui/AppActionButton.vue'
import AppSectionHeader from '../../../components/ui/AppSectionHeader.vue'
import AppStatCard from '../../../components/ui/AppStatCard.vue'
import AppStatusBadge from '../../../components/ui/AppStatusBadge.vue'

defineProps({
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

const getHealthTone = (level) => {
  if (level === 'healthy') return 'success'
  if (level === 'warning') return 'danger'
  if (level === 'attention') return 'warning'
  return 'neutral'
}
</script>
