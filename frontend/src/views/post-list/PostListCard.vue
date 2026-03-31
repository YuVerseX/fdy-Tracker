<template>
  <router-link
    :to="{ name: 'PostDetail', params: { id: card.id }, query: { ...routeQuery } }"
    class="group block rounded-[28px] border border-slate-200 bg-white/92 p-6 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-sky-200 hover:shadow-[0_18px_48px_-36px_rgba(30,64,175,0.42)] focus:outline-none focus:ring-2 focus:ring-sky-300"
    :aria-label="`查看：${card.title}`"
  >
    <div class="flex flex-col gap-4">
      <div class="flex items-start justify-between gap-4">
        <div class="flex flex-wrap gap-2">
          <AppStatusBadge
            v-for="badge in card.badges"
            :key="`${card.id}-${badge.label}`"
            :label="badge.label"
            :tone="badge.tone || 'neutral'"
          />
        </div>
        <span class="hidden items-center gap-1 text-xs font-medium text-sky-700 sm:inline-flex">
          查看详情
          <svg class="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M9 5l7 7-7 7" />
          </svg>
        </span>
      </div>

      <div>
        <h2 class="text-xl font-semibold text-slate-950 transition-colors duration-200 group-hover:text-sky-800">
          {{ card.title }}
        </h2>
        <p v-if="card.summary" class="mt-3 text-sm leading-7 text-slate-600">
          {{ card.summary }}
        </p>
      </div>

      <div
        v-if="card.jobOverview"
        class="rounded-2xl border border-sky-100 bg-sky-50/85 px-4 py-3 text-sm leading-6 text-sky-900"
      >
        <span class="font-medium text-sky-950">岗位概览</span>
        <span class="ml-2 text-sky-800">{{ card.jobOverview }}</span>
      </div>

      <dl
        v-if="card.factItems.length > 0"
        class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
      >
        <div
          v-for="fact in card.factItems"
          :key="`${card.id}-${fact.label}`"
          class="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3"
        >
          <dt class="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
            {{ fact.label }}
          </dt>
          <dd class="mt-1 text-sm font-medium text-slate-900">
            {{ fact.value }}
          </dd>
        </div>
      </dl>

      <div v-if="card.metaItems.length > 0" class="flex flex-wrap gap-2.5 text-sm text-slate-600">
        <span
          v-for="item in card.metaItems"
          :key="`${card.id}-${item.label}-${item.value}`"
          class="inline-flex items-center rounded-full border px-3 py-1.5"
          :class="item.tone === 'success' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-slate-200 bg-white text-slate-600'"
        >
          <span class="font-medium text-slate-700">{{ item.label }}</span>
          <span class="ml-1.5">{{ item.value }}</span>
        </span>
      </div>
    </div>
  </router-link>
</template>

<script setup>
import AppStatusBadge from '../../components/ui/AppStatusBadge.vue'

defineProps({
  card: { type: Object, required: true },
  routeQuery: {
    type: Object,
    default: () => ({})
  }
})
</script>
