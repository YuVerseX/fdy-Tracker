<template>
  <div class="min-h-screen">
    <main class="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
      <AppPageHeader
        eyebrow="招聘列表"
        title="辅导员招聘公告"
        description="按关键词、招聘范围和条件快速缩小结果，先看值得继续打开的公告。"
      >
        <template #actions>
          <AppStatusBadge :label="`当前范围 · ${currentScopeLabel}`" tone="info" />
        </template>
      </AppPageHeader>

      <AppNotice
        :tone="freshnessNotice.tone"
        :title="freshnessNotice.title"
        :description="freshnessNotice.description"
      />

      <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article
          v-for="card in metricCards"
          :key="card.key"
          class="rounded-[24px] border border-slate-200 bg-white/92 p-5 shadow-sm"
        >
          <p class="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">{{ card.label }}</p>
          <p class="mt-3 text-3xl font-semibold text-slate-950">{{ card.value }}</p>
          <p class="mt-2 text-sm text-slate-600">{{ card.description }}</p>
        </article>
      </section>

      <section class="rounded-[28px] border border-slate-200 bg-white/92 p-6 shadow-sm">
        <div class="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_220px_auto]">
          <div>
            <label for="post-search" class="mb-2 block text-sm font-medium text-slate-700">按关键词查找公告</label>
            <input
              id="post-search"
              v-model="searchQuery"
              type="text"
              aria-describedby="post-search-hint"
              placeholder="学校、岗位、地区或公告标题"
              class="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-900 transition-colors duration-200 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-200"
              @input="handleSearchInput"
            />
            <p id="post-search-hint" class="mt-2 text-xs text-slate-500">
              输入后会自动更新结果，也可以调整条件后再手动筛选。
            </p>
          </div>

          <div>
            <label for="scope-filter" class="mb-2 block text-sm font-medium text-slate-700">招聘范围</label>
            <select
              id="scope-filter"
              v-model="filters.counselorScope"
              class="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-900 transition-colors duration-200 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-200"
              @change="handleFilter"
            >
              <option
                v-for="option in COUNSELOR_SCOPE_OPTIONS"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </option>
            </select>
          </div>

          <div class="flex flex-col gap-3 xl:justify-end">
            <button
              type="button"
              class="inline-flex items-center justify-center rounded-full border border-slate-300 bg-white px-4 py-3 text-sm font-medium text-slate-700 transition-colors duration-200 hover:border-sky-300 hover:text-sky-700"
              :aria-expanded="showAdvancedFilters"
              @click="toggleAdvancedFilters"
            >
              {{ showAdvancedFilters ? '收起更多条件' : '更多条件' }}
            </button>
            <button
              type="button"
              class="inline-flex items-center justify-center rounded-full bg-sky-700 px-4 py-3 text-sm font-medium text-white transition-colors duration-200 hover:bg-sky-800"
              @click="handleManualSearch"
            >
              立即筛选
            </button>
          </div>
        </div>

        <div v-if="showAdvancedFilters" class="mt-5 border-t border-slate-200 pt-5">
          <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <div>
              <label for="gender-filter" class="mb-2 block text-sm font-medium text-slate-700">性别要求</label>
              <select
                id="gender-filter"
                v-model="filters.gender"
                class="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-900 transition-colors duration-200 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-200"
                @change="handleFilter"
              >
                <option value="">全部</option>
                <option value="男">男</option>
                <option value="女">女</option>
                <option value="不限">不限</option>
              </select>
            </div>

            <div>
              <label for="education-filter" class="mb-2 block text-sm font-medium text-slate-700">学历要求</label>
              <select
                id="education-filter"
                v-model="filters.education"
                class="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-900 transition-colors duration-200 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-200"
                @change="handleFilter"
              >
                <option value="">全部</option>
                <option value="博士">博士</option>
                <option value="硕士">硕士</option>
                <option value="本科">本科</option>
                <option value="专科">专科</option>
              </select>
            </div>

            <div>
              <label for="location-filter" class="mb-2 block text-sm font-medium text-slate-700">工作地点</label>
              <input
                id="location-filter"
                v-model="filters.location"
                type="text"
                placeholder="城市或地区"
                class="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-900 transition-colors duration-200 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-200"
                @input="handleLocationInput"
              />
            </div>

            <div>
              <label for="event-type-filter" class="mb-2 block text-sm font-medium text-slate-700">公告类型</label>
              <select
                id="event-type-filter"
                v-model="filters.eventType"
                class="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-900 transition-colors duration-200 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-200"
                @change="handleFilter"
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

            <label class="flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <input
                v-model="filters.hasContent"
                type="checkbox"
                class="h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-sky-500"
                @change="handleFilter"
              />
              仅看已收录正文的公告
            </label>
          </div>
        </div>

        <div
          v-if="filterChips.length > 0"
          class="mt-5 flex flex-wrap items-center gap-2 border-t border-slate-200 pt-5"
        >
          <span class="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">当前条件</span>
          <button
            v-for="chip in filterChips"
            :key="chip.key"
            type="button"
            class="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors duration-200 hover:bg-slate-200"
            :aria-label="`移除${chip.label}`"
            @click="clearFilterChip(chip.key)"
          >
            <span>{{ chip.label }}：{{ chip.value }}</span>
            <span aria-hidden="true">×</span>
          </button>
          <button
            type="button"
            class="ml-auto inline-flex items-center justify-center rounded-full border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition-colors duration-200 hover:border-slate-400 hover:text-slate-950"
            @click="clearFilters"
          >
            清空条件
          </button>
        </div>
      </section>

      <div v-if="loading" class="rounded-[28px] border border-slate-200 bg-white/92 px-6 py-14 text-center shadow-sm">
        <div class="mx-auto h-12 w-12 animate-spin rounded-full border-b-2 border-sky-700"></div>
        <p class="mt-4 text-sm text-slate-600">正在整理当前结果...</p>
      </div>

      <AppNotice
        v-else-if="error"
        tone="danger"
        title="招聘列表暂时无法显示"
        :description="error"
      >
        <template #actions>
          <button
            type="button"
            class="inline-flex items-center justify-center rounded-full bg-rose-600 px-4 py-2 text-sm font-medium text-white transition-colors duration-200 hover:bg-rose-700"
            @click="fetchPosts"
          >
            重新加载
          </button>
        </template>
      </AppNotice>

      <template v-else-if="postCards.length > 0">
        <AppNotice
          v-if="refreshing"
          tone="info"
          title="正在刷新当前结果"
          description="列表会保留你已经选好的条件。"
        />

        <section class="space-y-4">
          <router-link
            v-for="card in postCards"
            :key="card.id"
            :to="{ name: 'PostDetail', params: { id: card.id }, query: { ...route.query } }"
            class="group block rounded-[28px] border border-slate-200 bg-white/94 p-6 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-sky-200 hover:shadow-[0_24px_60px_-36px_rgba(14,116,144,0.3)] focus:outline-none focus:ring-2 focus:ring-sky-500"
            :aria-label="`查看公告：${card.title}`"
          >
            <div class="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
              <div class="min-w-0 flex-1">
                <p v-if="card.highlight" class="text-sm font-medium text-sky-700">{{ card.highlight }}</p>
                <h2 class="mt-2 text-xl font-semibold leading-8 text-slate-950 group-hover:text-sky-800">
                  {{ card.title }}
                </h2>

                <div v-if="card.facts.length > 0" class="mt-4 flex flex-wrap gap-2">
                  <span
                    v-for="fact in card.facts"
                    :key="`${card.id}-${fact.label}`"
                    class="inline-flex items-center rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700"
                  >
                    {{ fact.label }} · {{ fact.value }}
                  </span>
                </div>

                <div v-if="card.meta.length > 0" class="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm text-slate-600">
                  <span v-for="item in card.meta" :key="`${card.id}-${item.label}`">
                    {{ item.label }}：{{ item.value }}
                  </span>
                </div>
              </div>

              <div v-if="card.badges.length > 0" class="flex flex-wrap gap-2 lg:max-w-56 lg:justify-end">
                <AppStatusBadge
                  v-for="badge in card.badges"
                  :key="`${card.id}-${badge.label}`"
                  :label="badge.label"
                  :tone="badge.tone"
                />
              </div>
            </div>
          </router-link>
        </section>
      </template>

      <AppEmptyState
        v-else
        :title="emptyState.title"
        :description="emptyState.description"
      />

      <nav v-if="totalPages > 1" class="flex items-center justify-center gap-3">
        <button
          type="button"
          class="inline-flex items-center justify-center rounded-full border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition-colors duration-200 hover:border-slate-400 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-45"
          :disabled="currentPage === 1"
          @click="goToPage(currentPage - 1)"
        >
          上一页
        </button>
        <span class="text-sm text-slate-600">第 {{ currentPage }} / {{ totalPages }} 页</span>
        <button
          type="button"
          class="inline-flex items-center justify-center rounded-full border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition-colors duration-200 hover:border-slate-400 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-45"
          :disabled="currentPage === totalPages"
          @click="goToPage(currentPage + 1)"
        >
          下一页
        </button>
      </nav>
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppEmptyState from '../components/ui/AppEmptyState.vue'
import AppNotice from '../components/ui/AppNotice.vue'
import AppPageHeader from '../components/ui/AppPageHeader.vue'
import AppStatusBadge from '../components/ui/AppStatusBadge.vue'
import { getPublicFreshnessHeadline } from '../utils/publicFreshness.js'
import {
  buildActiveFilterChips,
  buildPostCardView,
  buildPostListEmptyState,
  buildPostListMetricCards,
  COUNSELOR_SCOPE_OPTIONS,
  getFilterCounselorScopeLabel
} from '../utils/postListPresentation.js'
import { getPublicTaskTypeLabel } from '../utils/taskTypeLabels.js'
import { DEFAULT_COUNSELOR_SCOPE } from '../utils/postFilters.js'
import { usePostListState } from './post-list/usePostListState.js'

