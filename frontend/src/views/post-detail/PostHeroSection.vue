<template>
  <section class="overflow-hidden rounded-[32px] border border-slate-200 bg-white/92 shadow-[0_28px_70px_-40px_rgba(15,23,42,0.35)] backdrop-blur">
    <div class="border-b border-slate-100 px-6 py-4 lg:px-8">
      <button
        type="button"
        class="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors duration-200 hover:border-sky-300 hover:text-sky-700"
        @click="$emit('back')"
      >
        返回列表
      </button>
    </div>

    <div class="flex flex-col gap-6 px-6 py-7 lg:px-8">
      <div class="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div class="max-w-4xl">
          <p class="text-xs font-semibold uppercase tracking-[0.24em] text-sky-700">
            招聘详情
          </p>
          <h1 class="mt-3 text-3xl font-semibold leading-tight text-slate-950 lg:text-[2.4rem]">
            {{ title }}
          </h1>
          <div class="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-slate-600">
            <span v-if="publishDateLabel">{{ publishDateLabel }}</span>
            <span v-if="sourceName">{{ sourceName }}</span>
          </div>
        </div>

        <a
          v-if="originalUrl"
          :href="originalUrl"
          target="_blank"
          rel="noopener noreferrer"
          class="inline-flex shrink-0 items-center justify-center rounded-full bg-sky-700 px-5 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-sky-800"
        >
          查看原文
        </a>
      </div>

      <div v-if="tags.length > 0" class="flex flex-wrap gap-2">
        <span
          v-for="tag in tags"
          :key="tag.label"
          class="inline-flex items-center rounded-full px-3 py-1 text-xs font-medium"
          :class="getTagClass(tag.tone)"
        >
          {{ tag.label }}
        </span>
      </div>

      <div
        v-if="freshnessNote"
        class="rounded-2xl border border-sky-100 bg-sky-50/90 px-4 py-3 text-sm leading-6 text-sky-800"
      >
        {{ freshnessNote }}
      </div>
    </div>
  </section>
</template>

<script setup>
defineEmits(['back'])

defineProps({
  title: { type: String, required: true },
  publishDateLabel: { type: String, default: '' },
  sourceName: { type: String, default: '' },
  tags: { type: Array, default: () => [] },
  freshnessNote: { type: String, default: '' },
  originalUrl: { type: String, default: '' }
})

const getTagClass = (tone) => {
  if (tone === 'success') return 'bg-emerald-100 text-emerald-800'
  if (tone === 'info') return 'bg-sky-100 text-sky-800'
  if (tone === 'warning') return 'bg-amber-100 text-amber-800'
  return 'bg-slate-100 text-slate-700'
}
</script>
