<template>
  <AppSurface padding="lg">
    <div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
      <AppSectionHeader
        title="系统设置"
        description="设置自动抓取频率和默认抓取范围。"
        aside="自动抓取和手动处理互不影响；这里只控制系统默认行为。"
      />
      <AppStatusBadge
        class="md:shrink-0"
        :label="statusBadgeLabel"
        :tone="schedulerForm.enabled ? 'success' : 'warning'"
      />
    </div>

    <div class="mt-4 flex flex-wrap gap-2">
      <AppMetricPill
        v-for="card in summaryCards"
        :key="card.label"
        :label="card.label"
        :value="card.value"
        :tone="card.label === '当前状态' ? (schedulerForm.enabled ? 'success' : 'warning') : 'muted'"
      />
    </div>

    <AppFactList class="mt-4" :items="scheduleFacts" compact />

    <div class="mt-4 rounded-lg border px-4 py-3 text-sm" :class="noticeClass">
      <p>{{ statusLine }}</p>
      <p class="mt-1 text-xs opacity-80">{{ nextRunLine }}</p>
    </div>

    <AppNotice
      v-if="schedulerRefreshNotice"
      class="mt-4"
      :tone="schedulerRefreshNotice.tone"
      :title="schedulerRefreshNotice.title"
      :description="schedulerRefreshNotice.description"
      :announce="true"
    >
      <template #actions>
        <AppActionButton
          label="刷新配置"
          busy-label="刷新中..."
          :busy="schedulerLoading"
          @click="refreshSchedulerConfig"
        />
      </template>
    </AppNotice>

    <AppNotice
      v-if="saveBlockedReason"
      class="mt-4"
      tone="warning"
      title="保存前先同步当前配置"
      :description="saveBlockedReason"
      :announce="true"
    >
      <template #actions>
        <AppActionButton
          label="刷新配置"
          busy-label="刷新中..."
          :busy="schedulerLoading"
          @click="refreshSchedulerConfig"
        />
      </template>
    </AppNotice>

    <AppNotice
      class="mt-4"
      :tone="helperNotice.tone"
      title="生效说明"
      :description="helperNotice.description"
    />

    <div class="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
      <div class="md:col-span-2 xl:col-span-2">
        <label for="scheduler-default-source" class="mb-2 block text-sm font-medium text-gray-700">默认数据源</label>
        <select id="scheduler-default-source" v-model.number="schedulerForm.defaultSourceId" class="app-select">
          <option v-for="source in sourceOptions" :key="`scheduler-${source.value}`" :value="source.value">
            {{ source.label }}
          </option>
        </select>
      </div>
      <div>
        <label for="scheduler-interval-seconds" class="mb-2 block text-sm font-medium text-gray-700">抓取间隔（秒）</label>
        <input id="scheduler-interval-seconds" v-model.number="schedulerForm.intervalSeconds" type="number" min="60" max="86400" class="app-input">
      </div>
      <div>
        <label for="scheduler-default-max-pages" class="mb-2 block text-sm font-medium text-gray-700">默认抓取页数</label>
        <input id="scheduler-default-max-pages" v-model.number="schedulerForm.defaultMaxPages" type="number" min="1" max="50" class="app-input">
      </div>
      <div class="flex items-center md:col-span-2 xl:col-span-4">
        <input id="scheduler-enabled" v-model="schedulerForm.enabled" type="checkbox" class="app-checkbox">
        <label for="scheduler-enabled" class="ml-2 cursor-pointer text-sm text-gray-700">启用定时抓取</label>
      </div>
    </div>

    <div class="mt-6 flex flex-wrap gap-3">
      <AppActionButton
        label="保存配置"
        busy-label="保存中..."
        :busy="schedulerSaving"
        :disabled="saveDisabled"
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
  </AppSurface>
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
  saveDisabled: { type: Boolean, required: true },
  saveBlockedReason: { type: String, required: true },
  schedulerRefreshNotice: { type: Object, default: null },
  saveSchedulerConfig: { type: Function, required: true },
  refreshSchedulerConfig: { type: Function, required: true }
})

const getSummaryCardValue = (label, fallback = '未获取') => (
  props.summaryCards.find((card) => card.label === label)?.value || fallback
)

const scheduleFacts = computed(() => [
  {
    label: '默认数据源',
    value: props.sourceOptions.find((source) => Number(source.value) === Number(props.schedulerForm.defaultSourceId))?.label || '默认数据源'
  },
  {
    label: '抓取间隔',
    value: props.schedulerLoaded ? `${props.schedulerForm.intervalSeconds || '--'} 秒` : '加载中'
  },
  {
    label: '默认抓取页数',
    value: props.schedulerLoaded ? `${props.schedulerForm.defaultMaxPages || '--'} 页` : '加载中'
  },
  {
    label: '下次预计运行',
    value: props.schedulerLoaded ? getSummaryCardValue('下次运行') : '加载中'
  }
])
</script>
