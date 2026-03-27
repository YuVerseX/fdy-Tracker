<template>
  <div class="min-h-screen bg-sky-50">
    <!-- Header -->
    <header class="bg-white shadow-sm sticky top-0 z-10">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between gap-4">
        <div class="flex items-center gap-4">
          <button
            @click="goBack"
            class="p-2 hover:bg-gray-100 rounded-lg transition-colors duration-200 cursor-pointer"
          >
            <svg class="w-6 h-6 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <h1 class="text-2xl font-bold text-sky-900">招聘详情</h1>
        </div>
        <router-link
          :to="{ name: 'AdminDashboard' }"
          class="inline-flex items-center rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition-colors duration-200 hover:bg-gray-50"
        >
          管理台
        </router-link>
      </div>
    </header>

    <!-- Main Content -->
    <main class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div class="mb-4 rounded-lg border border-sky-100 bg-sky-50 px-4 py-3 text-sm text-sky-800">
        <p v-if="freshnessLoading">正在获取后台任务状态...</p>
        <p v-else-if="latestSuccessTask">
          最近后台成功任务：{{ getTaskTypeLabel(latestSuccessTask.taskType) }}，完成于
          {{ formatDateTime(latestSuccessTask.finishedAt) }}（{{ getRelativeTimeLabel(latestSuccessTask.finishedAt) }}）。
        </p>
        <p v-else-if="freshnessUnavailable">后台任务状态暂时不可用，不影响你查看当前详情。</p>
        <p v-else>还没有可展示的后台成功任务记录。</p>
      </div>

      <!-- Loading State -->
      <div v-if="loading" class="text-center py-12">
        <div class="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-sky-700"></div>
        <p class="mt-4 text-gray-600">加载中...</p>
      </div>

      <!-- Error State -->
      <div v-else-if="error" class="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
        <p class="text-red-600">{{ error }}</p>
        <button
          @click="fetchPostDetail"
          class="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors duration-200 cursor-pointer"
        >
          重试
        </button>
      </div>

      <!-- Post Detail -->
      <div v-else-if="post" class="bg-white rounded-lg shadow-sm">
        <!-- Header Section -->
        <div class="p-8 border-b border-gray-200">
          <div class="flex items-start justify-between mb-4">
            <h1 class="text-3xl font-bold text-sky-900 flex-1">{{ post.title }}</h1>
            <div class="ml-4 flex flex-col items-end gap-2">
              <span
                v-if="getCounselorScope(post)"
                class="inline-flex items-center px-4 py-2 rounded-full text-sm font-medium"
                :class="getCounselorScopeClass(post)"
              >
                {{ getCounselorScopeLabel(post) }}
              </span>
              <span
                v-if="hasCounselorJob(post)"
                class="inline-flex items-center px-4 py-2 rounded-full text-sm font-medium bg-cyan-100 text-cyan-800"
              >
                辅导员岗位{{ getCounselorJobsCount(post) ? ` · ${getCounselorJobsCount(post)}个` : '' }}
              </span>
            </div>
          </div>

          <!-- Meta Information -->
          <div class="flex flex-wrap gap-6 text-sm text-gray-600">
            <div v-if="post.publish_date" class="flex items-center gap-2">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              <span>发布日期：{{ formatDate(post.publish_date) }}</span>
            </div>

            <div v-if="post.source?.name" class="flex items-center gap-2">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
              </svg>
              <span>来源：{{ post.source.name }}</span>
            </div>

            <div v-if="post.confidence_score" class="flex items-center gap-2">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>匹配度：{{ (post.confidence_score * 100).toFixed(0) }}%</span>
            </div>
          </div>
        </div>

        <!-- Structured Fields Section -->
        <div v-if="preferredStructuredFields.length > 0 || supplementalFields.length > 0" class="p-8 border-t border-gray-200 bg-gray-50">
          <h2 class="text-xl font-semibold text-sky-900 mb-4 flex items-center gap-2">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
            </svg>
            结构化信息
          </h2>

          <div v-if="preferredStructuredFields.length > 0" class="mb-6">
            <div class="mb-4 rounded-lg border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
              当前这块优先展示岗位级结果，只有岗位里没有时才回退到原始字段，避免同名信息打架。
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div
                v-for="field in preferredStructuredFields"
                :key="`${field.field_name}-${field.field_value}`"
                class="bg-white rounded-lg p-4 shadow-sm border border-gray-200"
              >
                <div class="flex items-start gap-3">
                  <div class="flex-shrink-0">
                    <component :is="getFieldIcon(field.field_name)" class="w-5 h-5 text-sky-600" />
                  </div>
                  <div class="flex-1 min-w-0">
                    <div class="mb-1 flex flex-wrap items-center gap-2">
                      <div class="text-sm font-medium text-gray-500">{{ field.field_name }}</div>
                      <span
                        class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                        :class="field.source_class"
                      >
                        {{ field.source_label }}
                      </span>
                    </div>
                    <div class="text-base text-gray-900 font-medium break-words">{{ field.field_value }}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="supplementalFields.length > 0">
            <div class="mb-4 text-sm text-gray-500">
              下面这些是补充展示的原始解析字段；已经被岗位级结果覆盖的同名字段不再重复展示。
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div
              v-for="field in supplementalFields"
              :key="`${field.field_name}-${field.field_value}`"
              class="bg-white rounded-lg p-4 shadow-sm border border-gray-200"
            >
              <div class="flex items-start gap-3">
                <div class="flex-shrink-0">
                  <component :is="getFieldIcon(field.field_name)" class="w-5 h-5 text-sky-600" />
                </div>
                <div class="flex-1 min-w-0">
                  <div class="text-sm font-medium text-gray-500 mb-1">{{ field.field_name }}</div>
                  <div class="text-base text-gray-900 font-medium break-words">{{ field.field_value }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
        </div>

        <div v-if="post.analysis" class="p-8 border-t border-gray-200 bg-sky-50/70">
          <div class="mb-4 flex flex-wrap items-center gap-2">
            <h2 class="text-xl font-semibold text-sky-900">分析结果</h2>
            <span
              class="inline-flex items-center rounded-full px-3 py-1 text-xs font-medium"
              :class="getAnalysisProviderClass(post.analysis.analysis_provider)"
            >
              {{ getAnalysisProviderLabel(post.analysis.analysis_provider) }}
            </span>
            <span
              v-if="post.analysis.model_name"
              class="inline-flex items-center rounded-full bg-white px-3 py-1 text-xs font-medium text-gray-600 ring-1 ring-gray-200"
            >
              {{ post.analysis.model_name }}
            </span>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="rounded-lg bg-white p-4 shadow-sm border border-gray-200">
              <div class="text-sm font-medium text-gray-500">事件类型</div>
              <div class="mt-1 text-base font-semibold text-gray-900">{{ post.analysis.event_type || '--' }}</div>
            </div>
            <div class="rounded-lg bg-white p-4 shadow-sm border border-gray-200">
              <div class="text-sm font-medium text-gray-500">招聘阶段</div>
              <div class="mt-1 text-base font-semibold text-gray-900">{{ post.analysis.recruitment_stage || '--' }}</div>
            </div>
            <div class="rounded-lg bg-white p-4 shadow-sm border border-gray-200">
              <div class="text-sm font-medium text-gray-500">关注优先级</div>
              <div class="mt-1 text-base font-semibold text-gray-900">{{ formatPriority(post.analysis.tracking_priority) }}</div>
            </div>
            <div class="rounded-lg bg-white p-4 shadow-sm border border-gray-200">
              <div class="text-sm font-medium text-gray-500">学校/单位</div>
              <div class="mt-1 text-base font-semibold text-gray-900">{{ post.analysis.school_name || '--' }}</div>
            </div>
          </div>
          <div v-if="post.analysis.summary" class="mt-4 rounded-lg bg-white p-4 shadow-sm border border-gray-200">
            <div class="text-sm font-medium text-gray-500">摘要</div>
            <div class="mt-2 text-base leading-7 text-gray-800">{{ post.analysis.summary }}</div>
          </div>
        </div>

        <div v-if="normalizedJobItems.length > 0" class="p-8 border-t border-gray-200 bg-emerald-50/60">
          <h2 class="text-xl font-semibold text-sky-900 mb-4 flex items-center gap-2">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 17v-2a2 2 0 012-2h6m-6 4h6m-6-8h6m2 10H7a2 2 0 01-2-2V7a2 2 0 012-2h10a2 2 0 012 2v10a2 2 0 01-2 2z" />
            </svg>
            岗位级结果
          </h2>
          <div class="mb-4 text-sm text-emerald-800">
            共识别 {{ normalizedJobItems.length }} 个岗位{{ getCounselorJobsCount(post) ? `，其中辅导员岗 ${getCounselorJobsCount(post)} 个` : '' }}。
          </div>
          <div class="space-y-3">
            <article
              v-for="(job, index) in normalizedJobItems"
              :key="job.id || job.job_id || `${job.job_name || '岗位'}-${index}`"
              class="rounded-lg border border-emerald-100 bg-white p-4"
            >
              <div class="flex flex-wrap items-center justify-between gap-3">
                <h3 class="text-base font-semibold text-gray-900">{{ job.job_name || `岗位 ${index + 1}` }}</h3>
                <span
                  v-if="job.is_counselor_job"
                  class="inline-flex items-center rounded-full px-3 py-1 text-xs font-medium bg-emerald-100 text-emerald-800"
                >
                  辅导员岗位
                </span>
              </div>
              <div class="mt-3 flex flex-wrap gap-2 text-xs">
                <span v-if="job.headcount" class="inline-flex items-center rounded bg-orange-50 px-2 py-1 text-orange-700">人数: {{ job.headcount }}</span>
                <span v-if="job.education" class="inline-flex items-center rounded bg-purple-50 px-2 py-1 text-purple-700">学历: {{ job.education }}</span>
                <span v-if="job.major" class="inline-flex items-center rounded bg-blue-50 px-2 py-1 text-blue-700">专业: {{ job.major }}</span>
                <span v-if="job.location" class="inline-flex items-center rounded bg-green-50 px-2 py-1 text-green-700">地点: {{ job.location }}</span>
                <span v-if="job.source" class="inline-flex items-center rounded bg-gray-100 px-2 py-1 text-gray-700">来源: {{ job.source }}</span>
              </div>
            </article>
          </div>
        </div>

        <!-- Attachments Section -->
        <div v-if="post.attachments && post.attachments.length > 0" class="p-8 border-t border-gray-200 bg-sky-50/60">
          <h2 class="text-xl font-semibold text-sky-900 mb-4 flex items-center gap-2">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828L18 9.828a4 4 0 10-5.656-5.656L5.757 10.76a6 6 0 108.486 8.486L20.5 13" />
            </svg>
            附件
          </h2>
          <div class="space-y-3">
            <a
              v-for="attachment in post.attachments"
              :key="attachment.id || attachment.file_url"
              :href="attachment.file_url"
              target="_blank"
              rel="noopener noreferrer"
              class="flex items-start justify-between gap-4 rounded-lg border border-sky-100 bg-white px-4 py-4 transition-colors duration-200 hover:border-sky-300 hover:bg-sky-50"
            >
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <div class="text-base font-medium text-sky-900 break-all">
                    {{ attachment.filename }}
                  </div>
                  <span
                    class="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium"
                    :class="getAttachmentStatusClass(attachment.parse_status)"
                  >
                    {{ attachment.parse_status }}
                  </span>
                </div>
                <div class="mt-1 text-sm text-gray-500">
                  {{ getAttachmentMeta(attachment) }}
                </div>
              </div>
              <span class="shrink-0 text-sm font-medium text-sky-700">打开附件</span>
            </a>
          </div>
        </div>

        <!-- Content Section -->
        <div class="p-8 border-t border-gray-200">
          <h2 class="text-xl font-semibold text-sky-900 mb-4">公告正文</h2>
          <div
            v-if="post.content"
            class="prose prose-slate max-w-none text-gray-700 leading-8 whitespace-normal break-words"
            v-html="formatContent(post.content)"
          ></div>
          <div v-else class="rounded-lg border border-dashed border-gray-300 bg-gray-50 px-4 py-6 text-sm text-gray-500">
            当前这条记录还没有抓到正文内容，可以先点“查看原文”。
          </div>
        </div>

        <!-- Action Section -->
        <div class="p-8 border-t border-gray-200 bg-gray-50">
          <div class="flex flex-col sm:flex-row gap-4">
            <a
              v-if="post.canonical_url"
              :href="post.canonical_url"
              target="_blank"
              rel="noopener noreferrer"
              class="flex-1 inline-flex items-center justify-center gap-2 px-6 py-3 bg-sky-700 text-white rounded-lg hover:bg-sky-800 transition-colors duration-200 cursor-pointer"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
              查看原文
            </a>
            <button
              @click="goBack"
              class="flex-1 inline-flex items-center justify-center gap-2 px-6 py-3 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors duration-200 cursor-pointer"
            >
              返回列表
            </button>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, h } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { postsApi } from '../api/posts'

