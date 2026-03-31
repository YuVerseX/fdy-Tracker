<template>
  <div class="min-h-screen">
    <main class="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
      <AppPageHeader
        eyebrow="后台控制台"
        title="管理台"
        description="查看系统状态、处理数据任务，并跟踪最近执行结果。"
        action-label="返回前台"
        :action-to="{ name: 'PostList' }"
      />

      <AppNotice
        v-if="dashboard.feedback.message"
        :tone="dashboard.feedback.type === 'success' ? 'success' : 'danger'"
        :description="dashboard.feedback.message"
      />

      <AppNotice
        v-if="dashboard.adminAuthorized && dashboard.activeTaskHints.length > 0"
        tone="warning"
        title="有任务正在处理"
        :description="`${dashboard.activeTaskHints.join('、')}。你可以先继续查看页面，稍后刷新任务中心获取最新结果。`"
      />

      <section v-if="!dashboard.adminAuthorized" class="rounded-[28px] border border-slate-200 bg-white/90 p-6 shadow-sm backdrop-blur lg:p-8">
        <div class="flex flex-col gap-8 lg:flex-row lg:items-start lg:justify-between">
          <div class="max-w-2xl">
            <AppSectionHeader
              title="登录后继续"
              description="登录后可以查看任务状态、发起处理任务，并调整自动抓取设置。"
            />
            <p class="mt-4 text-sm leading-7 text-slate-500">
              如果暂时无法登录，请联系系统管理员检查管理账号设置。
            </p>
          </div>

          <form class="w-full max-w-md space-y-4" @submit.prevent="dashboard.submitAdminLogin">
            <AppNotice
              v-if="dashboard.adminAuthError"
              tone="warning"
              :description="dashboard.adminAuthError"
            />
            <div>
              <label class="mb-2 block text-sm font-medium text-slate-700">账号</label>
              <input
                v-model.trim="dashboard.adminAuthForm.username"
                type="text"
                autocomplete="username"
                class="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 shadow-sm outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-200"
                placeholder="输入账号"
              >
            </div>
            <div>
              <label class="mb-2 block text-sm font-medium text-slate-700">密码</label>
              <input
                v-model="dashboard.adminAuthForm.password"
                type="password"
                autocomplete="current-password"
                class="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 shadow-sm outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-200"
                placeholder="输入密码"
              >
            </div>
            <button
              type="submit"
              :disabled="dashboard.adminAuthChecking"
              class="inline-flex items-center justify-center rounded-full bg-sky-700 px-5 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {{ dashboard.adminAuthChecking ? '登录验证中...' : '进入管理台' }}
            </button>
          </form>
        </div>
      </section>

      <template v-else>
        <section class="rounded-[28px] border border-slate-200 bg-white/88 p-4 shadow-sm backdrop-blur">
          <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <AppTabNav
              :model-value="dashboard.activeAdminSection"
              :items="dashboard.adminSectionOptions"
              aria-label="管理台分区"
              @update:modelValue="dashboard.setActiveSection"
            />
            <div class="flex flex-wrap items-center gap-3 text-sm text-slate-500">
              <span v-if="dashboard.adminSavedUsername">当前账号：{{ dashboard.adminSavedUsername }}</span>
              <button
                type="button"
                class="inline-flex items-center rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors duration-200 hover:border-sky-300 hover:text-sky-700"
                @click="dashboard.logoutAdmin"
              >
                退出登录
              </button>
            </div>
          </div>
        </section>

        <AdminOverviewSection
          v-if="dashboard.activeAdminSection === 'overview'"
          :health="dashboard.overviewSection.health"
          :refreshing="dashboard.overviewSection.refreshing"
          :focus-items="dashboard.overviewSection.focusItems"
          :cards="dashboard.overviewSection.cards"
          :runtime-copy="dashboard.overviewSection.runtimeCopy"
          :structured-field-cards="dashboard.overviewSection.structuredFieldCards"
          :structure-refresh-label="dashboard.overviewSection.structureRefreshLabel"
          :refresh-overview="dashboard.refreshOverview"
          :refresh-structured-summary="dashboard.refreshStructuredSummary"
        />
        <AdminProcessingSection
          v-else-if="dashboard.activeAdminSection === 'processing'"
          :processing-mode="dashboard.processingSection.mode"
          :processing-tab-options="dashboard.processingSection.tabOptions"
          :set-processing-mode="dashboard.setProcessingMode"
          :base-section="dashboard.processingSection.baseSection"
          :ai-section="dashboard.processingSection.aiSection"
        />
        <AdminTaskRunsSection
          v-else-if="dashboard.activeAdminSection === 'tasks'"
          :task-runs="dashboard.taskRunsSection.taskRuns"
          :task-runs-loaded="dashboard.taskRunsSection.taskRunsLoaded"
          :loading-runs="dashboard.taskRunsSection.loadingRuns"
          :retrying-task-id="dashboard.taskRunsSection.retryingTaskId"
          :retrying-task-action-key="dashboard.taskRunsSection.retryingTaskActionKey"
          :expanded-task-ids="dashboard.taskRunsSection.expandedTaskIds"
          :now-ts="dashboard.taskRunsSection.nowTs"
          :source-options="dashboard.taskRunsSection.sourceOptions"
          :heartbeat-stale-ms="dashboard.taskRunsSection.heartbeatStaleMs"
          :refresh-task-status="dashboard.refreshTaskStatus"
          :retry-task-run="dashboard.retryTaskRun"
          :toggle-task-expanded="dashboard.toggleTaskExpanded"
          :can-retry-task="dashboard.canRetryTask"
        />
        <AdminSystemSection
          v-else
          :scheduler-form="dashboard.systemSection.schedulerForm"
          :scheduler-loaded="dashboard.systemSection.schedulerLoaded"
          :scheduler-loading="dashboard.systemSection.schedulerLoading"
          :scheduler-saving="dashboard.systemSection.schedulerSaving"
          :source-options="dashboard.systemSection.sourceOptions"
          :status-badge-label="dashboard.systemSection.statusBadgeLabel"
          :summary-cards="dashboard.systemSection.summaryCards"
          :helper-notice="dashboard.systemSection.helperNotice"
          :notice-class="dashboard.systemSection.noticeClass"
          :status-line="dashboard.systemSection.statusLine"
          :next-run-line="dashboard.systemSection.nextRunLine"
          :save-scheduler-config="dashboard.saveSchedulerConfig"
          :refresh-scheduler-config="dashboard.refreshSchedulerConfig"
        />
      </template>
    </main>
  </div>
</template>

<script setup>
import AppNotice from '../components/ui/AppNotice.vue'
import AppPageHeader from '../components/ui/AppPageHeader.vue'
import AppSectionHeader from '../components/ui/AppSectionHeader.vue'
import AppTabNav from '../components/ui/AppTabNav.vue'
import AdminOverviewSection from './admin/sections/AdminOverviewSection.vue'
import AdminProcessingSection from './admin/sections/AdminProcessingSection.vue'
import AdminSystemSection from './admin/sections/AdminSystemSection.vue'
import AdminTaskRunsSection from './admin/sections/AdminTaskRunsSection.vue'
import { normalizeAdminDashboardBindings, useAdminDashboardState } from './admin/useAdminDashboardState.js'

const dashboard = normalizeAdminDashboardBindings(useAdminDashboardState())
</script>
