<template>
  <div class="min-h-screen bg-sky-50">
    <!-- Header -->
    <header class="bg-white shadow-sm sticky top-0 z-10">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-sky-900">专职辅导员招聘追踪系统</h1>
          <p class="mt-1 text-sm text-gray-500">前台只看结果，运维动作请走管理台。</p>
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
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div class="mb-4 rounded-lg border border-sky-100 bg-sky-50 px-4 py-3 text-sm text-sky-800" aria-live="polite">
        <p v-if="freshnessLoading">正在获取最近抓取记录...</p>
        <template v-else-if="latestSuccessTask">
          <p>
            {{ freshnessHeadline }}，完成于
            {{ formatDateTime(latestSuccessTask.finishedAt) }}（{{ latestSuccessText }}）。
          </p>
          <p class="mt-1 text-xs text-sky-700/80">
            帮助判断系统最近是否抓取过更新，不直接代表当前公告刚发布。
          </p>
        </template>
        <p v-else-if="freshnessUnavailable">抓取记录暂时不可用，不影响你继续筛选和浏览。</p>
        <p v-else>还没有可展示的抓取成功任务记录。</p>
      </div>

      <div class="mb-3 flex flex-col gap-2 text-sm text-gray-600 lg:flex-row lg:items-center lg:justify-between">
        <p>统计口径已跟当前搜索和筛选同步，下面这组数字和当前列表是一套口径。</p>
        <span class="inline-flex items-center rounded-full bg-sky-100 px-3 py-1 text-xs font-medium text-sky-800">
          当前范围：{{ getFilterCounselorScopeLabel(filters.counselorScope) }}
        </span>
      </div>

      <div class="grid grid-cols-2 xl:grid-cols-6 gap-4 mb-6">
        <div class="rounded-lg bg-white p-5 shadow-sm">
          <div class="text-xs text-gray-500">当前范围</div>
          <div class="mt-2 text-lg font-semibold text-sky-900">{{ getFilterCounselorScopeLabel(filters.counselorScope) }}</div>
          <div class="mt-1 text-xs text-gray-500">搜索词和高级筛选都已计入</div>
        </div>
        <div class="rounded-lg bg-white p-5 shadow-sm">
          <div class="text-xs text-gray-500">当前匹配公告</div>
          <div class="mt-2 text-2xl font-semibold text-sky-900">{{ totalMatchedPosts }}</div>
        </div>
        <div class="rounded-lg bg-white p-5 shadow-sm">
          <div class="text-xs text-gray-500">所有辅导员相关</div>
          <div class="mt-2 text-2xl font-semibold text-emerald-700">{{ scopeTotals.any }}</div>
        </div>
        <div class="rounded-lg bg-white p-5 shadow-sm">
          <div class="text-xs text-gray-500">只招辅导员</div>
          <div class="mt-2 text-2xl font-semibold text-emerald-700">{{ scopeTotals.dedicated }}</div>
        </div>
        <div class="rounded-lg bg-white p-5 shadow-sm">
          <div class="text-xs text-gray-500">混合招聘含辅导员</div>
          <div class="mt-2 text-2xl font-semibold text-teal-700">{{ scopeTotals.contains }}</div>
        </div>
        <div class="rounded-lg bg-white p-5 shadow-sm">
          <div class="text-xs text-gray-500">全部公告</div>
          <div class="mt-2 text-2xl font-semibold text-gray-800">{{ scopeTotals.all }}</div>
        </div>
      </div>

      <!-- Search and Filter Section -->
      <div class="bg-white rounded-lg shadow-sm p-6 mb-6">
        <div class="flex flex-col gap-4">
          <!-- First Row: Search Input and Basic Filter -->
          <div class="flex flex-col md:flex-row gap-4">
            <!-- Search Input -->
            <div class="flex-1">
              <label for="post-search" class="mb-2 block text-sm font-medium text-gray-700">搜索招聘信息</label>
              <input
                id="post-search"
                v-model="searchQuery"
                type="text"
                aria-describedby="post-search-hint"
                placeholder="搜索招聘信息..."
                class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-600 focus:border-transparent transition-all duration-200"
                @input="handleSearchInput"
              />
              <p id="post-search-hint" class="mt-2 text-xs text-gray-500">
                输入关键词后会自动刷新列表，保留当前筛选结果。
              </p>
            </div>

            <!-- Filter: Counselor Scope -->
            <div class="min-w-52">
              <select
                v-model="filters.counselorScope"
                @change="handleFilter"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-600 focus:border-transparent text-sm text-gray-700"
              >
                <option value="any">辅导员范围：所有辅导员相关</option>
                <option value="dedicated">只招辅导员</option>
                <option value="contains">混合招聘含辅导员</option>
                <option value="all">全部公告</option>
              </select>
            </div>

            <!-- Toggle Advanced Filters -->
            <button
              type="button"
              @click="showAdvancedFilters = !showAdvancedFilters"
              class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors duration-200 cursor-pointer flex items-center gap-2"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
              </svg>
              高级筛选
            </button>

            <!-- Search Button -->
            <button
              type="button"
              @click="handleManualSearch"
              class="px-6 py-2 bg-sky-700 text-white rounded-lg hover:bg-sky-800 transition-colors duration-200 cursor-pointer"
            >
              搜索
            </button>
          </div>

          <!-- Advanced Filters Panel -->
          <div v-if="showAdvancedFilters" class="border-t border-gray-200 pt-4">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
              <!-- Gender Filter -->
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">性别要求</label>
                <select
                  v-model="filters.gender"
                  @change="handleFilter"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-600 focus:border-transparent"
                >
                  <option value="">全部</option>
                  <option value="男">男</option>
                  <option value="女">女</option>
                  <option value="不限">不限</option>
                </select>
              </div>

              <!-- Education Filter -->
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">学历要求</label>
                <select
                  v-model="filters.education"
                  @change="handleFilter"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-600 focus:border-transparent"
                >
                  <option value="">全部</option>
                  <option value="博士">博士</option>
                  <option value="硕士">硕士</option>
                  <option value="本科">本科</option>
                  <option value="专科">专科</option>
                </select>
              </div>

              <!-- Location Filter -->
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">工作地点</label>
                <input
                  v-model="filters.location"
                  type="text"
                  placeholder="输入城市或地区"
                  @input="handleLocationInput"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-600 focus:border-transparent"
                />
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">事件类型</label>
                <select
                  v-model="filters.eventType"
                  @change="handleFilter"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-600 focus:border-transparent"
                >
                  <option value="">全部</option>
                  <option
                    v-for="item in eventTypeOptions"
                    :key="item.event_type"
                    :value="item.event_type"
                  >
                    {{ item.event_type }}
                  </option>
                </select>
              </div>

              <!-- Has Content Filter -->
              <div>
                <label class="flex items-center cursor-pointer">
                  <input
                    v-model="filters.hasContent"
                    type="checkbox"
                    class="w-4 h-4 text-sky-600 border-gray-300 rounded focus:ring-sky-500 cursor-pointer"
                    @change="handleFilter"
                  />
                  <span class="ml-2 text-sm text-gray-700">仅显示有详细内容</span>
                </label>
              </div>

              <!-- Clear Filters Button -->
              <div class="flex items-end">
                <button
                  @click="clearFilters"
                  class="w-full px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors duration-200 cursor-pointer"
                >
                  清除筛选
                </button>
              </div>
            </div>

            <!-- Active Filters Display -->
            <div v-if="hasActiveFilters" class="mt-4 flex flex-wrap gap-2">
              <span class="text-sm text-gray-600">已选筛选条件:</span>
              <span v-if="filters.gender" class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-sky-100 text-sky-800">
                性别: {{ filters.gender }}
                <button @click="filters.gender = ''; handleFilter()" class="ml-2 hover:text-sky-900">×</button>
              </span>
              <span v-if="filters.education" class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-sky-100 text-sky-800">
                学历: {{ filters.education }}
                <button @click="filters.education = ''; handleFilter()" class="ml-2 hover:text-sky-900">×</button>
              </span>
              <span v-if="filters.location" class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-sky-100 text-sky-800">
                地点: {{ filters.location }}
                <button @click="filters.location = ''; handleFilter()" class="ml-2 hover:text-sky-900">×</button>
              </span>
              <span v-if="filters.eventType" class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-sky-100 text-sky-800">
                类型: {{ filters.eventType }}
                <button @click="filters.eventType = ''; handleFilter()" class="ml-2 hover:text-sky-900">×</button>
              </span>
              <span v-if="filters.counselorScope !== DEFAULT_COUNSELOR_SCOPE" class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">
                辅导员: {{ getFilterCounselorScopeLabel(filters.counselorScope) }}
                <button @click="filters.counselorScope = DEFAULT_COUNSELOR_SCOPE; handleFilter()" class="ml-2 hover:text-emerald-900">×</button>
              </span>
              <span v-if="filters.hasContent" class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-sky-100 text-sky-800">
                有详细内容
                <button @click="filters.hasContent = false; handleFilter()" class="ml-2 hover:text-sky-900">×</button>
              </span>
            </div>
          </div>
        </div>
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
          @click="fetchPosts"
          class="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors duration-200 cursor-pointer"
        >
          重试
        </button>
      </div>

      <!-- Posts List -->
      <div v-else-if="posts.length > 0" class="space-y-4">
        <div
          v-if="refreshing"
          class="rounded-lg border border-sky-100 bg-sky-50 px-4 py-2 text-sm text-sky-700"
          aria-live="polite"
        >
          正在刷新当前结果，列表和筛选条件会保留。
        </div>
        <router-link
          v-for="post in posts"
          :key="post.id"
          :to="{ name: 'PostDetail', params: { id: post.id }, query: { ...route.query } }"
          class="block bg-white rounded-lg shadow-sm p-6 hover:shadow-md transition-all duration-200 border border-transparent hover:border-sky-200 focus:outline-none focus:ring-2 focus:ring-sky-600"
          :aria-label="`查看：${post.title}`"
        >
          <div class="flex items-start justify-between">
            <div class="flex-1">
              <h2 class="text-lg font-semibold text-sky-900 mb-2">{{ post.title }}</h2>

              <div v-if="post.analysis?.summary" class="mb-3 rounded-lg bg-sky-50 px-3 py-2 text-sm text-sky-800">
                {{ post.analysis.summary }}
              </div>

              <div v-if="getJobSnapshot(post)" class="mb-3 rounded-lg border border-emerald-100 bg-emerald-50/70 px-3 py-2 text-xs text-emerald-800">
                <span class="font-medium">岗位快照：</span>{{ getJobSnapshot(post) }}
              </div>

              <!-- Key Fields Display -->
              <div v-if="hasDisplayFields(post)" class="flex flex-wrap gap-2 mb-3">
                <span v-if="getDisplayGender(post)" class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-blue-50 text-blue-700">
                  <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                  {{ getDisplayGender(post) }}
                </span>
                <span v-if="getDisplayEducation(post)" class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-purple-50 text-purple-700">
                  <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 14l9-5-9-5-9 5 9 5z" />
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 14l9-5-9-5-9 5 9 5zm0 0l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14z" />
                  </svg>
                  {{ getDisplayEducation(post) }}
                </span>
                <span v-if="getDisplayLocation(post)" class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-green-50 text-green-700">
                  <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  {{ getDisplayLocation(post) }}
                </span>
                <span v-if="getDisplayRecruitmentCount(post)" class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-orange-50 text-orange-700">
                  <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                  </svg>
                  {{ getDisplayRecruitmentCount(post) }}
                </span>
              </div>

              <div class="flex flex-wrap gap-4 text-sm text-gray-600">
                <span v-if="post.publish_date" class="flex items-center gap-1">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                  {{ formatDate(post.publish_date) }}
                </span>
                <span v-if="post.source && post.source.name" class="flex items-center gap-1">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                  </svg>
                  {{ post.source.name }}
                </span>
                <span v-if="post.has_content" class="flex items-center gap-1 text-green-600">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  有详细内容
                </span>
                <span v-if="post.analysis?.school_name" class="flex items-center gap-1">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
                  </svg>
                  {{ post.analysis.school_name }}
                </span>
              </div>
            </div>
            <div class="ml-4 flex flex-col items-end gap-2">
              <span
                v-if="getCounselorScope(post)"
                class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium"
                :class="getCounselorScopeClass(post)"
              >
                {{ getCounselorScopeLabel(post) }}
              </span>
              <span
                v-if="hasCounselorJob(post)"
                class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-cyan-100 text-cyan-800"
              >
                辅导员岗位{{ getCounselorJobCount(post) ? ` · ${getCounselorJobCount(post)}个` : '' }}
              </span>
              <span
                v-if="post.analysis?.event_type"
                class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-sky-100 text-sky-800"
              >
                {{ post.analysis.event_type }}
              </span>
            </div>
          </div>
        </router-link>
      </div>

      <!-- Empty State -->
      <div v-else class="bg-white rounded-lg shadow-sm p-12 text-center">
        <svg class="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <p class="mt-4 text-gray-600">暂无招聘信息</p>
      </div>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="mt-8 flex justify-center gap-2">
        <button
          @click="goToPage(currentPage - 1)"
          :disabled="currentPage === 1"
          class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200 cursor-pointer"
        >
          上一页
        </button>
        <span class="px-4 py-2 text-gray-700">
          第 {{ currentPage }} / {{ totalPages }} 页
        </span>
        <button
          @click="goToPage(currentPage + 1)"
          :disabled="currentPage === totalPages"
          class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200 cursor-pointer"
        >
          下一页
        </button>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { postsApi } from '../api/posts'