const router = useRouter()
const route = useRoute()

// State
const post = ref(null)
const loading = ref(false)
const error = ref(null)
const freshnessLoading = ref(false)
const freshnessUnavailable = ref(false)
const latestSuccessTask = ref(null)
const normalizedJobItems = ref([])
const PRIMARY_FIELD_NAMES = ['岗位名称', '性别要求', '学历要求', '专业要求', '工作地点', '招聘人数', '政治面貌', '年龄要求']

// Methods
const fetchPostDetail = async () => {
  loading.value = true
  error.value = null

  try {
    const postId = route.params.id
    const response = await postsApi.getPostById(postId)
    post.value = response.data
    normalizedJobItems.value = normalizeJobItems(response.data)
  } catch (err) {
    error.value = getErrorMessage(err)
    console.error('Error fetching post detail:', err)
  } finally {
    loading.value = false
  }
}

const fetchLatestSuccessTask = async () => {
  freshnessLoading.value = true
  freshnessUnavailable.value = false
  latestSuccessTask.value = null

  try {
    const response = await postsApi.getFreshnessSummary()
    latestSuccessTask.value = normalizeSummaryResponse({
      latest_success_run: response?.data?.latest_success_run || null,
      latest_success_at: response?.data?.latest_success_at || null,
    })
  } catch (err) {
    freshnessUnavailable.value = true
    if (err?.response?.status && err.response.status !== 404) {
      console.warn('获取公开任务新鲜度失败:', err)
    }
  }

  freshnessLoading.value = false
}

