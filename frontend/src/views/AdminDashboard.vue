<template>
  <div class="min-h-screen bg-sky-50">
    <header class="bg-white shadow-sm sticky top-0 z-10">
      <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-sky-900">管理台</h1>
          <p class="text-sm text-gray-500 mt-1">这里放运维动作，和普通列表页分开。</p>
        </div>
        <router-link
          :to="{ name: 'PostList' }"
          class="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors duration-200 hover:bg-gray-50"
        >
          返回前台
        </router-link>
      </div>
    </header>

    <main class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <div v-if="feedback.message" :class="feedbackClass" class="rounded-lg border px-4 py-3 text-sm">
        {{ feedback.message }}
      </div>
      <div
        v-if="activeTaskHints.length > 0"
        class="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
      >
        当前有任务运行中：{{ activeTaskHints.join('、') }}。可以先继续浏览，稍后点“刷新记录”看结果。
      </div>

      <section class="rounded-lg border p-6" :class="healthPanelClass">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div class="flex flex-wrap items-center gap-3">
              <h2 class="text-lg font-semibold">系统健康总览</h2>
              <span
                class="inline-flex items-center rounded-full px-3 py-1 text-xs font-medium"
                :class="healthBadgeClass"
              >
                {{ healthStatusLabel }}
              </span>
            </div>
            <p class="mt-2 text-sm" :class="healthTextClass">{{ healthStatusSummary }}</p>
          </div>
          <button
            @click="refreshOverview"
            :disabled="overviewRefreshing"
            class="inline-flex items-center justify-center rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors duration-200 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {{ overviewRefreshing ? '刷新中...' : '刷新总览' }}
          </button>
        </div>

        <div class="mt-6 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          <article class="rounded-lg bg-white/80 px-4 py-4 shadow-sm ring-1 ring-black/5">
            <div class="text-xs text-gray-500">定时抓取</div>
            <div class="mt-2 text-lg font-semibold text-sky-900">
              {{ schedulerForm.enabled ? '已启用' : '已关闭' }}
            </div>
            <div class="mt-1 text-xs text-gray-500">间隔 {{ formatIntervalLabel(schedulerForm.intervalSeconds) }}</div>
            <div class="mt-1 text-xs text-gray-500">
              {{ schedulerForm.nextRunAt ? `下次 ${formatDateTime(schedulerForm.nextRunAt)}` : '还没拿到下次运行时间' }}
            </div>
          </article>

          <article class="rounded-lg bg-white/80 px-4 py-4 shadow-sm ring-1 ring-black/5">
            <div class="text-xs text-gray-500">AI 分析</div>
            <div class="mt-2 text-lg font-semibold text-sky-900">
              {{ openaiReady ? '已就绪' : '未就绪' }}
            </div>
            <div class="mt-1 text-xs text-gray-500">模型 {{ analysisRuntime.model_name || '--' }}</div>
            <div class="mt-1 text-xs text-gray-500">待 OpenAI {{ analysisOverview.openai_pending_posts || 0 }} 条</div>
            <div class="mt-1 text-xs text-gray-500">待统计 {{ insightOverview.pending_insight_posts || 0 }} 条</div>
          </article>

          <article class="rounded-lg bg-white/80 px-4 py-4 shadow-sm ring-1 ring-black/5">
            <div class="text-xs text-gray-500">岗位索引</div>
            <div class="mt-2 text-lg font-semibold text-sky-900">
              {{ jobsOverview.total_jobs }} 个岗位
            </div>
            <div class="mt-1 text-xs text-gray-500">含岗位帖子 {{ jobsOverview.posts_with_jobs || 0 }} 条</div>
            <div class="mt-1 text-xs text-gray-500">待抽取 {{ jobsOverview.pending_posts || 0 }} 条</div>
          </article>

          <article class="rounded-lg bg-white/80 px-4 py-4 shadow-sm ring-1 ring-black/5">
            <div class="text-xs text-gray-500">最近任务</div>
            <div class="mt-2 text-sm font-semibold text-sky-900">
              {{ latestSuccessTask ? getTaskTypeLabel(latestSuccessTask.taskType) : '还没有成功记录' }}
            </div>
            <div class="mt-1 text-xs text-gray-500">
              {{ latestSuccessTask ? `${formatDateTime(latestSuccessTask.finishedAt)}（${latestSuccessText}）` : '先跑一次任务后再看这里' }}
            </div>
            <div v-if="latestFailedTask" class="mt-2 text-xs text-red-600">
              最近失败：{{ getTaskTypeLabel(latestFailedTask.taskType) }}，{{ latestFailedText }}
            </div>
          </article>
        </div>

        <div
          v-if="healthAlerts.length > 0"
          class="mt-4 rounded-lg border border-amber-200 bg-white/80 px-4 py-4 text-sm text-amber-900"
        >
          <div class="font-medium">当前需要注意</div>
          <div class="mt-3 space-y-2">
            <div
              v-for="item in healthAlerts"
              :key="item"
              class="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800"
            >
              {{ item }}
            </div>
          </div>
        </div>
      </section>

      <section class="bg-white rounded-lg shadow-sm p-6">
        <div class="flex items-center justify-between gap-4">
          <div>
            <h2 class="text-lg font-semibold text-sky-900">重复治理</h2>
            <p class="mt-1 text-sm text-gray-500">默认隐藏重复帖子，只保留主记录给前台使用。</p>
          </div>
          <button
            @click="fetchDuplicateSummary"
            :disabled="duplicateLoading"
            class="inline-flex items-center justify-center rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-700"
          >
            {{ duplicateLoading ? '刷新中...' : '刷新重复摘要' }}
          </button>
        </div>

        <div class="mt-6 grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div class="rounded-lg bg-rose-50 px-4 py-3">
            <div class="text-xs text-gray-500">重复组数</div>
            <div class="mt-1 text-xl font-semibold text-rose-700">{{ duplicateSummary.overview.duplicate_groups }}</div>
          </div>
          <div class="rounded-lg bg-amber-50 px-4 py-3">
            <div class="text-xs text-gray-500">折叠帖子</div>
            <div class="mt-1 text-xl font-semibold text-amber-700">{{ duplicateSummary.overview.duplicate_posts }}</div>
          </div>
          <div class="rounded-lg bg-emerald-50 px-4 py-3">
            <div class="text-xs text-gray-500">主记录</div>
            <div class="mt-1 text-xl font-semibold text-emerald-700">{{ duplicateSummary.overview.primary_posts }}</div>
          </div>
          <div class="rounded-lg bg-slate-50 px-4 py-3">
            <div class="text-xs text-gray-500">未检查</div>
            <div class="mt-1 text-xl font-semibold text-slate-700">{{ duplicateSummary.overview.unchecked_posts }}</div>
          </div>
        </div>

        <div class="mt-6 rounded-lg border border-slate-200 bg-slate-50 p-4">
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">单次补齐条数</label>
              <input
                v-model.number="duplicateBackfillForm.limit"
                type="number"
                min="1"
                max="2000"
                class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-600 focus:border-transparent"
              />
            </div>
            <div class="flex items-end justify-start sm:justify-end">
              <button
                @click="runDuplicateBackfillTask"
                :disabled="duplicateBackfillBusy"
                class="inline-flex items-center justify-center rounded-lg bg-sky-700 px-4 py-2.5 text-white transition-colors duration-200 hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {{ duplicateBackfillBusy ? '补齐中...' : '执行历史去重补齐' }}
              </button>
            </div>
          </div>
          <p class="mt-3 text-xs text-gray-500">
            用来处理“未检查”积压。建议先用 200~500 试跑，确认耗时后再逐步放大。
          </p>
        </div>
      </section>

      <section class="bg-white rounded-lg shadow-sm p-6">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h2 class="text-lg font-semibold text-sky-900">定时抓取配置</h2>
            <p class="mt-1 text-sm text-gray-500">控制自动抓取是否开启、多久跑一次、默认抓哪个源和抓几页。</p>
          </div>
          <span class="inline-flex items-center rounded-full bg-violet-100 px-3 py-1 text-xs font-medium text-violet-700">
            调度配置
          </span>
        </div>

        <div
          class="mt-4 rounded-lg border px-4 py-3 text-sm"
          :class="schedulerForm.enabled
            ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
            : 'border-gray-200 bg-gray-50 text-gray-700'"
        >
          <p>
            当前状态：{{ schedulerForm.enabled ? '已启用定时抓取' : '已停用定时抓取' }}；
            间隔 {{ formatIntervalLabel(schedulerForm.intervalSeconds) }}；
            默认抓 {{ schedulerForm.defaultMaxPages }} 页。
          </p>
          <p v-if="schedulerForm.nextRunAt" class="mt-1 text-xs opacity-80">
            下次预计运行：{{ formatDateTime(schedulerForm.nextRunAt) }}
          </p>
        </div>

        <div class="mt-6 grid grid-cols-1 lg:grid-cols-4 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">默认数据源</label>
            <select
              v-model.number="schedulerForm.defaultSourceId"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-violet-600 focus:border-transparent"
            >
              <option
                v-for="source in sourceOptions"
                :key="`scheduler-${source.value}`"
                :value="source.value"
              >
                {{ source.label }}
              </option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">抓取间隔（秒）</label>
            <input
              v-model.number="schedulerForm.intervalSeconds"
              type="number"
              min="60"
              max="86400"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-violet-600 focus:border-transparent"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">默认抓取页数</label>
            <input
              v-model.number="schedulerForm.defaultMaxPages"
              type="number"
              min="1"
              max="50"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-violet-600 focus:border-transparent"
            />
          </div>
          <div class="flex items-end">
            <label class="inline-flex items-center cursor-pointer text-sm text-gray-700">
              <input
                v-model="schedulerForm.enabled"
                type="checkbox"
                class="w-4 h-4 text-violet-600 border-gray-300 rounded focus:ring-violet-500 cursor-pointer"
              />
              <span class="ml-2">启用定时抓取</span>
            </label>
          </div>
        </div>

        <div class="mt-6 flex flex-wrap gap-3">
          <button
            @click="saveSchedulerConfig"
            :disabled="schedulerSaving"
            class="inline-flex items-center justify-center rounded-lg bg-violet-600 px-4 py-2.5 text-white transition-colors duration-200 hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {{ schedulerSaving ? '保存中...' : '保存配置' }}
          </button>
          <button
            @click="fetchSchedulerConfig"
            :disabled="schedulerLoading"
            class="inline-flex items-center justify-center rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-700 transition-colors duration-200 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {{ schedulerLoading ? '刷新中...' : '刷新配置' }}
          </button>
        </div>

        <p v-if="schedulerForm.updatedAt" class="mt-3 text-xs text-gray-500">
          最近配置更新时间：{{ formatDateTime(schedulerForm.updatedAt) }}
        </p>
      </section>

      <div class="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <section class="bg-white rounded-lg shadow-sm p-6">
          <div class="flex items-start justify-between gap-4">
            <div>
              <h2 class="text-lg font-semibold text-sky-900">手动抓取最新数据</h2>
              <p class="mt-1 text-sm text-gray-500">适合你想马上把最新公告抓进来时手动触发。</p>
            </div>
            <span class="inline-flex items-center rounded-full bg-sky-100 px-3 py-1 text-xs font-medium text-sky-700">
              抓取任务
            </span>
          </div>

          <div class="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">数据源</label>
              <select
                v-model.number="scrapeForm.sourceId"
                class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-600 focus:border-transparent"
              >
                <option
                  v-for="source in sourceOptions"
                  :key="source.value"
                  :value="source.value"
                  :disabled="source.isActive === false"
                >
                  {{ source.label }}
                </option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">抓取页数</label>
              <input
                v-model.number="scrapeForm.maxPages"
                type="number"
                min="1"
                max="50"
                class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-600 focus:border-transparent"
              />
            </div>
          </div>

          <button
            @click="runScrapeTask"
            :disabled="scrapeBusy"
            class="mt-6 inline-flex items-center justify-center rounded-lg bg-sky-700 px-4 py-2.5 text-white transition-colors duration-200 hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {{ scrapeBusy ? '抓取中...' : '开始抓取' }}
          </button>
        </section>

        <section class="bg-white rounded-lg shadow-sm p-6">
          <div class="flex items-start justify-between gap-4">
            <div>
              <h2 class="text-lg font-semibold text-sky-900">补处理历史附件</h2>
              <p class="mt-1 text-sm text-gray-500">会重跑旧帖子附件发现、下载和 Excel 解析，适合给历史数据补质量。</p>
            </div>
            <span class="inline-flex items-center rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-700">
              补处理任务
            </span>
          </div>

          <div class="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">数据源</label>
              <select
                v-model="backfillForm.sourceId"
                class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-600 focus:border-transparent"
              >
                <option value="">全部数据源</option>
                <option
                  v-for="source in sourceOptions"
                  :key="`backfill-${source.value}`"
                  :value="String(source.value)"
                  :disabled="source.isActive === false"
                >
                  {{ source.label }}
                </option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">处理条数上限</label>
              <input
                v-model.number="backfillForm.limit"
                type="number"
                min="1"
                max="1000"
                class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-600 focus:border-transparent"
              />
            </div>
          </div>

          <button
            @click="runBackfillTask"
            :disabled="backfillBusy"
            class="mt-6 inline-flex items-center justify-center rounded-lg bg-amber-600 px-4 py-2.5 text-white transition-colors duration-200 hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {{ backfillBusy ? '补处理中...' : '开始补处理' }}
          </button>
        </section>
      </div>

      <section class="bg-white rounded-lg shadow-sm p-6">
        <div class="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-6">
          <div>
            <div class="flex items-start justify-between gap-4">
              <div>
                <h2 class="text-lg font-semibold text-sky-900">分析层</h2>
                <p class="mt-1 text-sm text-gray-500">规则分析先兜住统计，OpenAI 再补更细的标签、摘要和阶段判断。</p>
              </div>
              <span class="inline-flex items-center rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium text-emerald-700">
                分析任务
              </span>
            </div>

            <div
              class="mt-6 rounded-lg border px-4 py-3 text-sm"
              :class="openaiReady
                ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                : 'border-amber-200 bg-amber-50 text-amber-800'"
            >
              <p v-if="openaiReady">
                OpenAI 已就绪，当前模型是 {{ analysisRuntime.model_name }}。现在点“开始 OpenAI 分析”会真的走 AI。
              </p>
              <p v-else>
                当前还没接上 OpenAI，页面里看到的“分析结果”还是规则分析。{{ openaiUnavailableReason }}
              </p>
              <p class="mt-1 text-xs opacity-80">
                分析总开关：{{ analysisRuntime.analysis_enabled ? '已开启' : '已关闭' }}；
                当前 provider：{{ analysisRuntime.provider }}；
                接口地址：{{ analysisRuntime.base_url_configured ? analysisRuntime.base_url : 'OpenAI 官方默认' }}
              </p>
            </div>

            <div class="mt-6 grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
              <div class="rounded-lg bg-sky-50 px-4 py-3">
                <div class="text-xs text-gray-500">总帖子</div>
                <div class="mt-1 text-xl font-semibold text-sky-900">{{ analysisOverview.total_posts }}</div>
              </div>
              <div class="rounded-lg bg-emerald-50 px-4 py-3">
                <div class="text-xs text-gray-500">任意分析</div>
                <div class="mt-1 text-xl font-semibold text-emerald-700">{{ analysisOverview.analyzed_posts }}</div>
              </div>
              <div class="rounded-lg bg-amber-50 px-4 py-3">
                <div class="text-xs text-gray-500">规则分析</div>
                <div class="mt-1 text-xl font-semibold text-amber-700">{{ analysisOverview.rule_analyzed_posts }}</div>
              </div>
              <div class="rounded-lg bg-indigo-50 px-4 py-3">
                <div class="text-xs text-gray-500">OpenAI 分析</div>
                <div class="mt-1 text-xl font-semibold text-indigo-700">{{ analysisOverview.openai_analyzed_posts }}</div>
              </div>
              <div class="rounded-lg bg-violet-50 px-4 py-3">
                <div class="text-xs text-gray-500">待 OpenAI</div>
                <div class="mt-1 text-xl font-semibold text-violet-700">{{ analysisOverview.openai_pending_posts }}</div>
              </div>
              <div class="rounded-lg bg-cyan-50 px-4 py-3">
                <div class="text-xs text-gray-500">含附件</div>
                <div class="mt-1 text-xl font-semibold text-cyan-700">{{ analysisOverview.attachment_posts }}</div>
              </div>
            </div>

            <div class="mt-6 grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">数据源</label>
                <select
                  v-model="analysisForm.sourceId"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-600 focus:border-transparent"
                >
                  <option value="">全部数据源</option>
                  <option
                    v-for="source in sourceOptions"
                    :key="`analysis-${source.value}`"
                    :value="String(source.value)"
                    :disabled="source.isActive === false"
                  >
                    {{ source.label }}
                  </option>
                </select>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">分析条数上限</label>
                <input
                  v-model.number="analysisForm.limit"
                  type="number"
                  min="1"
                  max="500"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-600 focus:border-transparent"
                />
              </div>
              <div class="flex items-end">
                <label class="inline-flex items-center cursor-pointer text-sm text-gray-700">
                  <input
                    v-model="analysisForm.onlyUnanalyzed"
                    type="checkbox"
                    class="w-4 h-4 text-sky-600 border-gray-300 rounded focus:ring-sky-500 cursor-pointer"
                  />
                  <span class="ml-2">只跑未分析内容</span>
                </label>
              </div>
            </div>

            <div class="mt-6 flex flex-wrap gap-3">
              <button
                @click="runAiAnalysisTask"
                :disabled="analysisBusy || !openaiReady"
                class="inline-flex items-center justify-center rounded-lg bg-emerald-600 px-4 py-2.5 text-white transition-colors duration-200 hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {{ analysisBusy ? '分析中...' : '开始 OpenAI 分析' }}
              </button>
              <button
                @click="fetchAnalysisSummary"
                :disabled="analysisLoading"
                class="inline-flex items-center justify-center rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-700 transition-colors duration-200 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {{ analysisLoading ? '刷新中...' : '刷新分析摘要' }}
              </button>
            </div>

            <div class="mt-6 rounded-lg border border-cyan-200 bg-cyan-50 px-4 py-4">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <h3 class="text-sm font-semibold text-cyan-900">岗位级抽取</h3>
                  <p class="mt-1 text-xs text-cyan-800">从正文+附件+AI里提取岗位明细，用于“只招辅导员/混合招聘含辅导员”分层和统计。</p>
                </div>
                <span class="inline-flex items-center rounded-full bg-cyan-100 px-2.5 py-1 text-xs font-medium text-cyan-800">
                  新入口
                </span>
              </div>

              <div class="mt-4 grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
                <div class="rounded-lg bg-white px-3 py-3">
                  <div class="text-gray-500">岗位总数</div>
                  <div class="mt-1 font-semibold text-cyan-900">{{ jobsOverview.total_jobs }}</div>
                </div>
                <div class="rounded-lg bg-white px-3 py-3">
                  <div class="text-gray-500">含岗位帖子</div>
                  <div class="mt-1 font-semibold text-cyan-900">{{ jobsOverview.posts_with_jobs }}</div>
                </div>
                <div class="rounded-lg bg-white px-3 py-3">
                  <div class="text-gray-500">辅导员岗位数</div>
                  <div class="mt-1 font-semibold text-emerald-700">{{ jobsOverview.counselor_jobs }}</div>
                </div>
                <div class="rounded-lg bg-white px-3 py-3">
                  <div class="text-gray-500">待抽取帖子</div>
                  <div class="mt-1 font-semibold text-amber-700">{{ jobsOverview.pending_posts }}</div>
                </div>
              </div>

              <div class="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label class="block text-sm font-medium text-gray-700 mb-2">数据源</label>
                  <select
                    v-model="jobsForm.sourceId"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-cyan-600 focus:border-transparent"
                  >
                    <option value="">全部数据源</option>
                    <option
                      v-for="source in sourceOptions"
                      :key="`jobs-${source.value}`"
                      :value="String(source.value)"
                      :disabled="source.isActive === false"
                    >
                      {{ source.label }}
                    </option>
                  </select>
                </div>
                <div>
                  <label class="block text-sm font-medium text-gray-700 mb-2">处理上限</label>
                  <input
                    v-model.number="jobsForm.limit"
                    type="number"
                    min="1"
                    max="1000"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-cyan-600 focus:border-transparent"
                  />
                </div>
                <div class="flex items-end">
                  <label class="inline-flex items-center cursor-pointer text-sm text-gray-700">
                    <input
                      v-model="jobsForm.onlyPending"
                      type="checkbox"
                      class="w-4 h-4 text-cyan-600 border-gray-300 rounded focus:ring-cyan-500 cursor-pointer"
                    />
                    <span class="ml-2">只处理未抽取</span>
                  </label>
                </div>
              </div>

              <div class="mt-4">
                <label
                  class="inline-flex items-center cursor-pointer text-sm"
                  :class="openaiReady ? 'text-gray-700' : 'text-gray-400 cursor-not-allowed'"
                >
                  <input
                    v-model="jobsForm.useAi"
                    type="checkbox"
                    class="w-4 h-4 text-cyan-600 border-gray-300 rounded focus:ring-cyan-500 cursor-pointer disabled:cursor-not-allowed"
                    :disabled="!openaiReady"
                  />
                  <span class="ml-2">启用 AI 补抽（更慢，但能补正文里没结构化出来的岗位）</span>
                </label>
              </div>

              <div class="mt-4 flex flex-wrap gap-3">
                <button
                  @click="runJobExtractionTask"
                  :disabled="jobsBusy"
                  class="inline-flex items-center justify-center rounded-lg bg-cyan-600 px-4 py-2.5 text-white transition-colors duration-200 hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {{ jobsBusy ? '抽取中...' : '开始岗位抽取' }}
                </button>
                <button
                  @click="fetchJobSummary"
                  :disabled="jobsLoading"
                  class="inline-flex items-center justify-center rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-700 transition-colors duration-200 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {{ jobsLoading ? '刷新中...' : '刷新岗位摘要' }}
                </button>
              </div>

              <p v-if="jobsSummaryUnavailable" class="mt-3 text-xs text-amber-700">
                后端还没开放岗位级摘要接口，当前先显示 0，不影响别的功能。
              </p>
              <p v-if="jobSummary.latest_extracted_at" class="mt-2 text-xs text-gray-500">
                最近岗位抽取完成时间：{{ formatDateTime(jobSummary.latest_extracted_at) }}
              </p>
            </div>

            <p v-if="!openaiReady" class="mt-3 text-xs text-amber-700">
              先在后端 `.env` 里补 `OPENAI_API_KEY`，必要时再补 `OPENAI_BASE_URL`，然后重启后端。
            </p>

            <p v-if="analysisSummary.latest_analyzed_at" class="mt-4 text-xs text-gray-500">
              最近一次分析完成时间：{{ formatDateTime(analysisSummary.latest_analyzed_at) }}
            </p>
          </div>

          <div class="lg:w-80 space-y-6">
            <div>
              <h3 class="text-sm font-semibold text-gray-700">分析来源分布</h3>
              <div v-if="analysisProviderStats.length" class="mt-4 space-y-3">
                <div
                  v-for="item in analysisProviderStats.slice(0, 4)"
                  :key="item.analysis_provider"
                  class="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3"
                >
                  <div class="flex items-center justify-between gap-3 text-sm">
                    <span class="font-medium text-gray-700">{{ getAnalysisProviderLabel(item.analysis_provider) }}</span>
                    <span class="text-emerald-700 font-semibold">{{ item.count }}</span>
                  </div>
                </div>
              </div>
              <div v-else class="mt-4 rounded-lg border border-dashed border-gray-300 px-4 py-6 text-sm text-gray-500">
                还没有分析来源数据。
              </div>
            </div>

            <div>
              <h3 class="text-sm font-semibold text-gray-700">事件类型分布</h3>
              <div v-if="analysisSummary.event_type_distribution?.length" class="mt-4 space-y-3">
                <div
                  v-for="item in analysisSummary.event_type_distribution.slice(0, 6)"
                  :key="item.event_type"
                  class="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3"
                >
                  <div class="flex items-center justify-between gap-3 text-sm">
                    <span class="font-medium text-gray-700">{{ item.event_type }}</span>
                    <span class="text-sky-700 font-semibold">{{ item.count }}</span>
                  </div>
                </div>
              </div>
              <div v-else class="mt-4 rounded-lg border border-dashed border-gray-300 px-4 py-6 text-sm text-gray-500">
                还没有分析结果，先跑一次分析。
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="bg-white rounded-lg shadow-sm p-6">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div class="flex items-center gap-3">
              <h2 class="text-lg font-semibold text-sky-900">AI 统计看板</h2>
              <span class="inline-flex items-center rounded-full bg-fuchsia-100 px-3 py-1 text-xs font-medium text-fuchsia-700">
                统计摘要
              </span>
            </div>
            <p class="mt-1 text-sm text-gray-500">把 AI 和规则抽出来的稳定字段单独看，方便判断数据覆盖率、截止节奏和区域分布。</p>
          </div>
          <button
            @click="fetchInsightSummary"
            :disabled="insightLoading"
            class="inline-flex items-center justify-center rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-700 transition-colors duration-200 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {{ insightLoading ? '刷新中...' : '刷新统计看板' }}
          </button>
        </div>

        <div class="mt-6 rounded-lg border border-fuchsia-200 bg-fuchsia-50 px-4 py-4 text-sm text-fuchsia-900">
          <p>
            当前已提取 {{ insightOverview.insight_posts || 0 }} 条统计结果，
            覆盖率 {{ formatPercent(insightOverview.insight_posts, analysisOverview.total_posts) }}；
            其中 OpenAI 占 {{ formatPercent(insightOverview.openai_insight_posts, insightOverview.insight_posts) }}。
          </p>
          <p class="mt-1 text-xs opacity-80">
            失败 {{ insightOverview.failed_insight_posts || 0 }} 条，跳过 {{ insightOverview.skipped_insight_posts || 0 }} 条。
            {{ insightLatestAnalyzedAt ? `最近统计完成于 ${formatDateTime(insightLatestAnalyzedAt)}` : '还没有统计完成时间。' }}
          </p>
        </div>

        <div class="mt-6 grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
          <div class="rounded-lg bg-fuchsia-50 px-4 py-3">
            <div class="text-xs text-gray-500">已提取</div>
            <div class="mt-1 text-xl font-semibold text-fuchsia-700">{{ insightOverview.insight_posts || 0 }}</div>
          </div>
          <div class="rounded-lg bg-slate-50 px-4 py-3">
            <div class="text-xs text-gray-500">待提取</div>
            <div class="mt-1 text-xl font-semibold text-slate-700">{{ insightOverview.pending_insight_posts || 0 }}</div>
          </div>
          <div class="rounded-lg bg-indigo-50 px-4 py-3">
            <div class="text-xs text-gray-500">OpenAI 统计</div>
            <div class="mt-1 text-xl font-semibold text-indigo-700">{{ insightOverview.openai_insight_posts || 0 }}</div>
          </div>
          <div class="rounded-lg bg-amber-50 px-4 py-3">
            <div class="text-xs text-gray-500">规则统计</div>
            <div class="mt-1 text-xl font-semibold text-amber-700">{{ insightOverview.rule_insight_posts || 0 }}</div>
          </div>
          <div class="rounded-lg bg-emerald-50 px-4 py-3">
            <div class="text-xs text-gray-500">有截止时间</div>
            <div class="mt-1 text-xl font-semibold text-emerald-700">{{ insightOverview.posts_with_deadline || 0 }}</div>
          </div>
          <div class="rounded-lg bg-cyan-50 px-4 py-3">
            <div class="text-xs text-gray-500">有附件岗位表</div>
            <div class="mt-1 text-xl font-semibold text-cyan-700">{{ insightOverview.posts_with_attachment_job_table || 0 }}</div>
          </div>
        </div>

        <div class="mt-6 grid grid-cols-1 xl:grid-cols-3 gap-4">
          <div class="rounded-lg border border-gray-200 bg-white px-4 py-4">
            <h3 class="text-sm font-semibold text-gray-700">截止状态分布</h3>
            <div v-if="insightDeadlineStats.length" class="mt-4 space-y-3">
              <div
                v-for="item in insightDeadlineStats.slice(0, 4)"
                :key="item.deadline_status"
                class="rounded-lg bg-amber-50 px-3 py-3"
              >
                <div class="flex items-center justify-between gap-3 text-sm">
                  <span class="font-medium text-gray-700">{{ item.deadline_status }}</span>
                  <span class="font-semibold text-amber-700">{{ item.count }}</span>
                </div>
                <div class="mt-2 h-2 rounded-full bg-white/80">
                  <div
                    class="h-2 rounded-full bg-amber-500"
                    :style="getDistributionBarStyle(item.count, insightDeadlineMaxCount)"
                  />
                </div>
              </div>
            </div>
            <div v-else class="mt-4 rounded-lg border border-dashed border-gray-300 px-4 py-6 text-sm text-gray-500">
              还没有截止状态数据。
            </div>
          </div>

          <div class="rounded-lg border border-gray-200 bg-white px-4 py-4">
            <h3 class="text-sm font-semibold text-gray-700">学历下限分布</h3>
            <div v-if="insightDegreeStats.length" class="mt-4 space-y-3">
              <div
                v-for="item in insightDegreeStats.slice(0, 5)"
                :key="item.degree_floor"
                class="rounded-lg bg-sky-50 px-3 py-3"
              >
                <div class="flex items-center justify-between gap-3 text-sm">
                  <span class="font-medium text-gray-700">{{ item.degree_floor }}</span>
                  <span class="font-semibold text-sky-700">{{ item.count }}</span>
                </div>
                <div class="mt-2 h-2 rounded-full bg-white/80">
                  <div
                    class="h-2 rounded-full bg-sky-500"
                    :style="getDistributionBarStyle(item.count, insightDegreeMaxCount)"
                  />
                </div>
              </div>
            </div>
            <div v-else class="mt-4 rounded-lg border border-dashed border-gray-300 px-4 py-6 text-sm text-gray-500">
              还没有学历分布数据。
            </div>
          </div>

          <div class="rounded-lg border border-gray-200 bg-white px-4 py-4">
            <h3 class="text-sm font-semibold text-gray-700">城市分布</h3>
            <div v-if="insightCityStats.length" class="mt-4 space-y-3">
              <div
                v-for="item in insightCityStats.slice(0, 6)"
                :key="item.city"
                class="rounded-lg bg-emerald-50 px-3 py-3"
              >
                <div class="flex items-center justify-between gap-3 text-sm">
                  <span class="font-medium text-gray-700">{{ item.city }}</span>
                  <span class="font-semibold text-emerald-700">{{ item.count }}</span>
                </div>
                <div class="mt-2 h-2 rounded-full bg-white/80">
                  <div
                    class="h-2 rounded-full bg-emerald-500"
                    :style="getDistributionBarStyle(item.count, insightCityMaxCount)"
                  />
                </div>
              </div>
            </div>
            <div v-else class="mt-4 rounded-lg border border-dashed border-gray-300 px-4 py-6 text-sm text-gray-500">
              还没有城市分布数据。
            </div>
          </div>
        </div>

        <div class="mt-6 grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div class="rounded-lg border border-gray-200 bg-white px-4 py-3">
            <div class="text-xs text-gray-500">含笔试</div>
            <div class="mt-1 text-lg font-semibold text-gray-900">{{ insightOverview.posts_with_written_exam || 0 }}</div>
          </div>
          <div class="rounded-lg border border-gray-200 bg-white px-4 py-3">
            <div class="text-xs text-gray-500">含面试</div>
            <div class="mt-1 text-lg font-semibold text-gray-900">{{ insightOverview.posts_with_interview || 0 }}</div>
          </div>
          <div class="rounded-lg border border-gray-200 bg-white px-4 py-3">
            <div class="text-xs text-gray-500">统计失败</div>
            <div class="mt-1 text-lg font-semibold text-red-600">{{ insightOverview.failed_insight_posts || 0 }}</div>
          </div>
          <div class="rounded-lg border border-gray-200 bg-white px-4 py-3">
            <div class="text-xs text-gray-500">统计跳过</div>
            <div class="mt-1 text-lg font-semibold text-gray-700">{{ insightOverview.skipped_insight_posts || 0 }}</div>
          </div>
        </div>
      </section>

      <section class="bg-white rounded-lg shadow-sm p-6">
        <div class="flex items-center justify-between gap-4">
          <div>
            <h2 class="text-lg font-semibold text-sky-900">最近执行记录</h2>
            <p class="mt-1 text-sm text-gray-500">只保留最近几次，方便你看任务有没有真的跑起来。</p>
          </div>
          <button
            @click="refreshTaskStatus"
            :disabled="loadingRuns"
            class="inline-flex items-center rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition-colors duration-200 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {{ loadingRuns ? '刷新中...' : '刷新状态' }}
          </button>
        </div>

        <div v-if="loadingRuns" class="py-10 text-center text-sm text-gray-500">正在加载任务记录...</div>

        <div v-else-if="taskRuns.length === 0" class="py-10 text-center text-sm text-gray-500">
          还没有管理任务记录，先手动跑一次任务。
        </div>

        <div v-else class="mt-6 space-y-4">
          <article
            v-for="run in taskRuns"
            :key="run.id"
            class="rounded-lg border border-gray-200 bg-gray-50 p-4"
          >
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <div class="flex flex-wrap items-center gap-2">
                  <h3 class="text-base font-semibold text-sky-900">{{ getTaskTypeLabel(run.task_type) }}</h3>
                  <span
                    class="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium"
                    :class="getTaskStatusClass(run.status, run)"
                  >
                    {{ getTaskStatusLabel(run.status, run) }}
                  </span>
                </div>
                <p class="mt-1 text-sm text-gray-600">{{ run.summary }}</p>
                <div class="mt-2 space-y-2">
                  <div class="flex items-center justify-between gap-3 text-xs text-gray-500">
                    <span>{{ run.phase || getDefaultTaskPhase(run) }}</span>
                    <span>{{ getTaskProgress(run) }}%</span>
                  </div>
                  <div class="h-2 rounded-full bg-gray-200">
                    <div
                      class="h-2 rounded-full transition-all duration-300"
                      :class="isTaskPossiblyStuck(run) ? 'bg-red-400' : 'bg-sky-500'"
                      :style="{ width: `${getTaskProgress(run)}%` }"
                    />
                  </div>
                  <div v-if="isRunningStatus(run.status)" class="text-xs text-gray-500">
                    已运行 {{ formatRunningElapsed(run) }}，最近心跳 {{ formatDateTime(getTaskHeartbeatAt(run)) || '--' }}
                  </div>
                </div>
              </div>
              <div class="flex items-center gap-3">
                <div class="text-sm text-gray-500">
                  {{ formatDateTime(run.finished_at || run.started_at) }}
                </div>
                <button
                  @click="retryTaskRun(run)"
                  :disabled="retryingTaskId === run.id || !canRetryTask(run.task_type)"
                  class="inline-flex items-center rounded-lg border border-sky-300 bg-sky-50 px-3 py-1.5 text-xs font-medium text-sky-700 transition-colors duration-200 hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {{ retryingTaskId === run.id ? '重试中...' : '重试任务' }}
                </button>
                <button
                  @click="toggleTaskExpanded(run.id)"
                  class="inline-flex items-center rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors duration-200 hover:bg-gray-100"
                >
                  {{ isTaskExpanded(run.id) ? '收起详情' : '展开详情' }}
                </button>
              </div>
            </div>

            <div v-if="isTaskExpanded(run.id)" class="mt-4 space-y-4">
              <div
                v-if="isTaskPossiblyStuck(run)"
                class="rounded-lg border border-amber-300 bg-amber-50 px-3 py-3 text-sm text-amber-800"
              >
                这个任务超过 10 分钟没有心跳，可能卡住了。可以先点上面的“刷新状态”，再按“重试任务”。
              </div>

              <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 text-sm">
                <div class="rounded-lg bg-white px-3 py-3">
                  <div class="text-gray-500">开始时间</div>
                  <div class="mt-1 font-semibold text-gray-900">{{ formatDateTime(run.started_at) || '--' }}</div>
                </div>
                <div class="rounded-lg bg-white px-3 py-3">
                  <div class="text-gray-500">结束时间</div>
                  <div class="mt-1 font-semibold text-gray-900">{{ formatDateTime(run.finished_at) || '--' }}</div>
                </div>
                <div class="rounded-lg bg-white px-3 py-3">
                  <div class="text-gray-500">耗时</div>
                  <div class="mt-1 font-semibold text-gray-900">{{ formatDuration(run) }}</div>
                </div>
                <div class="rounded-lg bg-white px-3 py-3">
                  <div class="text-gray-500">最近心跳</div>
                  <div class="mt-1 font-semibold text-gray-900">{{ formatDateTime(getTaskHeartbeatAt(run)) || '--' }}</div>
                </div>
              </div>

              <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3 text-sm">
                <div class="rounded-lg bg-white px-3 py-3">
                  <div class="text-gray-500">参数 source_id</div>
                  <div class="mt-1 font-semibold text-gray-900">{{ formatSourceParam(run) }}</div>
                </div>
                <div class="rounded-lg bg-white px-3 py-3">
                  <div class="text-gray-500">参数 max_pages</div>
                  <div class="mt-1 font-semibold text-gray-900">{{ getTaskParam(run, 'max_pages', 'maxPages') ?? '--' }}</div>
                </div>
                <div class="rounded-lg bg-white px-3 py-3">
                  <div class="text-gray-500">参数 limit</div>
                  <div class="mt-1 font-semibold text-gray-900">{{ getTaskParam(run, 'limit') ?? '--' }}</div>
                </div>
              </div>

              <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 text-sm">
                <div class="rounded-lg bg-white px-3 py-3">
                  <div class="text-gray-500">处理帖子</div>
                  <div class="mt-1 font-semibold text-gray-900">{{ getDetailValue(run.details, 'posts_updated', 'processed_records') }}</div>
                </div>
                <div class="rounded-lg bg-white px-3 py-3">
                  <div class="text-gray-500">发现附件</div>
                  <div class="mt-1 font-semibold text-gray-900">{{ getDetailValue(run.details, 'attachments_discovered') }}</div>
                </div>
                <div class="rounded-lg bg-white px-3 py-3">
                  <div class="text-gray-500">下载附件</div>
                  <div class="mt-1 font-semibold text-gray-900">{{ getDetailValue(run.details, 'attachments_downloaded') }}</div>
                </div>
                <div class="rounded-lg bg-white px-3 py-3">
                  <div class="text-gray-500">补字段</div>
                  <div class="mt-1 font-semibold text-gray-900">{{ getDetailValue(run.details, 'fields_added') }}</div>
                </div>
              </div>

              <div
                v-if="getTaskFailureReason(run)"
                class="rounded-lg border border-red-200 bg-red-50 px-3 py-3 text-sm text-red-700"
              >
                <span class="font-medium">失败原因：</span>{{ getTaskFailureReason(run) }}
              </div>
            </div>
          </article>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { adminApi } from '../api/posts'

