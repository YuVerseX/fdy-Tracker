<template>
  <div class="min-h-screen bg-sky-50">
    <header class="sticky top-0 z-10 bg-white shadow-sm">
      <div class="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
        <div>
          <h1 class="text-2xl font-bold text-sky-900">管理台</h1>
          <p class="mt-1 text-sm text-gray-500">按任务目标拆分入口，避免把基础处理和 AI 增强混在一起。</p>
        </div>
        <router-link :to="{ name: 'PostList' }" class="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors duration-200 hover:bg-gray-50">
          返回前台
        </router-link>
      </div>
    </header>

    <main class="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
      <div v-if="dashboard.feedback.message" :class="dashboard.feedbackClass" class="rounded-lg border px-4 py-3 text-sm">
        {{ dashboard.feedback.message }}
      </div>

      <div v-if="dashboard.adminAuthorized && dashboard.activeTaskHints.length > 0" class="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        当前有任务运行中：{{ dashboard.activeTaskHints.join('、') }}。可以先继续浏览，稍后点“刷新状态”看结果。
      </div>

      <section v-if="!dashboard.adminAuthorized" class="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <div class="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div class="max-w-xl">
            <h2 class="text-lg font-semibold text-sky-900">后台登录</h2>
            <p class="mt-2 text-sm text-gray-600">管理台现在单独受保护。这里的操作会直接触发抓取、补处理、分析、岗位索引和调度配置更新。</p>
            <p class="mt-2 text-xs text-gray-500">如果页面提示“后台鉴权还没配置”，先在后端环境变量里补 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD`，再重启服务。</p>
          </div>

          <form class="w-full max-w-md space-y-4" @submit.prevent="dashboard.submitAdminLogin">
            <div v-if="dashboard.adminAuthError" class="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              {{ dashboard.adminAuthError }}
            </div>
            <div>
              <label class="mb-2 block text-sm font-medium text-gray-700">账号</label>
              <input v-model.trim="dashboard.adminAuthForm.username" type="text" autocomplete="username" class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-sky-600" placeholder="输入后台账号">
            </div>
            <div>
              <label class="mb-2 block text-sm font-medium text-gray-700">密码</label>
              <input v-model="dashboard.adminAuthForm.password" type="password" autocomplete="current-password" class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-sky-600" placeholder="输入后台密码">
            </div>
            <button type="submit" :disabled="dashboard.adminAuthChecking" class="inline-flex items-center justify-center rounded-lg bg-sky-700 px-4 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-60">
              {{ dashboard.adminAuthChecking ? '登录验证中...' : '进入管理台' }}
            </button>
          </form>
        </div>
      </section>

      <template v-else>
        <section class="rounded-lg border border-slate-200 bg-white px-4 py-4 shadow-sm">
          <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div class="flex flex-wrap gap-2">
              <button
                v-for="item in dashboard.adminSectionOptions"
                :key="item.value"
                type="button"
                class="inline-flex items-center rounded-full px-4 py-2 text-sm font-medium transition-colors duration-200"
                :class="dashboard.activeAdminSection === item.value ? 'bg-sky-700 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'"
                @click="dashboard.setActiveSection(item.value)"
              >
                {{ item.label }}
              </button>
            </div>
            <div class="flex flex-wrap items-center gap-3 text-sm text-gray-500">
              <span v-if="dashboard.adminSavedUsername">当前账号：{{ dashboard.adminSavedUsername }}</span>
              <button type="button" class="inline-flex items-center rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition-colors duration-200 hover:bg-gray-50" @click="dashboard.logoutAdmin">
                退出登录
              </button>
            </div>
          </div>
        </section>

        <AdminOverviewSection
          v-if="dashboard.activeAdminSection === 'overview'"
          :health="dashboard.overviewSection.health"
          :refreshing="dashboard.overviewSection.refreshing"
          :cards="dashboard.overviewSection.cards"
          :runtime-copy="dashboard.overviewSection.runtimeCopy"
          :structured-field-cards="dashboard.overviewSection.structuredFieldCards"
          :structure-refresh-label="dashboard.overviewSection.structureRefreshLabel"
          :refresh-overview="dashboard.refreshOverview"
          :refresh-structured-summary="dashboard.refreshStructuredSummary"
        />
        <AdminDataProcessingSection
          v-else-if="dashboard.activeAdminSection === 'processing'"
          :collect-panel="dashboard.dataProcessingSection.collectPanel"
          :duplicate-panel="dashboard.dataProcessingSection.duplicatePanel"
          :analysis-panel="dashboard.dataProcessingSection.analysisPanel"
          :jobs-panel="dashboard.dataProcessingSection.jobsPanel"
          :source-options="dashboard.dataProcessingSection.sourceOptions"
          :jobs-summary-unavailable="dashboard.dataProcessingSection.jobsSummaryUnavailable"
          :scrape-form="dashboard.dataProcessingSection.scrapeForm"
          :backfill-form="dashboard.dataProcessingSection.backfillForm"
          :duplicate-form="dashboard.dataProcessingSection.duplicateForm"
          :base-analysis-form="dashboard.dataProcessingSection.baseAnalysisForm"
          :job-index-form="dashboard.dataProcessingSection.jobIndexForm"
          :scrape-busy="dashboard.dataProcessingSection.scrapeBusy"
          :backfill-busy="dashboard.dataProcessingSection.backfillBusy"
          :duplicate-busy="dashboard.dataProcessingSection.duplicateBusy"
          :base-analysis-busy="dashboard.dataProcessingSection.baseAnalysisBusy"
          :job-index-busy="dashboard.dataProcessingSection.jobIndexBusy"
          :duplicate-loading="dashboard.dataProcessingSection.duplicateLoading"
          :analysis-loading="dashboard.dataProcessingSection.analysisLoading"
          :jobs-loading="dashboard.dataProcessingSection.jobsLoading"
          :run-scrape-task="dashboard.runScrapeTask"
          :run-backfill-task="dashboard.runBackfillTask"
          :run-duplicate-backfill-task="dashboard.runDuplicateBackfillTask"
          :run-base-analysis-task="dashboard.runBaseAnalysisTask"
          :run-job-index-task="dashboard.runJobIndexTask"
          :refresh-duplicate-summary="dashboard.refreshDuplicateSummary"
          :refresh-analysis-summary="dashboard.refreshAnalysisSummary"
          :refresh-job-summary="dashboard.refreshJobSummary"
        />
        <AdminAiEnhancementSection
          v-else-if="dashboard.activeAdminSection === 'ai-enhancement'"
          :runtime-copy="dashboard.aiEnhancementSection.runtimeCopy"
          :openai-ready="dashboard.aiEnhancementSection.openaiReady"
          :disabled-reason="dashboard.aiEnhancementSection.disabledReason"
          :panels="dashboard.aiEnhancementSection.panels"
          :source-options="dashboard.aiEnhancementSection.sourceOptions"
          :analysis-form="dashboard.aiEnhancementSection.analysisForm"
          :jobs-form="dashboard.aiEnhancementSection.jobsForm"
          :analysis-busy="dashboard.aiEnhancementSection.analysisBusy"
          :jobs-busy="dashboard.aiEnhancementSection.jobsBusy"
          :analysis-loading="dashboard.aiEnhancementSection.analysisLoading"
          :jobs-loading="dashboard.aiEnhancementSection.jobsLoading"
          :jobs-summary-unavailable="dashboard.aiEnhancementSection.jobsSummaryUnavailable"
          :latest-analysis-label="dashboard.aiEnhancementSection.latestAnalysisLabel"
          :latest-jobs-label="dashboard.aiEnhancementSection.latestJobsLabel"
          :run-ai-analysis-task="dashboard.runAiAnalysisTask"
          :run-ai-job-extraction-task="dashboard.runAiJobExtractionTask"
          :refresh-analysis-summary="dashboard.refreshAnalysisSummary"
          :refresh-job-summary="dashboard.refreshJobSummary"
        />
        <AdminSystemSection
          v-else-if="dashboard.activeAdminSection === 'system'"
          :scheduler-form="dashboard.systemSection.schedulerForm"
          :scheduler-loaded="dashboard.systemSection.schedulerLoaded"
          :scheduler-loading="dashboard.systemSection.schedulerLoading"
          :scheduler-saving="dashboard.systemSection.schedulerSaving"
          :source-options="dashboard.systemSection.sourceOptions"
          :notice-class="dashboard.systemSection.noticeClass"
          :status-line="dashboard.systemSection.statusLine"
          :next-run-line="dashboard.systemSection.nextRunLine"
          :save-scheduler-config="dashboard.saveSchedulerConfig"
          :refresh-scheduler-config="dashboard.refreshSchedulerConfig"
        />
        <AdminTaskRunsSection
          v-else
          :task-runs="dashboard.taskRunsSection.taskRuns"
          :task-runs-loaded="dashboard.taskRunsSection.taskRunsLoaded"
          :loading-runs="dashboard.taskRunsSection.loadingRuns"
          :retrying-task-id="dashboard.taskRunsSection.retryingTaskId"
          :expanded-task-ids="dashboard.taskRunsSection.expandedTaskIds"
          :now-ts="dashboard.taskRunsSection.nowTs"
          :source-options="dashboard.taskRunsSection.sourceOptions"
          :heartbeat-stale-ms="dashboard.taskRunsSection.heartbeatStaleMs"
          :refresh-task-status="dashboard.refreshTaskStatus"
          :retry-task-run="dashboard.retryTaskRun"
          :toggle-task-expanded="dashboard.toggleTaskExpanded"
          :can-retry-task="dashboard.canRetryTask"
        />
      </template>
    </main>
  </div>
</template>

<script setup>
import AdminAiEnhancementSection from './admin/sections/AdminAiEnhancementSection.vue'
import AdminDataProcessingSection from './admin/sections/AdminDataProcessingSection.vue'
import AdminOverviewSection from './admin/sections/AdminOverviewSection.vue'
import AdminSystemSection from './admin/sections/AdminSystemSection.vue'
import AdminTaskRunsSection from './admin/sections/AdminTaskRunsSection.vue'
import { normalizeAdminDashboardBindings, useAdminDashboardState } from './admin/useAdminDashboardState.js'

const dashboard = normalizeAdminDashboardBindings(useAdminDashboardState())
</script>
