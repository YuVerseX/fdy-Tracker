<template>
  <div class="space-y-6">
    <section class="rounded-lg border p-6" :class="health.panelClass">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div class="flex flex-wrap items-center gap-3">
            <h2 class="text-lg font-semibold">系统健康总览</h2>
            <span class="inline-flex items-center rounded-full px-3 py-1 text-xs font-medium" :class="health.badgeClass">
              {{ health.label }}
            </span>
          </div>
          <p class="mt-2 text-sm" :class="health.textClass">{{ health.summary }}</p>
        </div>
        <button
          type="button"
          :disabled="refreshing"
          class="inline-flex items-center justify-center rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors duration-200 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
          @click="refreshOverview"
        >
          {{ refreshing ? '刷新中...' : '刷新总览' }}
        </button>
      </div>

      <div class="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article v-for="card in cards" :key="card.id" class="rounded-lg bg-white/80 px-4 py-4 shadow-sm ring-1 ring-black/5">
          <div class="text-xs text-gray-500">{{ card.label }}</div>
          <div class="mt-2 text-lg font-semibold text-sky-900">{{ card.value }}</div>
          <p v-for="line in card.meta.filter(Boolean)" :key="`${card.id}-${line}`" class="mt-1 text-xs text-gray-500">
            {{ line }}
          </p>
        </article>
      </div>

      <div v-if="health.alerts.length > 0" class="mt-4 rounded-lg border border-amber-200 bg-white/80 px-4 py-4 text-sm text-amber-900">
        <div class="font-medium">当前需要注意</div>
        <div class="mt-3 space-y-2">
          <div v-for="item in health.alerts" :key="item" class="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
            {{ item }}
          </div>
        </div>
      </div>
    </section>

    <section class="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div class="flex flex-wrap items-center gap-3">
            <h2 class="text-lg font-semibold text-sky-900">结构化字段</h2>
            <span class="inline-flex items-center rounded-full bg-fuchsia-100 px-3 py-1 text-xs font-medium text-fuchsia-700">
              {{ runtimeCopy.badge }}
            </span>
          </div>
          <p class="mt-1 text-sm text-gray-500">{{ runtimeCopy.description }}</p>
          <p class="mt-2 text-xs text-gray-500">{{ runtimeCopy.emphasis }}</p>
        </div>
        <button
          type="button"
          class="inline-flex items-center justify-center rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-700 transition-colors duration-200 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
          @click="refreshStructuredSummary"
        >
          {{ structureRefreshLabel }}
        </button>
      </div>

      <div class="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div v-for="card in structuredFieldCards" :key="card.label" class="rounded-lg border border-gray-200 bg-white px-4 py-3">
          <div class="text-xs text-gray-500">{{ card.label }}</div>
          <div class="mt-1 text-lg font-semibold text-gray-900">{{ card.value }}</div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
defineProps({
  health: { type: Object, required: true },
  refreshing: { type: Boolean, required: true },
  cards: { type: Array, required: true },
  runtimeCopy: { type: Object, required: true },
  structuredFieldCards: { type: Array, required: true },
  structureRefreshLabel: { type: String, required: true },
  refreshOverview: { type: Function, required: true },
  refreshStructuredSummary: { type: Function, required: true }
})
</script>