const scrapeRunning = ref(false)
const backfillRunning = ref(false)
const duplicateBackfillRunning = ref(false)
const analysisRunning = ref(false)
const jobsRunning = ref(false)
const loadingRuns = ref(false)
const analysisLoading = ref(false)
const insightLoading = ref(false)
const jobsLoading = ref(false)
const duplicateLoading = ref(false)
const schedulerLoading = ref(false)
const schedulerSaving = ref(false)
const jobsSummaryUnavailable = ref(false)
const overviewRefreshing = ref(false)
const taskRuns = ref([])
const taskSummary = ref(null)
const expandedTaskIds = ref([])
const analysisSummary = ref({
  runtime: {
    analysis_enabled: true,
    provider: 'openai',
    model_name: 'gpt-5-mini',
    openai_ready: false,
    openai_configured: false,
    openai_sdk_available: true,
    base_url_configured: false,
    base_url: ''
  },
  overview: {
    total_posts: 0,
    analyzed_posts: 0,
    pending_posts: 0,
    attachment_posts: 0,
    rule_analyzed_posts: 0,
    openai_analyzed_posts: 0,
    openai_pending_posts: 0
  },
  provider_distribution: [],
  event_type_distribution: [],
  latest_analyzed_at: ''
})
const insightSummary = ref(null)
const jobSummary = ref({
  overview: {
    total_jobs: 0,
    posts_with_jobs: 0,
    counselor_jobs: 0,
    pending_posts: 0
  },
  latest_extracted_at: ''
})
const duplicateSummary = ref({
  overview: {
    duplicate_groups: 0,
    duplicate_posts: 0,
    primary_posts: 0,
    unchecked_posts: 0
  },
  reason_distribution: [],
  latest_checked_at: '',
  latest_groups: []
})
const feedback = ref({
  type: '',
  message: ''
})
const retryingTaskId = ref('')
const taskPollingInFlight = ref(false)
const taskPollingTimerId = ref(null)
const nowTs = ref(Date.now())
const sourceOptions = ref([
  { label: '江苏省人社厅（source_id=1）', value: 1, isActive: true }
])