import { getPublicFreshnessHeadline } from '../utils/publicFreshness.js'
import {
  DEFAULT_COUNSELOR_SCOPE,
  buildPostParams as buildPostRequestParams,
  buildStatsParams as buildStatsRequestParams
} from '../utils/postFilters'

const router = useRouter()
const route = useRoute()

// State
const posts = ref([])
const loading = ref(false)
const refreshing = ref(false)
const error = ref(null)
const searchQuery = ref('')
const currentPage = ref(1)
const totalPages = ref(1)
const pageSize = 20
const showAdvancedFilters = ref(false)
const freshnessLoading = ref(false)
const freshnessUnavailable = ref(false)
const latestSuccessTask = ref(null)
const totalMatchedPosts = ref(0)
const scopeTotals = ref({
  any: 0,
  dedicated: 0,
  contains: 0,
  all: 0
})
const FETCH_DEBOUNCE_MS = 400
const FILTER_DEBOUNCE_FIELDS = new Set(['search', 'location'])
let fetchDebounceTimer = null
let statsDebounceTimer = null
let postsRequestSeq = 0
let statsRequestSeq = 0
const statsSummary = ref({
  overview: {
    total_posts: 0,
    counselor_posts: 0,
    analyzed_posts: 0,
    attachment_posts: 0
  },
  event_type_distribution: [],
  attachment_ratio: 0,
  new_in_days: 0,
  days: 7
})
const LIST_SCOPE_OPTIONS = ['any', 'dedicated', 'contains', 'all']