const goBack = () => {
  router.replace({
    name: 'PostList',
    query: { ...route.query }
  })
}

const formatDate = (dateString) => {
  if (!dateString) return ''
  const date = new Date(dateString)
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })
}

const formatContent = (content) => {
  if (!content) return ''
  const escapedContent = content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

  return escapedContent
    .split(/\n{2,}/)
    .map((paragraph) => `<p>${paragraph.replace(/\n/g, '<br>')}</p>`)
    .join('')
}

const getAttachmentMeta = (attachment) => {
  const parts = []
  if (attachment.file_type) {
    parts.push(attachment.file_type.toUpperCase())
  }
  if (attachment.is_downloaded) {
    parts.push('已下载')
  }
  if (attachment.parsed_fields_count > 0) {
    parts.push(`提取到 ${attachment.parsed_fields_count} 个字段`)
  }
  return parts.join(' · ')
}

const getAttachmentStatusClass = (status) => {
  if (status === '已解析') {
    return 'bg-emerald-100 text-emerald-700'
  }
  if (status === '待解析') {
    return 'bg-amber-100 text-amber-700'
  }
  if (status === '待下载') {
    return 'bg-gray-100 text-gray-700'
  }
  return 'bg-sky-100 text-sky-700'
}

const buildFieldMap = (fields = []) => {
  return fields.reduce((accumulator, field) => {
    if (!field?.field_name || accumulator[field.field_name]) {
      return accumulator
    }
    accumulator[field.field_name] = field.field_value || ''
    return accumulator
  }, {})
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

const normalizeRunsResponse = (items) => {
  if (!Array.isArray(items) || items.length === 0) return null
  const successRun = items.find((run) => run?.status === 'success')
  return normalizeTaskRun(successRun)
}

const normalizeTaskRun = (run) => {
  if (!run) return null
  const finishedAt = run.finished_at || run.finishedAt || run.last_success_at || run.lastSuccessAt
  if (!finishedAt) return null
  return {
    taskType: run.task_type || run.taskType || '',
    finishedAt
  }
}

const getTaskTypeLabel = (taskType) => {
  const labels = {
    manual_scrape: '手动抓取',
    attachment_backfill: '历史附件补处理',
    scheduled_scrape: '定时抓取',
    ai_analysis: 'AI 分析',
    job_extraction: '岗位级抽取',
    ai_job_extraction: '岗位级抽取'
  }
  return labels[taskType] || '后台任务'
}

const normalizeCounselorScope = (scope, isCounselor) => {
  const normalizedScope = (scope || '').trim()
  if (normalizedScope && normalizedScope !== 'none') {
    return normalizedScope
  }
  return isCounselor ? 'related' : ''
}

const getCounselorScope = (postData) => {
  return normalizeCounselorScope(
    postData?.counselor_scope || postData?.analysis?.counselor_scope,
    Boolean(postData?.is_counselor)
  )
}

const hasCounselorJob = (postData) => {
  if (typeof postData?.has_counselor_job === 'boolean') {
    return postData.has_counselor_job
  }
  if (typeof postData?.analysis?.has_counselor_job === 'boolean') {
    return postData.analysis.has_counselor_job
  }
  return getCounselorJobsCount(postData) > 0
}

const getCounselorJobsCount = (postData) => {
  const displayedCounselorJobsCount = normalizedJobItems.value.filter((job) => job.is_counselor_job).length
  if (displayedCounselorJobsCount > 0) {
    return displayedCounselorJobsCount
  }

  return Number(
    postData?.counselor_jobs_count ??
    postData?.jobs_count ??
    postData?.analysis?.counselor_jobs_count ??
    postData?.analysis?.jobs_count ??
    normalizedJobItems.value.filter((job) => job.is_counselor_job).length ??
    0
  )
}

const getCounselorScopeLabel = (postData) => {
  const scope = getCounselorScope(postData)
  if (scope === 'dedicated') return '只招辅导员'
  if (scope === 'contains') return '混合招聘含辅导员'
  if (scope === 'general') return '综合招聘'
  return '辅导员相关'
}

const getCounselorScopeClass = (postData) => {
  const scope = getCounselorScope(postData)
  if (scope === 'dedicated') return 'bg-emerald-100 text-emerald-800'
  if (scope === 'contains') return 'bg-teal-100 text-teal-800'
  return 'bg-green-100 text-green-800'
}

const getAnalysisProviderLabel = (provider) => {
  const labels = {
    openai: 'OpenAI 分析',
    rule: '规则分析'
  }
  return labels[provider] || '分析结果'
}

const getAnalysisProviderClass = (provider) => {
  if (provider === 'openai') {
    return 'bg-emerald-100 text-emerald-800'
  }
  if (provider === 'rule') {
    return 'bg-amber-100 text-amber-800'
  }
  return 'bg-sky-100 text-sky-800'
}

const formatJobSource = (value) => {
  const labels = {
    hybrid: '附件+正文',
    attachment: '附件表格',
    attachment_pdf: '附件 PDF',
    field: '正文字段',
    ai: 'AI 抽取',
    snapshot: '岗位快照'
  }
  return labels[value] || value || ''
}

const normalizeJobItems = (postData) => {
  const rawItems =
    postData?.job_items ||
    postData?.jobs ||
    postData?.analysis?.job_items ||
    postData?.analysis?.jobs ||
    []

  if (Array.isArray(rawItems) && rawItems.length > 0) {
    const normalizedItems = rawItems.map((item) => ({
      id: item.id || item.job_id || null,
      job_name: item.job_name || item.position_name || item.title || '',
      headcount: item.headcount || item.recruitment_count || item.count || '',
      education: item.education || item.education_requirement || '',
      major: item.major || item.major_requirement || '',
      location: item.location || item.city || item.work_location || '',
      is_counselor_job: Boolean(
        item.is_counselor_job ||
        item.is_counselor ||
        (item.job_name || '').includes('辅导员')
      ),
      source: formatJobSource(item.source || item.data_source || item.source_type || '')
    }))

    const hasSpecificStructuredJobs = normalizedItems.some((item) => item.source !== formatJobSource('field'))
    if (!hasSpecificStructuredJobs) {
      return normalizedItems
    }

    return normalizedItems.filter((item) => {
      const isNoisyFieldAggregate =
        item.source === formatJobSource('field') &&
        (
          (item.job_name || '').includes('；') ||
          (item.headcount || '').includes('；')
        )

      return !isNoisyFieldAggregate
    })
  }

  const snapshot = postData?.job_snapshot || postData?.analysis?.job_snapshot
  if (typeof snapshot === 'string' && snapshot.trim()) {
    return [{
      id: null,
      job_name: snapshot.trim(),
      headcount: '',
      education: '',
      major: '',
      location: '',
      is_counselor_job: snapshot.includes('辅导员'),
      source: formatJobSource('snapshot')
    }]
  }
  if (snapshot && typeof snapshot === 'object') {
    return [{
      id: snapshot.id || null,
      job_name: snapshot.job_name || snapshot.position_name || snapshot.title || '',
      headcount: snapshot.headcount || snapshot.recruitment_count || snapshot.count || '',
      education: snapshot.education || snapshot.education_requirement || '',
      major: snapshot.major || snapshot.major_requirement || '',
      location: snapshot.location || snapshot.city || snapshot.work_location || '',
      is_counselor_job: Boolean(
        snapshot.is_counselor_job ||
        snapshot.is_counselor ||
        (snapshot.job_name || '').includes('辅导员')
      ),
      source: formatJobSource(snapshot.source || snapshot.data_source || snapshot.source_type || 'snapshot')
    }]
  }

  return []
}

const getPreferredSourceMeta = (sourceType) => {
  if (sourceType === 'job') {
    return {
      source_label: '岗位级结果',
      source_class: 'bg-emerald-100 text-emerald-700'
    }
  }
  return {
    source_label: '原始字段',
    source_class: 'bg-gray-100 text-gray-600'
  }
}

const getPrimaryJobItem = (postData) => {
  const items = normalizeJobItems(postData)
  return items[0] || null
}

const inferGenderFromJobs = (jobItems = []) => {
  const hasMale = jobItems.some((job) => (job.job_name || '').includes('（男）') || (job.job_name || '').includes('(男)'))
  const hasFemale = jobItems.some((job) => (job.job_name || '').includes('（女）') || (job.job_name || '').includes('(女)'))

  if (hasMale && hasFemale) return ''
  if (hasMale) return '男'
  if (hasFemale) return '女'
  return ''
}

const preferredStructuredFields = computed(() => {
  if (!post.value) return []

  const fieldMap = buildFieldMap(post.value.fields || [])
  const primaryJob = getPrimaryJobItem(post.value)
  const jobGender = inferGenderFromJobs(normalizedJobItems.value)
  const items = []

  const pushField = (fieldName, fieldValue, sourceType) => {
    const normalizedValue = (fieldValue || '').trim()
    if (!normalizedValue) return
    const sourceMeta = getPreferredSourceMeta(sourceType)
    items.push({
      field_name: fieldName,
      field_value: normalizedValue,
      ...sourceMeta
    })
  }

  pushField('岗位名称', primaryJob?.job_name || fieldMap['岗位名称'], primaryJob?.job_name ? 'job' : 'field')
  pushField('性别要求', jobGender || fieldMap['性别要求'], jobGender ? 'job' : 'field')
  pushField('学历要求', primaryJob?.education || fieldMap['学历要求'], primaryJob?.education ? 'job' : 'field')
  pushField('专业要求', primaryJob?.major || fieldMap['专业要求'], primaryJob?.major ? 'job' : 'field')
  pushField('工作地点', primaryJob?.location || fieldMap['工作地点'], primaryJob?.location ? 'job' : 'field')
  pushField('招聘人数', primaryJob?.headcount || fieldMap['招聘人数'], primaryJob?.headcount ? 'job' : 'field')
  pushField('政治面貌', fieldMap['政治面貌'], 'field')
  pushField('年龄要求', fieldMap['年龄要求'], 'field')

  return items
})

const supplementalFields = computed(() => {
  const existingNames = new Set(preferredStructuredFields.value.map((field) => field.field_name))
  return (post.value?.fields || []).filter((field) => {
    const fieldName = field?.field_name || ''
    const fieldValue = (field?.field_value || '').trim()
    if (!fieldName || !fieldValue) return false
    if (existingNames.has(fieldName)) return false
    if (PRIMARY_FIELD_NAMES.includes(fieldName)) return false
    return true
  })
})

const formatPriority = (value) => {
  const labels = {
    high: '高',
    medium: '中',
    low: '低'
  }
  return labels[value] || '--'
}

const formatDateTime = (value) => {
  if (!value) return '--'
  return new Date(value).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Shanghai'
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

const getErrorMessage = (err) => {
  const status = err?.response?.status

  if (status === 404) {
    return '这条招聘信息不存在，可能已经被删除了'
  }
  if (status >= 500) {
    return '后端服务出错了，请稍后再试'
  }
  if (err?.code === 'ECONNABORTED') {
    return '请求超时了，请稍后重试'
  }
  if (err?.response) {
    return '获取招聘详情失败，请稍后重试'
  }

  return '无法连接后端服务，请确认服务已启动'
}

const getFieldIcon = (fieldName) => {
  const iconMap = {
    '性别要求': () => h('svg', { fill: 'none', stroke: 'currentColor', viewBox: '0 0 24 24' }, [
      h('path', { 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'stroke-width': '2', d: 'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z' })
    ]),
    '学历要求': () => h('svg', { fill: 'none', stroke: 'currentColor', viewBox: '0 0 24 24' }, [
      h('path', { 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'stroke-width': '2', d: 'M12 14l9-5-9-5-9 5 9 5z' }),
      h('path', { 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'stroke-width': '2', d: 'M12 14l9-5-9-5-9 5 9 5zm0 0l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14z' })
    ]),
    '专业要求': () => h('svg', { fill: 'none', stroke: 'currentColor', viewBox: '0 0 24 24' }, [
      h('path', { 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'stroke-width': '2', d: 'M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253' })
    ]),
    '工作地点': () => h('svg', { fill: 'none', stroke: 'currentColor', viewBox: '0 0 24 24' }, [
      h('path', { 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'stroke-width': '2', d: 'M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z' }),
      h('path', { 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'stroke-width': '2', d: 'M15 11a3 3 0 11-6 0 3 3 0 016 0z' })
    ]),
    '招聘人数': () => h('svg', { fill: 'none', stroke: 'currentColor', viewBox: '0 0 24 24' }, [
      h('path', { 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'stroke-width': '2', d: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z' })
    ]),
    '报名时间': () => h('svg', { fill: 'none', stroke: 'currentColor', viewBox: '0 0 24 24' }, [
      h('path', { 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'stroke-width': '2', d: 'M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z' })
    ]),
    '年龄要求': () => h('svg', { fill: 'none', stroke: 'currentColor', viewBox: '0 0 24 24' }, [
      h('path', { 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'stroke-width': '2', d: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z' })
    ]),
    '政治面貌': () => h('svg', { fill: 'none', stroke: 'currentColor', viewBox: '0 0 24 24' }, [
      h('path', { 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'stroke-width': '2', d: 'M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z' })
    ])
  }

  return iconMap[fieldName] || (() => h('svg', { fill: 'none', stroke: 'currentColor', viewBox: '0 0 24 24' }, [
    h('path', { 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'stroke-width': '2', d: 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z' })
  ]))
}

// Lifecycle
onMounted(() => {
  fetchPostDetail()
  fetchLatestSuccessTask()
})
</script>

<style scoped>
/* Custom styles if needed */
</style>