const scrapeForm = ref({
  sourceId: 1,
  maxPages: 5
})
const schedulerForm = ref({
  enabled: true,
  intervalSeconds: 7200,
  defaultSourceId: 1,
  defaultMaxPages: 5,
  nextRunAt: '',
  updatedAt: ''
})

const backfillForm = ref({
  sourceId: '',
  limit: 100
})
const duplicateBackfillForm = ref({
  limit: 200
})
const analysisForm = ref({
  sourceId: '',
  limit: 100,
  onlyUnanalyzed: true
})
const jobsForm = ref({
  sourceId: '',
  limit: 100,
  onlyPending: true,
  useAi: false
})
const EMPTY_INSIGHT_OVERVIEW = {
  insight_posts: 0,
  pending_insight_posts: 0,
  openai_insight_posts: 0,
  rule_insight_posts: 0,
  failed_insight_posts: 0,
  skipped_insight_posts: 0,
  posts_with_deadline: 0,
  posts_with_written_exam: 0,
  posts_with_interview: 0,
  posts_with_attachment_job_table: 0
}
const TASK_HEARTBEAT_STALE_MS = 10 * 60 * 1000
const TASK_POLL_INTERVAL_MS = 15 * 1000
const getMaxDistributionCount = (items = []) => {
  const counts = items.map((item) => Number(item?.count || 0)).filter((count) => Number.isFinite(count) && count > 0)
  return counts.length ? Math.max(...counts) : 0
}
const formatPercent = (part, total) => {
  const numerator = Number(part || 0)
  const denominator = Number(total || 0)
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator <= 0) {
    return '0%'
  }
  return `${Math.round((numerator / denominator) * 100)}%`
}
const getDistributionBarStyle = (count, maxCount) => {
  const normalizedCount = Number(count || 0)
  const normalizedMax = Number(maxCount || 0)
  if (!Number.isFinite(normalizedCount) || !Number.isFinite(normalizedMax) || normalizedCount <= 0 || normalizedMax <= 0) {
    return { width: '0%' }
  }
  const width = Math.max(Math.round((normalizedCount / normalizedMax) * 100), 8)
  return { width: `${Math.min(width, 100)}%` }
}