// Advanced Filters
const filters = ref({
  gender: '',
  education: '',
  location: '',
  eventType: '',
  counselorScope: DEFAULT_COUNSELOR_SCOPE,
  hasContent: false
})

// Computed
const hasActiveFilters = computed(() => {
  return (
    filters.value.gender ||
    filters.value.education ||
    filters.value.location ||
    filters.value.eventType ||
    filters.value.counselorScope !== DEFAULT_COUNSELOR_SCOPE ||
    filters.value.hasContent
  )
})
const latestSuccessText = computed(() => {
  if (!latestSuccessTask.value?.finishedAt) return ''
  return getRelativeTimeLabel(latestSuccessTask.value.finishedAt)
})
const freshnessHeadline = computed(() => {
  if (!latestSuccessTask.value) return ''
  return getPublicFreshnessHeadline({
    ...latestSuccessTask.value,
    taskLabel: latestSuccessTask.value.taskLabel || getTaskTypeLabel(latestSuccessTask.value.taskType)
  })
})
const eventTypeOptions = computed(() => statsSummary.value?.event_type_distribution || [])

// Methods
const getSingleQueryValue = (value) => {
  if (Array.isArray(value)) {
    return value[0] ?? ''
  }
  return value ?? ''
}

const parseQueryText = (value) => String(getSingleQueryValue(value) || '').trim()

