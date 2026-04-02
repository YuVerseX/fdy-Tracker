<template>
  <div class="min-h-screen">
    <main class="app-shell max-w-7xl">
      <AppPageHeader
        eyebrow="后台控制台"
        title="管理台"
        description="查看系统状态、处理数据任务，并跟踪最近执行结果。"
        action-label="返回前台"
        :action-to="{ name: 'PostList' }"
      />

      <AppNotice
        v-if="dashboard.feedback.message"
        :tone="dashboard.feedback.type === 'error' ? 'danger' : dashboard.feedback.type"
        :description="dashboard.feedback.message"
      />

      <AppNotice
        v-if="dashboard.adminAuthorized && dashboard.activeTaskHints.length > 0"
        tone="warning"
        title="有活跃任务"
        :description="`${dashboard.activeTaskHints.join('、')}。你可以先继续查看页面，任务中心会按当前同步状态更新。`"
      />

      <section v-if="!dashboard.adminAuthorized" class="app-surface app-surface--padding-lg">
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
                class="app-input"
                placeholder="输入账号"
              >
            </div>
            <div>
              <label class="mb-2 block text-sm font-medium text-slate-700">密码</label>
              <input
                v-model="dashboard.adminAuthForm.password"
                type="password"
                autocomplete="current-password"
                class="app-input"
                placeholder="输入密码"
              >
            </div>
            <button
              type="submit"
              :disabled="dashboard.adminAuthChecking"
              class="app-button app-button--md app-button--primary disabled:cursor-not-allowed disabled:opacity-60"
            >
              {{ dashboard.adminAuthChecking ? '登录验证中...' : '进入管理台' }}
            </button>
          </form>
        </div>
      </section>

      <template v-else>
        <section class="app-surface app-surface--padding-sm">
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
                class="app-button app-button--sm app-button--secondary"
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
          :canceling-task-id="dashboard.taskRunsSection.cancelingTaskId"
          :expanded-task-ids="dashboard.taskRunsSection.expandedTaskIds"
          :now-ts="dashboard.taskRunsSection.nowTs"
          :source-options="dashboard.taskRunsSection.sourceOptions"
          :heartbeat-stale-ms="dashboard.taskRunsSection.heartbeatStaleMs"
          :sync-status="dashboard.taskRunsSection.syncStatus"
          :refresh-task-status="dashboard.refreshTaskStatus"
          :retry-task-run="dashboard.retryTaskRun"
          :cancel-task-run="dashboard.cancelTaskRun"
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