const feedbackClass = computed(() => {
  if (feedback.value.type === 'success') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700'
  }
  return 'border-red-200 bg-red-50 text-red-700'
})
const backendRunningTasks = computed(() => {
  const combined = [
    ...(Array.isArray(taskSummary.value?.running_tasks) ? taskSummary.value.running_tasks : []),
    ...taskRuns.value.filter((run) => isRunningStatus(run?.status))
  ]
  const seen = new Set()

  return combined.filter((run) => {
    const taskType = run?.task_type || run?.taskType
    if (!taskType) {
      return false
    }

    const taskKey = run?.id || `${taskType}-${run?.started_at || run?.startedAt || ''}`
    if (seen.has(taskKey)) {
      return false
    }

    seen.add(taskKey)
    return true
  })
})
const isTaskTypeRunning = (...taskTypes) => {
  return backendRunningTasks.value.some((run) => taskTypes.includes(run?.task_type || run?.taskType))
}
const scrapeBusy = computed(() => scrapeRunning.value || isTaskTypeRunning('manual_scrape', 'scheduled_scrape'))
const backfillBusy = computed(() => backfillRunning.value || isTaskTypeRunning('attachment_backfill'))
const duplicateBackfillBusy = computed(() => duplicateBackfillRunning.value || isTaskTypeRunning('duplicate_backfill'))
const analysisBusy = computed(() => analysisRunning.value || isTaskTypeRunning('ai_analysis'))
const jobsBusy = computed(() => jobsRunning.value || isTaskTypeRunning('job_extraction', 'ai_job_extraction'))
const activeTaskHints = computed(() => {
  const hints = []
  if (scrapeBusy.value) {
    hints.push('手动抓取最新数据')
  }
  if (backfillBusy.value) {
    hints.push('补处理历史附件')
  }
  if (analysisBusy.value) {
    hints.push('OpenAI 分析')
  }
  if (jobsBusy.value) {
    hints.push('岗位级抽取')
  }
  if (duplicateBackfillBusy.value) {
    hints.push('历史去重补齐')
  }
  backendRunningTasks.value.forEach((run) => {
    hints.push(`后台执行：${getTaskTypeLabel(run.task_type || run.taskType)}`)
  })
  return [...new Set(hints)]
})
const analysisOverview = computed(() => analysisSummary.value?.overview || {
  total_posts: 0,
  analyzed_posts: 0,
  pending_posts: 0,
  attachment_posts: 0,
  rule_analyzed_posts: 0,
  openai_analyzed_posts: 0,
  openai_pending_posts: 0
})
const analysisRuntime = computed(() => analysisSummary.value?.runtime || {
  analysis_enabled: true,
  provider: 'openai',
  model_name: 'gpt-5-mini',
  openai_ready: false,
  openai_configured: false,
  openai_sdk_available: true,
  base_url_configured: false,
  base_url: ''
})
const analysisProviderStats = computed(() => analysisSummary.value?.provider_distribution || [])
const insightOverview = computed(() => insightSummary.value?.overview || analysisSummary.value?.insight_overview || EMPTY_INSIGHT_OVERVIEW)
const insightDegreeStats = computed(() => insightSummary.value?.degree_floor_distribution || analysisSummary.value?.degree_floor_distribution || [])
const insightDeadlineStats = computed(() => insightSummary.value?.deadline_status_distribution || analysisSummary.value?.deadline_status_distribution || [])
const insightCityStats = computed(() => insightSummary.value?.city_distribution || analysisSummary.value?.city_distribution || [])
const insightLatestAnalyzedAt = computed(() => insightSummary.value?.latest_analyzed_at || analysisSummary.value?.latest_insight_at || '')
const insightDegreeMaxCount = computed(() => getMaxDistributionCount(insightDegreeStats.value))
const insightDeadlineMaxCount = computed(() => getMaxDistributionCount(insightDeadlineStats.value))
const insightCityMaxCount = computed(() => getMaxDistributionCount(insightCityStats.value))
const jobsOverview = computed(() => jobSummary.value?.overview || {
  total_jobs: 0,
  posts_with_jobs: 0,
  counselor_jobs: 0,
  pending_posts: 0
})
const openaiReady = computed(() => Boolean(analysisRuntime.value?.openai_ready))
const openaiUnavailableReason = computed(() => {
  if (!analysisRuntime.value.analysis_enabled) {
    return '因为 AI 总开关现在就是关着的。'
  }
  if (!analysisRuntime.value.openai_configured) {
    return '因为后端还没配置 OPENAI_API_KEY。'
  }
  if (!analysisRuntime.value.openai_sdk_available) {
    return '因为当前运行环境里还没装 openai SDK。'
  }
  return '因为当前 OpenAI 运行条件还没满足。'
})
const latestSuccessTask = computed(() => {
  const fromSummary = normalizeSummaryResponse(taskSummary.value)
  if (fromSummary) {
    return fromSummary
  }
  const successRun = taskRuns.value.find((run) => run?.status === 'success')
  return normalizeTaskRun(successRun)
})
const latestFailedTask = computed(() => {
  const failedRun = taskRuns.value.find((run) => run?.status === 'failed')
  return normalizeTaskRun(failedRun)
})
const latestSuccessText = computed(() => {
  if (!latestSuccessTask.value?.finishedAt) return ''
  return getRelativeTimeLabel(latestSuccessTask.value.finishedAt)
})
const latestFailedText = computed(() => {
  if (!latestFailedTask.value?.finishedAt) return ''
  return getRelativeTimeLabel(latestFailedTask.value.finishedAt)
})
const healthStatusLevel = computed(() => {
  const hasFreshFailure = latestFailedTask.value?.finishedAt && (
    !latestSuccessTask.value?.finishedAt ||
    new Date(latestFailedTask.value.finishedAt).getTime() > new Date(latestSuccessTask.value.finishedAt).getTime()
  )

  if (!schedulerForm.value.enabled || hasFreshFailure) {
    return 'warning'
  }

  if (
    !openaiReady.value ||
    Number(analysisOverview.value.openai_pending_posts || 0) > 0 ||
    Number(insightOverview.value.pending_insight_posts || 0) > 0 ||
    Number(jobsOverview.value.pending_posts || 0) > 0
  ) {
    return 'attention'
  }

  return 'healthy'
})
const healthStatusLabel = computed(() => {
  if (healthStatusLevel.value === 'warning') return '需处理'
  if (healthStatusLevel.value === 'attention') return '需关注'
  return '正常'
})
const healthPanelClass = computed(() => {
  if (healthStatusLevel.value === 'warning') {
    return 'border-red-200 bg-red-50/80'
  }
  if (healthStatusLevel.value === 'attention') {
    return 'border-amber-200 bg-amber-50/80'
  }
  return 'border-emerald-200 bg-emerald-50/80'
})
const healthBadgeClass = computed(() => {
  if (healthStatusLevel.value === 'warning') {
    return 'bg-red-100 text-red-700'
  }
  if (healthStatusLevel.value === 'attention') {
    return 'bg-amber-100 text-amber-800'
  }
  return 'bg-emerald-100 text-emerald-700'
})
const healthTextClass = computed(() => {
  if (healthStatusLevel.value === 'warning') {
    return 'text-red-700'
  }
  if (healthStatusLevel.value === 'attention') {
    return 'text-amber-800'
  }
  return 'text-emerald-800'
})
const healthStatusSummary = computed(() => {
  if (healthStatusLevel.value === 'warning') {
    return '当前有会影响持续更新的项，建议优先看下面的提示。'
  }
  if (healthStatusLevel.value === 'attention') {
    return '系统能跑，但还有积压或 AI 能力没完全打开。'
  }
  return '抓取、分析和岗位抽取都在正常状态。'
})
const healthAlerts = computed(() => {
  const alerts = []
  const latestSuccessAt = latestSuccessTask.value?.finishedAt
  const intervalMs = Number(schedulerForm.value.intervalSeconds || 0) * 1000

  if (!schedulerForm.value.enabled) {
    alerts.push('定时抓取现在是关闭的，前台不会自动更新。')
  }

  if (latestSuccessAt && intervalMs > 0) {
    const staleThreshold = Math.max(intervalMs * 2, 6 * 60 * 60 * 1000)
    const diffMs = Date.now() - new Date(latestSuccessAt).getTime()
    if (diffMs > staleThreshold) {
      alerts.push(`最近一次成功任务距离现在已经 ${getRelativeTimeLabel(latestSuccessAt)}，建议检查调度有没有卡住。`)
    }
  }

  if (latestFailedTask.value?.summary) {
    alerts.push(`最近失败任务：${getTaskTypeLabel(latestFailedTask.value.taskType)}。${latestFailedTask.value.summary}`)
  }

  if (!openaiReady.value) {
    alerts.push('OpenAI 现在还没就绪，分析层会继续回到规则分析。')
  }

  if (Number(analysisOverview.value.openai_pending_posts || 0) > 0) {
    alerts.push(`还有 ${analysisOverview.value.openai_pending_posts} 条帖子待 OpenAI 分析。`)
  }

  if (Number(insightOverview.value.pending_insight_posts || 0) > 0) {
    alerts.push(`还有 ${insightOverview.value.pending_insight_posts} 条帖子待统计字段提取。`)
  }

  if (Number(insightOverview.value.failed_insight_posts || 0) > 0) {
    alerts.push(`统计字段提取失败 ${insightOverview.value.failed_insight_posts} 条，建议点开 AI 统计看板看看。`)
  }

  if (jobsSummaryUnavailable.value) {
    alerts.push('岗位摘要接口当前不可用，岗位健康度只能看到部分信息。')
  } else if (Number(jobsOverview.value.pending_posts || 0) > 0) {
    alerts.push(`还有 ${jobsOverview.value.pending_posts} 条帖子待岗位抽取。`)
  }

  return alerts
})