const parseQueryBoolean = (value, fallback = false) => {
  const normalized = parseQueryText(value).toLowerCase()
  if (['1', 'true', 'yes'].includes(normalized)) return true
  if (['0', 'false', 'no'].includes(normalized)) return false
  return fallback
}

const parseQueryPage = (value) => {
  const parsed = Number.parseInt(parseQueryText(value), 10)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1
}

const parseRouteScope = (value) => {
  const normalized = parseQueryText(value)
  return LIST_SCOPE_OPTIONS.includes(normalized) ? normalized : DEFAULT_COUNSELOR_SCOPE
}

const hasAdvancedFilterSelection = (nextFilters) => {
  return Boolean(
    nextFilters.gender ||
    nextFilters.education ||
    nextFilters.location ||
    nextFilters.eventType ||
    nextFilters.hasContent
  )
}

const buildListRouteQuery = () => {
  const query = {}
  const normalizedSearch = searchQuery.value.trim()

  if (normalizedSearch) query.search = normalizedSearch
  if (filters.value.gender) query.gender = filters.value.gender
  if (filters.value.education) query.education = filters.value.education
  if (filters.value.location) query.location = filters.value.location
  if (filters.value.eventType) query.event_type = filters.value.eventType
  if (filters.value.counselorScope !== DEFAULT_COUNSELOR_SCOPE) query.scope = filters.value.counselorScope
  if (filters.value.hasContent) query.has_content = 'true'
  if (currentPage.value > 1) query.page = String(currentPage.value)

  return query
}