const route = useRoute()
const router = useRouter()
const {
  currentPage,
  error,
  eventTypeOptions,
  fetchPosts,
  filters,
  freshnessLoading,
  freshnessUnavailable,
  getRelativeTimeLabel,
  goToPage,
  handleFilter,
  handleLocationInput,
  handleManualSearch,
  handleSearchInput,
  hasActiveFilters,
  latestSuccessTask,
  loading,
  posts,
  refreshing,
  scopeTotals,
  searchQuery,
  showAdvancedFilters,
  toggleAdvancedFilters,
  totalMatchedPosts,
  totalPages,
  clearFilters,
  formatDateTime
} = usePostListState(route, router)

const currentScopeLabel = computed(() => getFilterCounselorScopeLabel(filters.value.counselorScope))
const metricCards = computed(() => buildPostListMetricCards({
  totalMatchedPosts: totalMatchedPosts.value,
  scopeTotals: scopeTotals.value,
  currentScopeLabel: currentScopeLabel.value
}))
const postCards = computed(() => posts.value.map((post) => buildPostCardView(post)))
const filterChips = computed(() => buildActiveFilterChips({
  searchQuery: searchQuery.value,
  filters: filters.value,
  defaultCounselorScope: DEFAULT_COUNSELOR_SCOPE
}))
const hasQueryOrFilters = computed(() => Boolean(searchQuery.value.trim()) || hasActiveFilters.value)
const emptyState = computed(() => buildPostListEmptyState({ hasFilters: hasQueryOrFilters.value }))