const applySchedulerConfig = (payload = {}) => {
  schedulerForm.value = {
    enabled: payload.enabled ?? true,
    intervalSeconds: Number(payload.interval_seconds ?? payload.intervalSeconds ?? 7200),
    defaultSourceId: Number(payload.default_source_id ?? payload.defaultSourceId ?? scrapeForm.value.sourceId ?? 1),
    defaultMaxPages: Number(payload.default_max_pages ?? payload.defaultMaxPages ?? scrapeForm.value.maxPages ?? 5),
    nextRunAt: payload.next_run_at || payload.nextRunAt || '',
    updatedAt: payload.updated_at || payload.updatedAt || ''
  }

  scrapeForm.value.sourceId = schedulerForm.value.defaultSourceId
  scrapeForm.value.maxPages = schedulerForm.value.defaultMaxPages
}

const fetchTaskRuns = async () => {
  loadingRuns.value = true
  try {
    const response = await adminApi.getTaskRuns({ limit: 10 })
    taskRuns.value = response.data.items || []
  } catch (error) {
    setFeedback('error', getErrorMessage(error, '加载任务记录失败'))
  } finally {
    loadingRuns.value = false
  }
}

const fetchTaskSummary = async () => {
  try {
    const response = await adminApi.getTaskSummary()
    taskSummary.value = response.data || null
  } catch (error) {
    console.warn('获取任务摘要失败，继续回退到任务记录:', error)
  }
}

