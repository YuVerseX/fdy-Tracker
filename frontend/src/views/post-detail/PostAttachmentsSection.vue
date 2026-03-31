<template>
  <section v-if="attachments.length > 0" class="rounded-[28px] border border-slate-200 bg-white/90 p-6 shadow-sm">
    <h2 class="text-lg font-semibold text-slate-950">附件</h2>
    <div class="mt-5 space-y-3">
      <a
        v-for="attachment in attachments"
        :key="attachment.id"
        :href="attachment.url"
        target="_blank"
        rel="noopener noreferrer"
        class="flex items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-slate-50/70 px-4 py-4 transition-colors duration-200 hover:border-sky-300 hover:bg-sky-50/70"
      >
        <div class="min-w-0">
          <div class="truncate text-sm font-medium text-slate-900">{{ attachment.title }}</div>
          <div v-if="attachment.meta" class="mt-1 text-xs text-slate-500">{{ attachment.meta }}</div>
        </div>
        <span class="shrink-0 text-sm font-medium text-sky-700">打开</span>
      </a>
    </div>
  </section>
</template>

<script setup>
defineProps({
  attachments: { type: Array, required: true }
})
</script>
