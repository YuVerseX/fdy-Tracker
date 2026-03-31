<template>
  <div class="min-h-screen">
    <main class="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
      <div v-if="loading" class="rounded-[28px] border border-slate-200 bg-white/90 px-6 py-14 text-center shadow-sm">
        <div class="mx-auto h-12 w-12 animate-spin rounded-full border-b-2 border-sky-700"></div>
        <p class="mt-4 text-sm text-slate-600">正在加载招聘详情...</p>
      </div>

      <div v-else-if="error" class="rounded-[28px] border border-rose-200 bg-rose-50/90 px-6 py-10 text-center shadow-sm">
        <p class="text-sm text-rose-700">{{ error }}</p>
        <button
          type="button"
          class="mt-4 inline-flex items-center justify-center rounded-full bg-rose-600 px-5 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-rose-700"
          @click="fetchPostDetail"
        >
          重新加载
        </button>
      </div>

      <template v-else-if="post">
        <PostHeroSection
          :title="post.title"
          :publish-date-label="publishDateLabel"
          :source-name="sourceLabel"
          :tags="heroTags"
          :freshness-note="freshnessNote"
          :original-url="post.canonical_url || ''"
          @back="goBack"
        />

        <PostFactsSection :facts="facts" :supplemental-facts="supplementalFacts" />
        <PostJobsSection :job-view="jobView" />
        <PostAttachmentsSection :attachments="attachmentCards" />

        <section class="rounded-[28px] border border-slate-200 bg-white/90 p-6 shadow-sm">
          <h2 class="text-lg font-semibold text-slate-950">公告正文</h2>
          <div
            v-if="post.content"
            class="prose prose-slate mt-5 max-w-none text-slate-700"
            v-html="formattedContent"
          ></div>
          <AppEmptyState
            v-else
            title="正文暂未收录"
            description="当前记录还没有抓到正文内容，可以先查看原文。"
          />
        </section>

        <PostInfoDisclosure :items="infoDisclosureItems" />
      </template>
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppEmptyState from '../components/ui/AppEmptyState.vue'
import { getPublicFreshnessHeadline } from '../utils/publicFreshness.js'
import { getPublicTaskTypeLabel } from '../utils/taskTypeLabels.js'
import {
  buildAttachmentCards,
  buildHeroTags,
  buildInfoDisclosureItems,
  buildJobPresentation,
  buildPostFacts,
  buildResolvedPostFields,
  buildSourceNotes,
  buildSupplementalFields,
  normalizeJobItems
} from '../utils/postDetailPresentation.js'
import PostAttachmentsSection from './post-detail/PostAttachmentsSection.vue'
import PostFactsSection from './post-detail/PostFactsSection.vue'
import PostHeroSection from './post-detail/PostHeroSection.vue'
import PostInfoDisclosure from './post-detail/PostInfoDisclosure.vue'
import PostJobsSection from './post-detail/PostJobsSection.vue'
import { usePostDetailState } from './post-detail/usePostDetailState.js'

const router = useRouter()
const route = useRoute()
const {
  post,
  loading,
  error,
  latestSuccessTask,
  freshnessLoading,
  freshnessUnavailable,
  fetchPostDetail
} = usePostDetailState(route)

const jobItems = computed(() => normalizeJobItems(post.value || {}))
const resolvedFields = computed(() => buildResolvedPostFields(post.value || {}, jobItems.value))
const facts = computed(() => buildPostFacts({ fields: resolvedFields.value }))
const supplementalFacts = computed(() => buildSupplementalFields(post.value || {}, facts.value))
const jobView = computed(() => buildJobPresentation(jobItems.value))
const attachmentCards = computed(() => buildAttachmentCards(post.value?.attachments || []))
const heroTags = computed(() => buildHeroTags(post.value || {}, jobItems.value))
const publishDateLabel = computed(() => post.value?.publish_date ? `发布日期：${formatDate(post.value.publish_date)}` : '')
const sourceLabel = computed(() => post.value?.source?.name ? `来源：${post.value.source.name}` : '')
const formattedContent = computed(() => formatContent(post.value?.content || ''))

const freshnessHeadline = computed(() => {
  if (!latestSuccessTask.value) return ''
  return getPublicFreshnessHeadline({
    ...latestSuccessTask.value,
    taskLabel: latestSuccessTask.value.taskLabel || getPublicTaskTypeLabel(latestSuccessTask.value.taskType)
  })
})

const freshnessHint = computed(() => {
  if (latestSuccessTask.value?.finishedAt) {
    return `${freshnessHeadline.value}，完成于 ${formatDateTime(latestSuccessTask.value.finishedAt)}（${getRelativeTimeLabel(latestSuccessTask.value.finishedAt)}）。`
  }
  if (freshnessUnavailable.value) {
    return '最近抓取记录暂时不可用。'
  }
  return ''
})

const freshnessNote = computed(() => {
  if (freshnessLoading.value) {
    return '正在更新最近抓取记录。'
  }
  if (latestSuccessTask.value?.finishedAt) {
    return freshnessHint.value
  }
  if (freshnessUnavailable.value) {
    return '最近抓取记录暂时不可用，不影响继续阅读当前公告。'
  }
  return '还没有可展示的抓取成功任务记录。'
})

const infoDisclosureItems = computed(() => buildInfoDisclosureItems({
  freshnessHint: freshnessHint.value,
  sourceNotes: buildSourceNotes(post.value || {}, jobItems.value),
  metadata: [
    post.value?.canonical_url ? { key: 'original_url', label: '原文链接', value: post.value.canonical_url } : null,
    attachmentCards.value.length > 0 ? { key: 'attachment_count', label: '附件数量', value: `共 ${attachmentCards.value.length} 份附件` } : null
  ]
}))

const goBack = () => {
  if (window.history.length > 1) {
    router.back()
    return
  }

  router.push({
    name: 'PostList',
    query: { ...route.query }
  })
}

const formatDate = (dateString) => {
  if (!dateString) return ''
  return new Date(dateString).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })
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
</script>