const syncListRouteQuery = () => {
  void router.replace({
    name: 'PostList',
    query: buildListRouteQuery()
  })
}

const hydrateStateFromRoute = () => {
  const nextFilters = {
    gender: parseQueryText(route.query.gender),
    education: parseQueryText(route.query.education),
    location: parseQueryText(route.query.location),
    eventType: parseQueryText(route.query.event_type),
    counselorScope: parseRouteScope(route.query.scope),
    hasContent: parseQueryBoolean(route.query.has_content, false)
  }

  searchQuery.value = parseQueryText(route.query.search)
  currentPage.value = parseQueryPage(route.query.page)
  filters.value = nextFilters
  showAdvancedFilters.value = hasAdvancedFilterSelection(nextFilters)
}

const buildPostParams = ({ scope = filters.value.counselorScope, skip = 0, limit = pageSize } = {}) => {
  return buildPostRequestParams({
    searchQuery: searchQuery.value,
    filters: filters.value,
    scope,
    skip,
    limit,
    defaultCounselorScope: DEFAULT_COUNSELOR_SCOPE
  })
}

const triggerFetch = ({ debounce = false, silent = false } = {}) => {
  if (fetchDebounceTimer) {
    clearTimeout(fetchDebounceTimer)
    fetchDebounceTimer = null
  }

  if (!debounce) {
    fetchPosts({ silent })
    return
  }

  fetchDebounceTimer = setTimeout(() => {
    fetchDebounceTimer = null
    fetchPosts({ silent })
  }, FETCH_DEBOUNCE_MS)
}

const triggerStatsFetch = ({ debounce = false } = {}) => {
  if (statsDebounceTimer) {
    clearTimeout(statsDebounceTimer)
    statsDebounceTimer = null
  }

  if (!debounce) {
    fetchStatsSummary()
    return
  }

  statsDebounceTimer = setTimeout(() => {
    statsDebounceTimer = null
    fetchStatsSummary()
  }, FETCH_DEBOUNCE_MS)
}