const fetchSources = async () => {
  try {
    const response = await adminApi.getSources()
    const items = response.data.items || []
    if (items.length === 0) {
      return
    }

    sourceOptions.value = items.map((source) => ({
      label: `${source.name}（source_id=${source.id}）${source.is_active ? '' : ' / 已停用'}`,
      value: source.id,
      isActive: source.is_active
    }))

    const currentSourceExists = sourceOptions.value.some(
      (source) => source.value === scrapeForm.value.sourceId && source.isActive !== false
    )
    if (!currentSourceExists) {
      const firstActiveSource = sourceOptions.value.find((source) => source.isActive !== false)
      if (firstActiveSource) {
        scrapeForm.value.sourceId = firstActiveSource.value
      }
    }
  } catch (error) {
    console.warn('获取数据源列表失败，继续使用前端默认选项:', error)
  }
}

const fetchSchedulerConfig = async () => {
  schedulerLoading.value = true
  try {
    const response = await adminApi.getSchedulerConfig()
    applySchedulerConfig(response.data || {})
  } catch (error) {
    setFeedback('error', getErrorMessage(error, '加载定时抓取配置失败'))
  } finally {
    schedulerLoading.value = false
  }
}

const fetchAnalysisSummary = async () => {
  analysisLoading.value = true
  try {
    const response = await adminApi.getAnalysisSummary()
    analysisSummary.value = response.data || analysisSummary.value
  } catch (error) {
    setFeedback('error', getErrorMessage(error, '加载 AI 摘要失败'))
  } finally {
    analysisLoading.value = false
  }
}

