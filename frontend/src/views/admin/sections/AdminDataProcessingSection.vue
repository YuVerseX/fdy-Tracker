<template>
  <div class="space-y-6">
    <section class="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <div>
        <h2 class="text-lg font-semibold text-sky-900">{{ collectPanel.title }}</h2>
        <p class="mt-1 text-sm text-gray-500">{{ collectPanel.description }}</p>
        <p class="mt-2 text-xs text-gray-500">{{ collectPanel.note }}</p>
        <p class="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
          默认参数已经覆盖日常操作。只有在需要缩小范围或调整批量时，再展开下面的设置。
        </p>
      </div>

      <div class="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div v-for="item in collectPanel.stats" :key="item.label" class="rounded-lg bg-slate-50 px-4 py-3">
          <div class="text-xs text-gray-500">{{ item.label }}</div>
          <div class="mt-1 text-lg font-semibold text-slate-900">{{ item.value }}</div>
        </div>
      </div>

      <div class="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <article class="rounded-lg border border-sky-200 bg-sky-50 p-5">
          <div>
            <h3 class="text-base font-semibold text-sky-900">立即抓取最新数据</h3>
            <p class="mt-1 text-sm text-sky-800">把最新公告尽快拉进系统，直接进入基础链路。</p>
          </div>
          <div class="mt-4 flex flex-wrap gap-2 text-xs">
            <span class="rounded-full bg-white/80 px-3 py-1 font-medium text-sky-800">数据源：{{ getSourceLabel(scrapeForm.sourceId, '默认数据源') }}</span>
            <span class="rounded-full bg-white/80 px-3 py-1 font-medium text-sky-800">抓取 {{ formatCountLabel(scrapeForm.maxPages, '页') }}</span>
          </div>
          <button type="button" :disabled="scrapeBusy" class="mt-5 inline-flex items-center justify-center rounded-lg bg-sky-700 px-4 py-2.5 text-white transition-colors duration-200 hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-60" @click="runScrapeTask">
            {{ scrapeBusy ? '抓取中...' : '立即抓取最新数据' }}
          </button>
          <details class="mt-4 rounded-lg border border-sky-100 bg-white/70 px-4 py-3">
            <summary class="cursor-pointer list-none text-sm font-medium text-sky-800">调整抓取范围</summary>
            <div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label class="mb-2 block text-sm font-medium text-gray-700">数据源</label>
                <select v-model.number="scrapeForm.sourceId" class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-sky-600">
                  <option v-for="source in sourceOptions" :key="source.value" :value="source.value" :disabled="source.isActive === false">
                    {{ source.label }}
                  </option>
                </select>
              </div>
              <div>
                <label class="mb-2 block text-sm font-medium text-gray-700">抓取页数</label>
                <input v-model.number="scrapeForm.maxPages" type="number" min="1" max="20" class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-sky-600">
              </div>
            </div>
          </details>
        </article>

        <article class="rounded-lg border border-amber-200 bg-amber-50 p-5">
          <div>
            <h3 class="text-base font-semibold text-amber-900">补处理历史附件</h3>
            <p class="mt-1 text-sm text-amber-800">给历史数据补附件发现、下载和解析结果。</p>
          </div>
          <div class="mt-4 flex flex-wrap gap-2 text-xs">
            <span class="rounded-full bg-white/80 px-3 py-1 font-medium text-amber-800">数据源：{{ getSourceLabel(backfillForm.sourceId, '全部数据源') }}</span>
            <span class="rounded-full bg-white/80 px-3 py-1 font-medium text-amber-800">单次补 {{ formatCountLabel(backfillForm.limit, '条') }}</span>
          </div>
          <button type="button" :disabled="backfillBusy" class="mt-5 inline-flex items-center justify-center rounded-lg bg-amber-600 px-4 py-2.5 text-white transition-colors duration-200 hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-60" @click="runBackfillTask">
            {{ backfillBusy ? '补处理中...' : '补处理历史附件' }}
          </button>
          <details class="mt-4 rounded-lg border border-amber-100 bg-white/70 px-4 py-3">
            <summary class="cursor-pointer list-none text-sm font-medium text-amber-800">调整补处理范围</summary>
            <div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label class="mb-2 block text-sm font-medium text-gray-700">数据源</label>
                <select v-model="backfillForm.sourceId" class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-amber-600">
                  <option value="">全部数据源</option>
                  <option v-for="source in sourceOptions" :key="`backfill-${source.value}`" :value="String(source.value)" :disabled="source.isActive === false">
                    {{ source.label }}
                  </option>
                </select>
              </div>
              <div>
                <label class="mb-2 block text-sm font-medium text-gray-700">处理条数上限</label>
                <input v-model.number="backfillForm.limit" type="number" min="1" max="1000" class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-amber-600">
              </div>
            </div>
          </details>
        </article>
      </div>
    </section>

    <section class="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h2 class="text-lg font-semibold text-sky-900">{{ duplicatePanel.title }}</h2>
          <p class="mt-1 text-sm text-gray-500">{{ duplicatePanel.description }}</p>
          <p class="mt-2 text-xs text-gray-500">{{ duplicatePanel.note }}</p>
        </div>
        <button type="button" :disabled="duplicateLoading" class="inline-flex items-center justify-center rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60" @click="refreshDuplicateSummary">
          {{ duplicateLoading ? '刷新中...' : '刷新重复摘要' }}
        </button>
      </div>

      <div class="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div v-for="item in duplicatePanel.stats" :key="item.label" class="rounded-lg bg-slate-50 px-4 py-3">
          <div class="text-xs text-gray-500">{{ item.label }}</div>
          <div class="mt-1 text-lg font-semibold text-slate-900">{{ item.value }}</div>
        </div>
      </div>

      <div class="mt-6 rounded-lg border border-slate-200 bg-slate-50 p-4">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h3 class="text-base font-semibold text-slate-900">补齐去重检查</h3>
            <p class="mt-1 text-sm text-gray-600">默认只需要确认本次补齐批量，其他逻辑保持系统默认。</p>
            <div class="mt-3 flex flex-wrap gap-2 text-xs">
              <span class="rounded-full bg-white px-3 py-1 font-medium text-slate-700">单次补齐 {{ formatCountLabel(duplicateForm.limit, '条') }}</span>
            </div>
          </div>
          <button type="button" :disabled="duplicateBusy" class="inline-flex items-center justify-center rounded-lg bg-sky-700 px-4 py-2.5 text-white transition-colors duration-200 hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-60" @click="runDuplicateBackfillTask">
            {{ duplicateBusy ? '补齐中...' : '补齐去重检查' }}
          </button>
        </div>
        <details class="mt-4 rounded-lg border border-slate-200 bg-white px-4 py-3">
          <summary class="cursor-pointer list-none text-sm font-medium text-slate-700">调整单次批量</summary>
          <div class="mt-4 max-w-sm">
            <label class="mb-2 block text-sm font-medium text-gray-700">单次补齐条数</label>
            <input v-model.number="duplicateForm.limit" type="number" min="1" max="2000" class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-sky-600">
          </div>
        </details>
      </div>
    </section>

    <section class="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h2 class="text-lg font-semibold text-sky-900">{{ analysisPanel.title }}</h2>
          <p class="mt-1 text-sm text-gray-500">{{ analysisPanel.description }}</p>
          <p class="mt-2 text-xs text-gray-500">{{ analysisPanel.note }}</p>
        </div>
        <button type="button" :disabled="analysisLoading" class="inline-flex items-center justify-center rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60" @click="refreshAnalysisSummary">
          {{ analysisLoading ? '刷新中...' : '刷新分析摘要' }}
        </button>
      </div>

      <div class="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div v-for="item in analysisPanel.stats" :key="item.label" class="rounded-lg bg-slate-50 px-4 py-3">
          <div class="text-xs text-gray-500">{{ item.label }}</div>
          <div class="mt-1 text-lg font-semibold text-slate-900">{{ item.value }}</div>
        </div>
      </div>

      <div class="mt-6 rounded-lg border border-sky-100 bg-sky-50/70 p-4">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h3 class="text-base font-semibold text-sky-900">补齐基础分析</h3>
            <p class="mt-1 text-sm text-sky-800">这一步只补基础结构化结果，无 AI 时也可以正常执行。</p>
            <div class="mt-3 flex flex-wrap gap-2 text-xs">
              <span class="rounded-full bg-white px-3 py-1 font-medium text-sky-800">数据源：{{ getSourceLabel(baseAnalysisForm.sourceId, '全部数据源') }}</span>
              <span class="rounded-full bg-white px-3 py-1 font-medium text-sky-800">单次补 {{ formatCountLabel(baseAnalysisForm.limit, '条') }}</span>
              <span class="rounded-full bg-white px-3 py-1 font-medium text-sky-800">{{ baseAnalysisForm.onlyPending ? '只补待处理内容' : '包含已处理内容' }}</span>
            </div>
          </div>
          <button type="button" :disabled="baseAnalysisBusy" class="inline-flex items-center justify-center rounded-lg bg-sky-700 px-4 py-2.5 text-white transition-colors duration-200 hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-60" @click="runBaseAnalysisTask">
            {{ baseAnalysisBusy ? '补齐中...' : '补齐基础分析' }}
          </button>
        </div>
        <details class="mt-4 rounded-lg border border-sky-100 bg-white px-4 py-3">
          <summary class="cursor-pointer list-none text-sm font-medium text-sky-800">调整分析范围</summary>
          <div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label class="mb-2 block text-sm font-medium text-gray-700">数据源</label>
              <select v-model="baseAnalysisForm.sourceId" class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-sky-600">
                <option value="">全部数据源</option>
                <option v-for="source in sourceOptions" :key="`base-${source.value}`" :value="String(source.value)" :disabled="source.isActive === false">
                  {{ source.label }}
                </option>
              </select>
            </div>
            <div>
              <label class="mb-2 block text-sm font-medium text-gray-700">处理条数上限</label>
              <input v-model.number="baseAnalysisForm.limit" type="number" min="1" max="1000" class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-sky-600">
            </div>
            <div class="flex items-end">
              <label class="inline-flex cursor-pointer items-center text-sm text-gray-700">
                <input v-model="baseAnalysisForm.onlyPending" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-sky-600 focus:ring-sky-500">
                <span class="ml-2">只补待处理内容</span>
              </label>
            </div>
          </div>
        </details>
      </div>
    </section>

    <section class="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h2 class="text-lg font-semibold text-sky-900">{{ jobsPanel.title }}</h2>
          <p class="mt-1 text-sm text-gray-500">{{ jobsPanel.description }}</p>
          <p class="mt-2 text-xs text-gray-500">{{ jobsPanel.note }}</p>
        </div>
        <button type="button" :disabled="jobsLoading" class="inline-flex items-center justify-center rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60" @click="refreshJobSummary">
          {{ jobsLoading ? '刷新中...' : '刷新岗位摘要' }}
        </button>
      </div>

      <div class="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-5">
        <div v-for="item in jobsPanel.stats" :key="item.label" class="rounded-lg bg-slate-50 px-4 py-3">
          <div class="text-xs text-gray-500">{{ item.label }}</div>
          <div class="mt-1 text-lg font-semibold text-slate-900">{{ item.value }}</div>
        </div>
      </div>

      <div class="mt-6 rounded-lg border border-cyan-100 bg-cyan-50/70 p-4">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h3 class="text-base font-semibold text-cyan-900">补齐岗位索引</h3>
            <p class="mt-1 text-sm text-cyan-800">优先补正文和附件里本地可恢复的岗位信息，AI 只是后续增强。</p>
            <div class="mt-3 flex flex-wrap gap-2 text-xs">
              <span class="rounded-full bg-white px-3 py-1 font-medium text-cyan-800">数据源：{{ getSourceLabel(jobIndexForm.sourceId, '全部数据源') }}</span>
              <span class="rounded-full bg-white px-3 py-1 font-medium text-cyan-800">单次补 {{ formatCountLabel(jobIndexForm.limit, '条') }}</span>
              <span class="rounded-full bg-white px-3 py-1 font-medium text-cyan-800">{{ jobIndexForm.onlyPending ? '只补待处理内容' : '包含已处理内容' }}</span>
            </div>
          </div>
          <button type="button" :disabled="jobIndexBusy" class="inline-flex items-center justify-center rounded-lg bg-cyan-600 px-4 py-2.5 text-white transition-colors duration-200 hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-60" @click="runJobIndexTask">
            {{ jobIndexBusy ? '补齐中...' : '补齐岗位索引' }}
          </button>
        </div>
        <details class="mt-4 rounded-lg border border-cyan-100 bg-white px-4 py-3">
          <summary class="cursor-pointer list-none text-sm font-medium text-cyan-800">调整索引范围</summary>
          <div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label class="mb-2 block text-sm font-medium text-gray-700">数据源</label>
              <select v-model="jobIndexForm.sourceId" class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-cyan-600">
                <option value="">全部数据源</option>
                <option v-for="source in sourceOptions" :key="`job-${source.value}`" :value="String(source.value)" :disabled="source.isActive === false">
                  {{ source.label }}
                </option>
              </select>
            </div>
            <div>
              <label class="mb-2 block text-sm font-medium text-gray-700">处理条数上限</label>
              <input v-model.number="jobIndexForm.limit" type="number" min="1" max="1000" class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-cyan-600">
            </div>
            <div class="flex items-end">
              <label class="inline-flex cursor-pointer items-center text-sm text-gray-700">
                <input v-model="jobIndexForm.onlyPending" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-cyan-600 focus:ring-cyan-500">
                <span class="ml-2">只补待处理内容</span>
              </label>
            </div>
          </div>
        </details>

        <p v-if="jobsSummaryUnavailable" class="mt-3 text-xs text-amber-700">
          后端还没开放岗位摘要接口，当前先显示占位值，不影响基础索引操作。
        </p>
      </div>
    </section>
  </div>
</template>

<script setup>
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

const formatCountLabel = (value, unit) => {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? `${numeric}${unit}` : `--${unit}`
}

const getSourceLabel = (sourceId, fallback) => {
  if (sourceId === '' || sourceId === null || sourceId === undefined) return fallback
  const matched = props.sourceOptions.find((source) => String(source.value) === String(sourceId))
  return matched?.label || fallback
}
</script>
