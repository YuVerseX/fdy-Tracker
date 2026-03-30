<template>
  <div class="space-y-6">
    <section class="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div class="flex flex-wrap items-center gap-3">
            <h2 class="text-lg font-semibold text-sky-900">AI 增强</h2>
            <span class="inline-flex items-center rounded-full px-3 py-1 text-xs font-medium" :class="openaiReady ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-800'">
              {{ runtimeCopy.badge }}
            </span>
          </div>
          <p class="mt-2 text-sm text-gray-600">{{ runtimeCopy.description }}</p>
          <p class="mt-2 text-xs" :class="openaiReady ? 'text-emerald-700' : 'text-amber-700'">
            {{ openaiReady ? runtimeCopy.emphasis : disabledReason }}
          </p>
        </div>
      </div>

      <div class="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article v-for="panel in panels" :key="panel.id" class="rounded-lg border px-4 py-4" :class="panel.disabled ? 'border-slate-200 bg-slate-50' : 'border-emerald-200 bg-emerald-50/60'">
          <div class="flex items-start justify-between gap-3">
            <div class="text-sm font-medium text-slate-900">{{ panel.title }}</div>
            <span class="inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-medium" :class="panel.disabled ? 'bg-slate-200 text-slate-700' : 'bg-emerald-100 text-emerald-700'">
              {{ panel.disabled ? '未开启' : '可用' }}
            </span>
          </div>
          <div class="mt-3 text-2xl font-semibold text-slate-900">{{ panel.value }}</div>
          <p class="mt-2 text-sm text-slate-600">{{ panel.helper }}</p>
          <p class="mt-1 text-xs text-slate-500">{{ panel.meta }}</p>
          <p v-if="panel.disabledReason" class="mt-3 text-xs text-amber-700">{{ panel.disabledReason }}</p>
        </article>
      </div>
    </section>

    <section class="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <div>
        <h2 class="text-lg font-semibold text-sky-900">AI 增强操作按钮</h2>
        <p class="mt-1 text-sm text-gray-500">基础链路已经可用时，再用这里的入口补更细的摘要、阶段判断和岗位识别。</p>
      </div>

      <div class="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <article class="rounded-lg border border-emerald-200 bg-emerald-50 p-5">
          <div>
            <h3 class="text-base font-semibold text-emerald-900">启动 AI 增强分析</h3>
            <p class="mt-1 text-sm text-emerald-800">针对已有基础结果继续补摘要、阶段判断和更细标签。</p>
          </div>
          <div class="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label class="mb-2 block text-sm font-medium text-gray-700">数据源</label>
              <select v-model="analysisForm.sourceId" class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-emerald-600">
                <option value="">全部数据源</option>
                <option v-for="source in sourceOptions" :key="`ai-analysis-${source.value}`" :value="String(source.value)" :disabled="source.isActive === false">
                  {{ source.label }}
                </option>
              </select>
            </div>
            <div>
              <label class="mb-2 block text-sm font-medium text-gray-700">处理条数上限</label>
              <input v-model.number="analysisForm.limit" type="number" min="1" max="500" class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-emerald-600">
            </div>
            <div class="flex items-end">
              <label class="inline-flex cursor-pointer items-center text-sm text-gray-700">
                <input v-model="analysisForm.onlyUnanalyzed" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500">
                <span class="ml-2">只跑未增强内容</span>
              </label>
            </div>
          </div>
          <div class="mt-5 flex flex-wrap gap-3">
            <button type="button" :disabled="analysisBusy || !openaiReady" class="inline-flex items-center justify-center rounded-lg bg-emerald-600 px-4 py-2.5 text-white transition-colors duration-200 hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60" @click="runAiAnalysisTask">
              {{ analysisBusy ? '增强中...' : '启动 AI 增强分析' }}
            </button>
            <button type="button" :disabled="analysisLoading" class="inline-flex items-center justify-center rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-700 transition-colors duration-200 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60" @click="refreshAnalysisSummary">
              {{ analysisLoading ? '刷新中...' : '刷新分析摘要' }}
            </button>
          </div>
          <p class="mt-3 text-xs text-gray-500">最近 AI 分析时间：{{ latestAnalysisLabel }}</p>
        </article>

        <article class="rounded-lg border border-cyan-200 bg-cyan-50 p-5">
          <div>
            <h3 class="text-base font-semibold text-cyan-900">启动 AI 岗位补抽</h3>
            <p class="mt-1 text-sm text-cyan-800">在正文和附件基础上，用 AI 补更难恢复的岗位识别。</p>
          </div>
          <div class="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label class="mb-2 block text-sm font-medium text-gray-700">数据源</label>
              <select v-model="jobsForm.sourceId" class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-cyan-600">
                <option value="">全部数据源</option>
                <option v-for="source in sourceOptions" :key="`ai-job-${source.value}`" :value="String(source.value)" :disabled="source.isActive === false">
                  {{ source.label }}
                </option>
              </select>
            </div>
            <div>
              <label class="mb-2 block text-sm font-medium text-gray-700">处理条数上限</label>
              <input v-model.number="jobsForm.limit" type="number" min="1" max="1000" class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-cyan-600">
            </div>
            <div class="flex items-end">
              <label class="inline-flex cursor-pointer items-center text-sm text-gray-700">
                <input v-model="jobsForm.onlyPending" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-cyan-600 focus:ring-cyan-500">
                <span class="ml-2">只补待处理内容</span>
              </label>
            </div>
          </div>
          <div class="mt-5 flex flex-wrap gap-3">
            <button type="button" :disabled="jobsBusy || !openaiReady" class="inline-flex items-center justify-center rounded-lg bg-cyan-600 px-4 py-2.5 text-white transition-colors duration-200 hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-60" @click="runAiJobExtractionTask">
              {{ jobsBusy ? '补抽中...' : '启动 AI 岗位补抽' }}
            </button>
            <button type="button" :disabled="jobsLoading" class="inline-flex items-center justify-center rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-700 transition-colors duration-200 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60" @click="refreshJobSummary">
              {{ jobsLoading ? '刷新中...' : '刷新岗位摘要' }}
            </button>
          </div>
          <p class="mt-3 text-xs text-gray-500">最近 AI 岗位补抽时间：{{ latestJobsLabel }}</p>
          <p v-if="jobsSummaryUnavailable" class="mt-2 text-xs text-amber-700">
            后端还没开放岗位摘要接口，当前先显示占位值，不影响 AI 补抽入口。
          </p>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
defineProps({
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
</script>
