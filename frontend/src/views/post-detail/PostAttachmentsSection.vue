<template>
  <AppSurface v-if="attachments.length > 0" padding="lg">
    <h2 class="text-lg font-semibold text-slate-950">附件</h2>
    <div class="mt-5 space-y-3">
      <a
        v-for="attachment in attachments"
        :key="attachment.id"
        :href="attachment.url"
        target="_blank"
        rel="noopener noreferrer"
        class="flex items-center justify-between gap-4 rounded-[18px] border px-4 py-4 transition-colors duration-200 hover:border-sky-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2"
        style="border-color: var(--color-border); background: rgba(244, 247, 250, 0.78);"
      >
        <div class="min-w-0">
          <div class="app-break text-sm font-medium text-slate-900">{{ attachment.title }}</div>
          <div v-if="attachment.meta" class="mt-1 text-xs text-slate-500">{{ attachment.meta }}</div>
        </div>
        <span class="shrink-0 text-sm font-medium text-sky-700">打开</span>
      </a>
    </div>
  </AppSurface>
</template>

<script setup>
import AppSurface from '../../components/ui/AppSurface.vue'

defineProps({
  attachments: { type: Array, required: true }
})
</script>
