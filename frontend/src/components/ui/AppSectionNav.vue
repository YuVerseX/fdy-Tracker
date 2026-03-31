<template>
  <AppSurface v-if="items.length > 0" padding="sm" as="nav" :aria-label="ariaLabel">
    <div class="flex flex-wrap items-center gap-2">
      <span class="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
        {{ label }}
      </span>
      <a
        v-for="item in items"
        :key="item.href"
        :href="item.href"
        class="inline-flex items-center rounded-full border border-slate-200 bg-white/90 px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors duration-200 hover:border-sky-200 hover:text-sky-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300 focus-visible:ring-offset-2"
      >
        {{ item.label }}
      </a>
    </div>
  </AppSurface>
</template>

<script setup>
import AppSurface from './AppSurface.vue'

defineProps({
  items: { type: Array, default: () => [] },
  label: { type: String, default: '快速跳转' },
  ariaLabel: { type: String, default: '页面分区导航' }
})
</script>