const fetchInsightSummary = async () => {
  insightLoading.value = true
  try {
    const response = await adminApi.getInsightSummary()
    insightSummary.value = response.data || insightSummary.value
  } catch (error) {
    if (error?.response?.status === 404 || error?.response?.status === 405) {
      insightSummary.value = null
    } else {
      setFeedback('error', getErrorMessage(error, '加载 AI 统计看板失败'))
    }
  } finally {
    insightLoading.value = false
  }
}

const fetchJobSummary = async () => {
  jobsLoading.value = true
  jobsSummaryUnavailable.value = false
  try {
    const response = await adminApi.getJobSummary()
    jobSummary.value = response.data || jobSummary.value
  } catch (error) {
    if (error?.response?.status === 404 || error?.response?.status === 405) {
      jobsSummaryUnavailable.value = true
    } else {
      setFeedback('error', getErrorMessage(error, '加载岗位摘要失败'))
    }
  } finally {
    jobsLoading.value = false
  }
}

const fetchDuplicateSummary = async () => {
  duplicateLoading.value = true
  try {
    const response = await adminApi.getDuplicateSummary()
    duplicateSummary.value = response.data || duplicateSummary.value
  } catch (error) {
    setFeedback('error', getErrorMessage(error, '加载重复治理摘要失败'))
  } finally {
    duplicateLoading.value = false
  }
}

const refreshOverview = async () => {
  overviewRefreshing.value = true
  try {
    await Promise.all([
      fetchTaskSummary(),
      fetchTaskRuns(),
      fetchSchedulerConfig(),
      fetchAnalysisSummary(),
      fetchInsightSummary(),
      fetchJobSummary(),
      fetchDuplicateSummary()
    ])
  } finally {
    overviewRefreshing.value = false
  }
}

const refreshAfterTask = async ({ includeAnalysis = false, includeInsight = false, includeJobs = false, includeDuplicate = false } = {}) => {
  const tasks = [fetchTaskRuns(), fetchTaskSummary()]
  if (includeAnalysis) {
    tasks.push(fetchAnalysisSummary())
  }
  if (includeInsight) {
    tasks.push(fetchInsightSummary())
  }
  if (includeJobs) {
    tasks.push(fetchJobSummary())
  }
  if (includeDuplicate) {
    tasks.push(fetchDuplicateSummary())
  }
  await Promise.all(tasks)
}

const refreshTaskStatus = async () => {
  await Promise.all([fetchTaskRuns(), fetchTaskSummary()])
}

const canRetryTask = (taskType) => {
  return ['manual_scrape', 'scheduled_scrape', 'attachment_backfill', 'duplicate_backfill', 'ai_analysis', 'job_extraction', 'ai_job_extraction'].includes(taskType)
}

const getRetryRefreshOptions = (taskType) => {
  if (taskType === 'manual_scrape' || taskType === 'scheduled_scrape') {
    return { includeAnalysis: true, includeInsight: true, includeJobs: true, includeDuplicate: true }
  }
  if (taskType === 'attachment_backfill') {
    return { includeAnalysis: true, includeInsight: true, includeJobs: true, includeDuplicate: true }
  }
  if (taskType === 'ai_analysis') {
    return { includeAnalysis: true, includeInsight: true }
  }
  if (taskType === 'duplicate_backfill') {
    return { includeDuplicate: true }
  }
  if (taskType === 'job_extraction' || taskType === 'ai_job_extraction') {
    return { includeJobs: true, includeDuplicate: true }
  }
  return {}
}

const retryTaskRun = async (run) => {
  const taskType = run?.task_type
  if (!canRetryTask(taskType)) {
    setFeedback('error', '这个任务类型暂时不支持一键重试')
    return
  }

  retryingTaskId.value = run?.id || ''
  const params = run?.params || {}
  const refreshOptions = getRetryRefreshOptions(taskType)

  try {
    let response = null

    if (taskType === 'manual_scrape' || taskType === 'scheduled_scrape') {
      const payload = {
        source_id: Number(params.source_id ?? scrapeForm.value.sourceId ?? 1),
        max_pages: Number(params.max_pages ?? scrapeForm.value.maxPages ?? 5)
      }
      response = await adminApi.runScrape(payload)
    } else if (taskType === 'attachment_backfill') {
      const payload = {
        limit: Number(params.limit ?? backfillForm.value.limit ?? 100)
      }
      if (params.source_id !== undefined && params.source_id !== null && params.source_id !== '') {
        payload.source_id = Number(params.source_id)
      }
      response = await adminApi.backfillAttachments(payload)
    } else if (taskType === 'duplicate_backfill') {
      response = await adminApi.backfillDuplicates({
        limit: Number(params.limit ?? duplicateBackfillForm.value.limit ?? 200)
      })
    } else if (taskType === 'ai_analysis') {
      const payload = {
        limit: Number(params.limit ?? analysisForm.value.limit ?? 100),
        only_unanalyzed: Boolean(params.only_unanalyzed ?? analysisForm.value.onlyUnanalyzed ?? true)
      }
      if (params.source_id !== undefined && params.source_id !== null && params.source_id !== '') {
        payload.source_id = Number(params.source_id)
      }
      response = await adminApi.runAiAnalysis(payload)
    } else if (taskType === 'job_extraction' || taskType === 'ai_job_extraction') {
      const payload = {
        limit: Number(params.limit ?? jobsForm.value.limit ?? 100),
        only_unindexed: params.only_unindexed ?? true,
        use_ai: Boolean(params.use_ai ?? false)
      }
      if (params.source_id !== undefined && params.source_id !== null && params.source_id !== '') {
        payload.source_id = Number(params.source_id)
      }
      response = await adminApi.runJobExtraction(payload)
    }

    setFeedback('success', response?.data?.message || '重试任务已提交')
    await refreshAfterTask(refreshOptions)
  } catch (error) {
    if (shouldRefreshAfterTaskError(error)) {
      await refreshAfterTask(refreshOptions)
    }
    setFeedback('error', getErrorMessage(error, '重试任务失败'))
  } finally {
    retryingTaskId.value = ''
  }
}

const shouldRefreshAfterTaskError = (error) => {
  const status = error?.response?.status
  return error?.code === 'ECONNABORTED' || status === 409
}

const saveSchedulerConfig = async () => {
  schedulerSaving.value = true
  try {
    const payload = {
      enabled: schedulerForm.value.enabled,
      interval_seconds: schedulerForm.value.intervalSeconds,
      default_source_id: schedulerForm.value.defaultSourceId,
      default_max_pages: schedulerForm.value.defaultMaxPages
    }
    const response = await adminApi.updateSchedulerConfig(payload)
    const configPayload = response.data?.config || payload
    applySchedulerConfig(configPayload)
    setFeedback('success', response.data?.message || '定时抓取配置已更新')
  } catch (error) {
    setFeedback('error', getErrorMessage(error, '保存定时抓取配置失败'))
  } finally {
    schedulerSaving.value = false
  }
}

const runScrapeTask = async () => {
  scrapeRunning.value = true
  try {
    const response = await adminApi.runScrape({
      source_id: scrapeForm.value.sourceId,
      max_pages: scrapeForm.value.maxPages
    })
    setFeedback('success', response.data.message)
    await refreshAfterTask({ includeAnalysis: true, includeInsight: true, includeJobs: true, includeDuplicate: true })
  } catch (error) {
    if (shouldRefreshAfterTaskError(error)) {
      await refreshAfterTask({ includeAnalysis: true, includeInsight: true, includeJobs: true, includeDuplicate: true })
    }
    setFeedback('error', getErrorMessage(error, '手动抓取失败'))
  } finally {
    scrapeRunning.value = false
  }
}

const runBackfillTask = async () => {
  backfillRunning.value = true
  try {
    const payload = {
      limit: backfillForm.value.limit
    }
    if (backfillForm.value.sourceId) {
      payload.source_id = Number(backfillForm.value.sourceId)
    }

    const response = await adminApi.backfillAttachments(payload)
    setFeedback('success', response.data.message)
    await refreshAfterTask({ includeAnalysis: true, includeInsight: true, includeJobs: true, includeDuplicate: true })
  } catch (error) {
    if (shouldRefreshAfterTaskError(error)) {
      await refreshAfterTask({ includeAnalysis: true, includeInsight: true, includeJobs: true, includeDuplicate: true })
    }
    setFeedback('error', getErrorMessage(error, '历史附件补处理失败'))
  } finally {
    backfillRunning.value = false
  }
}

const runAiAnalysisTask = async () => {
  analysisRunning.value = true
  try {
    const payload = {
      limit: analysisForm.value.limit,
      only_unanalyzed: analysisForm.value.onlyUnanalyzed
    }
    if (analysisForm.value.sourceId) {
      payload.source_id = Number(analysisForm.value.sourceId)
    }

    const response = await adminApi.runAiAnalysis(payload)
    setFeedback('success', response.data.message)
    await refreshAfterTask({ includeAnalysis: true, includeInsight: true })
  } catch (error) {
    if (shouldRefreshAfterTaskError(error)) {
      await refreshAfterTask({ includeAnalysis: true, includeInsight: true })
    }
    setFeedback('error', getErrorMessage(error, 'AI 分析失败'))
  } finally {
    analysisRunning.value = false
  }
}

const runDuplicateBackfillTask = async () => {
  duplicateBackfillRunning.value = true
  try {
    const response = await adminApi.backfillDuplicates({
      limit: duplicateBackfillForm.value.limit
    })
    setFeedback('success', response.data.message)
    await refreshAfterTask({ includeDuplicate: true })
  } catch (error) {
    if (shouldRefreshAfterTaskError(error)) {
      await refreshAfterTask({ includeDuplicate: true })
    }
    setFeedback('error', getErrorMessage(error, '历史去重补齐失败'))
  } finally {
    duplicateBackfillRunning.value = false
  }
}

