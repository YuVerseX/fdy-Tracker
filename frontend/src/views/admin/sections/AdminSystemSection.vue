<template>
  <section class="rounded-[28px] border border-slate-200 bg-white/90 p-6 shadow-sm">
    <div class="flex items-start justify-between gap-4">
      <div>
        <AppSectionHeader
          title="系统设置"
          description="设置自动抓取频率和默认抓取范围。"
          aside="自动抓取和手动处理互不影响；这里只控制系统默认行为。"
        />
      </div>
      <AppStatusBadge :label="statusBadgeLabel" :tone="schedulerForm.enabled ? 'success' : 'warning'" />
    </div>

    <div class="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-3">
      <AppStatCard
        v-for="card in summaryCards"
        :key="card.label"
        :label="card.label"
        :value="card.value"
        :meta="card.meta"
        size="sm"
        class="bg-slate-50"
      />
    </div>

    <div class="mt-4 rounded-lg border px-4 py-3 text-sm" :class="noticeClass">
      <p>{{ statusLine }}</p>
      <p class="mt-1 text-xs opacity-80">{{ nextRunLine }}</p>
    </div>

    <AppNotice
      class="mt-4"
      :tone="helperNotice.tone"
      :description="helperNotice.description"
    />

    <div class="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-4">
      <div>
        <label class="mb-2 block text-sm font-medium text-gray-700">默认数据源</label>
        <select v-model.number="schedulerForm.defaultSourceId" class="w-full rounded-2xl border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-sky-600">
          <option v-for="source in sourceOptions" :key="`scheduler-${source.value}`" :value="source.value">
            {{ source.label }}
          </option>
        </select>
      </div>
      <div>
        <label class="mb-2 block text-sm font-medium text-gray-700">抓取间隔（秒）</label>
        <input v-model.number="schedulerForm.intervalSeconds" type="number" min="60" max="86400" class="w-full rounded-2xl border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-sky-600">
      </div>
      <div>
        <label class="mb-2 block text-sm font-medium text-gray-700">默认抓取页数</label>
        <input v-model.number="schedulerForm.defaultMaxPages" type="number" min="1" max="50" class="w-full rounded-2xl border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-sky-600">
      </div>
      <div class="flex items-end">
        <label class="inline-flex cursor-pointer items-center text-sm text-gray-700">
          <input v-model="schedulerForm.enabled" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-sky-600 focus:ring-sky-500">
          <span class="ml-2">启用定时抓取</span>
        </label>
      </div>
    </div>

    <div class="mt-6 flex flex-wrap gap-3">
      <AppActionButton
        label="保存配置"
        busy-label="保存中..."
        :busy="schedulerSaving"
        variant="primary"
        @click="saveSchedulerConfig"
      />
      <AppActionButton
        label="刷新配置"
        busy-label="刷新中..."
        :busy="schedulerLoading"
        @click="refreshSchedulerConfig"
      />
    </div>
  </section>
</template>

<script setup>
import AppActionButton from '../../../components/ui/AppActionButton.vue'
import AppNotice from '../../../components/ui/AppNotice.vue'
import AppSectionHeader from '../../../components/ui/AppSectionHeader.vue'
import AppStatCard from '../../../components/ui/AppStatCard.vue'
import AppStatusBadge from '../../../components/ui/AppStatusBadge.vue'

defineProps({
  schedulerForm: { type: Object, required: true },
  schedulerLoaded: { type: Boolean, required: true },
  schedulerLoading: { type: Boolean, required: true },
  schedulerSaving: { type: Boolean, required: true },
  sourceOptions: { type: Array, required: true },
  statusBadgeLabel: { type: String, required: true },
  summaryCards: { type: Array, required: true },
  helperNotice: { type: Object, required: true },
  noticeClass: { type: String, required: true },
  statusLine: { type: String, required: true },
  nextRunLine: { type: String, required: true },
  saveSchedulerConfig: { type: Function, required: true },
  refreshSchedulerConfig: { type: Function, required: true }
})
</script>