const fetchPosts = async ({ silent = false } = {}) => {
  const requestId = ++postsRequestSeq
  if (silent && posts.value.length > 0) {
    refreshing.value = true
  } else {
    loading.value = true
  }
  error.value = null

  try {
    const response = await postsApi.getPosts(
      buildPostParams({
        scope: filters.value.counselorScope,
        skip: (currentPage.value - 1) * pageSize,
        limit: pageSize
      })
    )

    if (requestId !== postsRequestSeq) return

    posts.value = response.data.items || []

    const total = response.data.total ?? 0
    totalMatchedPosts.value = total
    totalPages.value = Math.max(1, Math.ceil(total / pageSize))

    const scopeKeys = ['any', 'dedicated', 'contains', 'all']
    const totalResponses = await Promise.allSettled(
      scopeKeys.map((scope) => postsApi.getPosts(buildPostParams({ scope, limit: 1 })))
    )

    if (requestId !== postsRequestSeq) return

    const nextScopeTotals = { ...scopeTotals.value }
    let totalErrors = 0

    totalResponses.forEach((result, index) => {
      const scope = scopeKeys[index]
      if (result.status === 'fulfilled') {
        nextScopeTotals[scope] = result.value?.data?.total ?? 0
      } else {
        totalErrors += 1
      }
    })

    scopeTotals.value = nextScopeTotals

    if (totalErrors > 0) {
      console.warn(`部分 totals 获取失败：${totalErrors}/${scopeKeys.length}`)
    }
  } catch (err) {
    if (requestId !== postsRequestSeq) return
    error.value = getErrorMessage(err, '获取招聘信息失败')
    console.error('Error fetching posts:', err)
  } finally {
    if (requestId === postsRequestSeq) {
      loading.value = false
      refreshing.value = false
    }
  }
}

const handleSearch = () => {
  currentPage.value = 1
  syncListRouteQuery()
  triggerFetch({ debounce: true, silent: true })
  triggerStatsFetch({ debounce: true })
}

const handleSearchInput = () => {
  handleSearch()
}

const handleLocationInput = () => {
  currentPage.value = 1
  syncListRouteQuery()
  triggerFetch({ debounce: true, silent: true })
  triggerStatsFetch({ debounce: true })
}

const handleFilter = (changedField = '') => {
  currentPage.value = 1
  syncListRouteQuery()
  const shouldDebounce = FILTER_DEBOUNCE_FIELDS.has(changedField)
  triggerFetch({ debounce: shouldDebounce, silent: true })
  triggerStatsFetch({ debounce: shouldDebounce })
}

const handleManualSearch = () => {
  currentPage.value = 1
  syncListRouteQuery()
  triggerFetch({ debounce: false, silent: true })
  triggerStatsFetch({ debounce: false })
}

const clearFilters = () => {
  searchQuery.value = ''
  filters.value = {
    gender: '',
    education: '',
    location: '',
    eventType: '',
    counselorScope: DEFAULT_COUNSELOR_SCOPE,
    hasContent: false
  }
  handleFilter()
}