const runJobExtractionTask = async () => {
  jobsRunning.value = true
  try {
    const payload = {
      limit: jobsForm.value.limit,
      only_unindexed: jobsForm.value.onlyPending,
      use_ai: jobsForm.value.useAi && openaiReady.value
    }
    if (jobsForm.value.sourceId) {
      payload.source_id = Number(jobsForm.value.sourceId)
    }

    const response = await adminApi.runJobExtraction(payload)
    setFeedback('success', response.data.message || '岗位级抽取任务已启动')
    await refreshAfterTask({ includeJobs: true, includeDuplicate: true })
  } catch (error) {
    if (shouldRefreshAfterTaskError(error)) {
      await refreshAfterTask({ includeJobs: true, includeDuplicate: true })
    }
    if (error?.response?.status === 404 || error?.response?.status === 405) {
      setFeedback('error', '后端还没开放岗位级抽取接口，请先完成后端对接')
    } else {
      setFeedback('error', getErrorMessage(error, '岗位级抽取失败'))
    }
  } finally {
    jobsRunning.value = false
  }
}

const setFeedback = (type, message) => {
  feedback.value = { type, message }
}

const getTaskTypeLabel = (taskType) => {
  const labels = {
    manual_scrape: '手动抓取最新数据',
    attachment_backfill: '补处理历史附件',
    duplicate_backfill: '历史去重补齐',
    scheduled_scrape: '定时抓取',
    ai_analysis: 'OpenAI 分析',
    job_extraction: '岗位级抽取',
    ai_job_extraction: '岗位级抽取'
  }
  return labels[taskType] || taskType
}
const getAnalysisProviderLabel = (provider) => {
  const labels = {
    openai: 'OpenAI',
    rule: '规则分析'
  }
  return labels[provider] || provider || '未知来源'
}
const isRunningStatus = (status) => ['queued', 'pending', 'running', 'processing'].includes(status)

const parseTimeToMs = (value) => {
  if (!value) return null
  const time = new Date(value).getTime()
  return Number.isFinite(time) ? time : null
}

const getTaskHeartbeatAt = (run) => run?.heartbeat_at || run?.heartbeatAt || run?.started_at || run?.startedAt || ''

const getTaskProgress = (run) => {
  const rawValue = Number(run?.progress)
  if (Number.isFinite(rawValue)) {
    return Math.max(0, Math.min(Math.round(rawValue), 100))
  }
  if (run?.status === 'success') return 100
  if (run?.status === 'failed') return 100
  return 0
}

const getDefaultTaskPhase = (run) => {
  if (run?.status === 'success') return '执行完成'
  if (run?.status === 'failed') return '执行失败'
  if (run?.status === 'queued' || run?.status === 'pending') return '排队等待执行'
  if (isRunningStatus(run?.status)) return '正在执行'
  return ''
}

const isTaskPossiblyStuck = (run) => {
  if (!isRunningStatus(run?.status)) return false
  const heartbeatMs = parseTimeToMs(getTaskHeartbeatAt(run))
  if (heartbeatMs === null) return false
  return nowTs.value - heartbeatMs >= TASK_HEARTBEAT_STALE_MS
}

const getTaskStatusClass = (status, run) => {
  if (status === 'success') {
    return 'bg-emerald-100 text-emerald-700'
  }
  if (isTaskPossiblyStuck(run)) {
    return 'bg-red-100 text-red-700'
  }
  if (status === 'queued' || status === 'pending') {
    return 'bg-slate-100 text-slate-700'
  }
  if (isRunningStatus(status)) {
    return 'bg-amber-100 text-amber-700'
  }
  return 'bg-red-100 text-red-700'
}

const getTaskStatusLabel = (status, run) => {
  if (status === 'success') return '完成'
  if (isTaskPossiblyStuck(run)) return '可能卡住'
  if (status === 'queued' || status === 'pending') return '排队中'
  if (isRunningStatus(status)) return '运行中'
  return '失败'
}

const normalizeSummaryResponse = (data) => {
  if (!data) return null
  const candidate =
    data.latest_success_run ||
    data.latest_success_task ||
    data.latest_success ||
    data.last_success ||
    data

  return normalizeTaskRun(candidate)
}

const normalizeTaskRun = (run) => {
  if (!run) return null
  const finishedAt = run.finished_at || run.finishedAt || run.last_success_at || run.lastSuccessAt
  return {
    taskType: run.task_type || run.taskType || '',
    summary: run.summary || '',
    status: run.status || '',
    finishedAt: finishedAt || run.started_at || run.startedAt || '',
    failureReason: run.failure_reason || run.error || run.details?.failure_reason || run.details?.error || ''
  }
}

const getDetailValue = (details, ...keys) => {
  for (const key of keys) {
    if (details && details[key] !== undefined && details[key] !== null) {
      return details[key]
    }
  }
  return 0
}
const getTaskParam = (run, ...keys) => {
  const sources = [run?.params, run?.details?.params, run?.details?.request_params, run]

  for (const source of sources) {
    if (!source) continue
    for (const key of keys) {
      if (source[key] !== undefined && source[key] !== null && source[key] !== '') {
        return source[key]
      }
    }
  }

  return null
}

const formatSourceParam = (run) => {
  const sourceId = getTaskParam(run, 'source_id', 'sourceId')
  if (sourceId === null || sourceId === undefined || sourceId === '') {
    return '全部数据源'
  }

  const matchedSource = sourceOptions.value.find((source) => source.value === Number(sourceId))
  if (matchedSource) {
    return matchedSource.label
  }

  return `source_id=${sourceId}`
}

const getTaskFailureReason = (run) => {
  const candidates = [
    run?.failure_reason,
    run?.error,
    run?.details?.failure_reason,
    run?.details?.error
  ]
  return candidates.find((item) => item) || ''
}

const formatDurationMs = (durationMs) => {
  const normalized = Number(durationMs)
  if (!Number.isFinite(normalized) || normalized < 0) return '--'

  if (normalized < 1000) return `${Math.round(normalized)}ms`
  const seconds = Math.floor(normalized / 1000)
  if (seconds < 60) return `${seconds}秒`
  const minutes = Math.floor(seconds / 60)
  const restSeconds = seconds % 60
  return `${minutes}分${restSeconds}秒`
}

const getTaskElapsedMs = (run) => {
  const durationMs = Number(run?.duration_ms)
  if (Number.isFinite(durationMs) && durationMs >= 0) {
    return durationMs
  }

  const startedMs = parseTimeToMs(run?.started_at || run?.startedAt)
  if (startedMs === null) return null

  const finishedMs = parseTimeToMs(run?.finished_at || run?.finishedAt)
  const endMs = finishedMs === null ? nowTs.value : finishedMs
  const elapsedMs = endMs - startedMs
  return elapsedMs >= 0 ? elapsedMs : null
}

const formatDuration = (run) => formatDurationMs(getTaskElapsedMs(run))
const formatRunningElapsed = (run) => formatDurationMs(getTaskElapsedMs(run))

const isTaskExpanded = (taskId) => expandedTaskIds.value.includes(taskId)

const toggleTaskExpanded = (taskId) => {
  if (isTaskExpanded(taskId)) {
    expandedTaskIds.value = expandedTaskIds.value.filter((id) => id !== taskId)
    return
  }
  expandedTaskIds.value = [...expandedTaskIds.value, taskId]
}

const formatIntervalLabel = (secondsValue) => {
  const seconds = Number(secondsValue || 0)
  if (!Number.isFinite(seconds) || seconds <= 0) return '--'
  if (seconds < 60) return `${seconds} 秒`
  if (seconds < 3600) return `${Math.round(seconds / 60)} 分钟`
  if (seconds % 3600 === 0) return `${seconds / 3600} 小时`
  return `${Math.floor(seconds / 3600)} 小时 ${Math.round((seconds % 3600) / 60)} 分钟`
}

const formatDateTime = (value) => {
  if (!value) return ''
  const date = new Date(value)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const getRelativeTimeLabel = (value) => {
  if (!value) return '--'
  const diffMs = Date.now() - new Date(value).getTime()
  if (diffMs < 0) return '刚刚'

  const minutes = Math.floor(diffMs / (1000 * 60))
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前`

  const days = Math.floor(hours / 24)
  if (days < 7) return `${days} 天前`

  return formatDateTime(value)
}

const getErrorMessage = (error, fallback) => {
  const status = error?.response?.status

  if (status >= 500) {
    return '后端执行任务失败了，请稍后再试'
  }
  if (error?.code === 'ECONNABORTED') {
    return '请求超时了，任务可能还在后台继续跑，我已经帮你刷新了任务记录'
  }
  if (error?.response?.data?.detail) {
    return error.response.data.detail
  }
  return fallback
}

onMounted(async () => {
  taskPollingTimerId.value = window.setInterval(async () => {
    nowTs.value = Date.now()
    if (backendRunningTasks.value.length === 0 || taskPollingInFlight.value) {
      return
    }
    taskPollingInFlight.value = true
    try {
      await refreshTaskStatus()
    } finally {
      taskPollingInFlight.value = false
    }
  }, TASK_POLL_INTERVAL_MS)

  await fetchSources()
  await refreshOverview()
})

onUnmounted(() => {
  if (taskPollingTimerId.value) {
    window.clearInterval(taskPollingTimerId.value)
    taskPollingTimerId.value = null
  }
})
</script>