const freshnessHeadline = computed(() => {
  if (!latestSuccessTask.value) return ''

  return getPublicFreshnessHeadline({
    ...latestSuccessTask.value,
    taskLabel: latestSuccessTask.value.taskLabel || getPublicTaskTypeLabel(latestSuccessTask.value.taskType)
  })
})

const freshnessNotice = computed(() => {
  if (freshnessLoading.value) {
    return {
      tone: 'info',
      title: '正在更新最近抓取记录',
      description: '你可以先继续筛选和浏览当前结果。'
    }
  }

  if (latestSuccessTask.value?.finishedAt) {
    return {
      tone: 'info',
      title: freshnessHeadline.value,
      description: `最近一次完成于 ${formatDateTime(latestSuccessTask.value.finishedAt)}（${getRelativeTimeLabel(latestSuccessTask.value.finishedAt)}）。`
    }
  }

  if (freshnessUnavailable.value) {
    return {
      tone: 'warning',
      title: '最近抓取记录暂时不可用',
      description: '这不会影响继续浏览当前列表。'
    }
  }

  return {
    tone: 'warning',
    title: '还没有可展示的抓取成功任务记录',
    description: '稍后再来看看，或等待下一次抓取完成。'
  }
})

const clearFilterChip = (key) => {
  if (key === 'search') {
    searchQuery.value = ''
    handleSearchInput()
    return
  }

  if (key === 'gender') {
    filters.value.gender = ''
    handleFilter()
    return
  }

  if (key === 'education') {
    filters.value.education = ''
    handleFilter()
    return
  }

  if (key === 'location') {
    filters.value.location = ''
    handleLocationInput()
    return
  }

  if (key === 'eventType') {
    filters.value.eventType = ''
    handleFilter()
    return
  }

  if (key === 'counselorScope') {
    filters.value.counselorScope = DEFAULT_COUNSELOR_SCOPE
    handleFilter()
    return
  }

  if (key === 'hasContent') {
    filters.value.hasContent = false
    handleFilter()
  }
}
</script>