const goToPage = (page) => {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page
    syncListRouteQuery()
    fetchPosts()
    window.scrollTo({ top: 0, behavior: 'smooth' })
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

const buildStatsParams = () => {
  return buildStatsRequestParams({
    days: 7,
    searchQuery: searchQuery.value,
    filters: filters.value,
    defaultCounselorScope: DEFAULT_COUNSELOR_SCOPE
  })
}

const fetchStatsSummary = async () => {
  const requestId = ++statsRequestSeq
  try {
    const response = await postsApi.getStatsSummary(buildStatsParams())
    if (requestId !== statsRequestSeq) return
    statsSummary.value = response.data || statsSummary.value
  } catch (err) {
    if (requestId !== statsRequestSeq) return
    console.warn('获取统计摘要失败:', err)
  }
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
  const taskType = run.task_type || run.taskType || ''
  return {
    taskType,
    taskLabel: run.task_label || run.taskLabel || '',
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

const getCounselorScope = (post) => {
  return normalizeCounselorScope(
    post?.counselor_scope || post?.analysis?.counselor_scope,
    Boolean(post?.is_counselor)
  )
}

const hasCounselorJob = (post) => {
  if (typeof post?.has_counselor_job === 'boolean') {
    return post.has_counselor_job
  }
  if (typeof post?.analysis?.has_counselor_job === 'boolean') {
    return post.analysis.has_counselor_job
  }
  return Number(getCounselorJobCount(post) || 0) > 0
}

const getJobsCount = (post) => {
  return (
    post?.jobs_count ??
    post?.counselor_jobs_count ??
    post?.analysis?.jobs_count ??
    post?.analysis?.counselor_jobs_count ??
    0
  )
}

const getCounselorJobCount = (post) => (
  post?.counselor_jobs_count ??
  post?.analysis?.counselor_jobs_count ??
  0
)

const getJobSnapshot = (post) => {
  const snapshot = post?.job_snapshot || post?.analysis?.job_snapshot
  if (typeof snapshot === 'string' && snapshot.trim()) {
    return snapshot.trim()
  }
  if (snapshot && typeof snapshot === 'object') {
    const parts = [
      snapshot.job_name,
      snapshot.recruitment_count ? `人数 ${snapshot.recruitment_count}` : '',
      snapshot.education_requirement ? `学历 ${snapshot.education_requirement}` : '',
      snapshot.location ? `地点 ${snapshot.location}` : ''
    ].filter(Boolean)
    return parts.join(' · ')
  }
  const jobTitle = post?.analysis?.primary_job_title || post?.analysis?.top_job_title
  if (jobTitle) return jobTitle
  return ''
}

const getJobSnapshotPayload = (post) => {
  const snapshot = post?.job_snapshot || post?.analysis?.job_snapshot
  if (snapshot && typeof snapshot === 'object') {
    return snapshot
  }
  return null
}

const getDisplayGender = (post) => {
  const explicitGender = post?.fields?.['性别要求']
  if (explicitGender) return explicitGender

  const jobName = getJobSnapshotPayload(post)?.job_name || ''
  if (jobName.includes('（男）') || jobName.includes('(男)')) return '男'
  if (jobName.includes('（女）') || jobName.includes('(女)')) return '女'
  return ''
}

const getDisplayEducation = (post) => (
  getJobSnapshotPayload(post)?.education_requirement ||
  post?.fields?.['学历要求'] ||
  ''
)

const getDisplayLocation = (post) => (
  getJobSnapshotPayload(post)?.location ||
  post?.fields?.['工作地点'] ||
  ''
)

const getDisplayRecruitmentCount = (post) => (
  getJobSnapshotPayload(post)?.recruitment_count ||
  post?.fields?.['招聘人数'] ||
  ''
)

const hasDisplayFields = (post) => Boolean(
  getDisplayGender(post) ||
  getDisplayEducation(post) ||
  getDisplayLocation(post) ||
  getDisplayRecruitmentCount(post)
)

const getCounselorScopeLabel = (post) => {
  const scope = getCounselorScope(post)
  if (scope === 'dedicated') return '只招辅导员'
  if (scope === 'contains') return '混合招聘含辅导员'
  if (scope === 'general') return '综合招聘'
  return '辅导员相关'
}

const getCounselorScopeClass = (post) => {
  const scope = getCounselorScope(post)
  if (scope === 'dedicated') return 'bg-emerald-100 text-emerald-800'
  if (scope === 'contains') return 'bg-teal-100 text-teal-800'
  return 'bg-green-100 text-green-800'
}

const getFilterCounselorScopeLabel = (scope) => {
  if (scope === 'dedicated') return '只招辅导员'
  if (scope === 'contains') return '混合招聘含辅导员'
  if (scope === 'any') return '所有辅导员相关'
  return '全部公告'
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

const formatDate = (dateString) => {
  if (!dateString) return ''
  const date = new Date(dateString)
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  })
}

const getErrorMessage = (err, fallback) => {
  const status = err?.response?.status

  if (status === 404) {
    return '没有找到对应的招聘信息'
  }
  if (status >= 500) {
    return '后端服务出错了，请稍后再试'
  }
  if (err?.code === 'ECONNABORTED') {
    return '请求超时了，请稍后重试'
  }
  if (err?.response) {
    return fallback
  }

  return '无法连接后端服务，请确认服务已启动'
}

// Lifecycle
onMounted(() => {
  hydrateStateFromRoute()
  fetchPosts()
  fetchLatestSuccessTask()
  fetchStatsSummary()
})

onBeforeUnmount(() => {
  if (fetchDebounceTimer) {
    clearTimeout(fetchDebounceTimer)
    fetchDebounceTimer = null
  }
  if (statsDebounceTimer) {
    clearTimeout(statsDebounceTimer)
    statsDebounceTimer = null
  }
})
</script>

<style scoped>
/* Custom styles if needed */
</style>
