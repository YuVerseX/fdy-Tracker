<template>
  <section class="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
    <div class="flex items-start justify-between gap-4">
      <div>
        <h2 class="text-lg font-semibold text-sky-900">系统配置</h2>
        <p class="mt-1 text-sm text-gray-500">控制自动抓取是否开启、多久跑一次，以及默认抓取范围。</p>
      </div>
      <span class="inline-flex items-center rounded-full bg-violet-100 px-3 py-1 text-xs font-medium text-violet-700">
        调度配置
      </span>
    </div>

    <div class="mt-4 rounded-lg border px-4 py-3 text-sm" :class="noticeClass">
      <p>{{ statusLine }}</p>
      <p class="mt-1 text-xs opacity-80">{{ nextRunLine }}</p>
    </div>

    <div class="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-4">
      <div>
        <label class="mb-2 block text-sm font-medium text-gray-700">默认数据源</label>
        <select v-model.number="schedulerForm.defaultSourceId" class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-violet-600">
          <option v-for="source in sourceOptions" :key="`scheduler-${source.value}`" :value="source.value">
            {{ source.label }}
          </option>
        </select>
      </div>
      <div>
        <label class="mb-2 block text-sm font-medium text-gray-700">抓取间隔（秒）</label>
        <input v-model.number="schedulerForm.intervalSeconds" type="number" min="60" max="86400" class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-violet-600">
      </div>
      <div>
        <label class="mb-2 block text-sm font-medium text-gray-700">默认抓取页数</label>
        <input v-model.number="schedulerForm.defaultMaxPages" type="number" min="1" max="50" class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-violet-600">
      </div>
      <div class="flex items-end">
        <label class="inline-flex cursor-pointer items-center text-sm text-gray-700">
          <input v-model="schedulerForm.enabled" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-violet-600 focus:ring-violet-500">
          <span class="ml-2">启用定时抓取</span>
        </label>
      </div>
    </div>

    <div class="mt-6 flex flex-wrap gap-3">
      <button type="button" :disabled="schedulerSaving" class="inline-flex items-center justify-center rounded-lg bg-violet-600 px-4 py-2.5 text-white transition-colors duration-200 hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60" @click="saveSchedulerConfig">
        {{ schedulerSaving ? '保存中...' : '保存配置' }}
      </button>
      <button type="button" :disabled="schedulerLoading" class="inline-flex items-center justify-center rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-700 transition-colors duration-200 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60" @click="refreshSchedulerConfig">
        {{ schedulerLoading ? '刷新中...' : '刷新配置' }}
      </button>
    </div>
  </section>
</template>

<script setup>
defineProps({
  schedulerForm: { type: Object, required: true },
  schedulerLoaded: { type: Boolean, required: true },
  schedulerLoading: { type: Boolean, required: true },
  schedulerSaving: { type: Boolean, required: true },
  sourceOptions: { type: Array, required: true },
  noticeClass: { type: String, required: true },
  statusLine: { type: String, required: true },
  nextRunLine: { type: String, required: true },
  saveSchedulerConfig: { type: Function, required: true },
  refreshSchedulerConfig: { type: Function, required: true }
})
</script>
