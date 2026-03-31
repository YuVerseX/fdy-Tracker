<template>
  <AppSurface tone="hero" padding="lg" class="overflow-hidden">
    <div class="border-b app-divider pb-5">
      <button
        type="button"
        class="app-button app-button--sm app-button--secondary gap-2"
        @click="$emit('back')"
      >
        返回列表
      </button>
    </div>

    <div class="flex flex-col gap-6 pt-6">
      <div class="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div class="max-w-4xl">
          <p class="app-eyebrow">
            招聘详情
          </p>
          <h1 class="mt-3 app-title-hero max-w-4xl !text-[clamp(1.9rem,3vw,2.8rem)]">
            {{ title }}
          </h1>
          <div class="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm app-copy">
            <span v-if="publishDateLabel">{{ publishDateLabel }}</span>
            <span v-if="sourceName">{{ sourceName }}</span>
          </div>
        </div>

        <a
          v-if="originalUrl"
          :href="originalUrl"
          target="_blank"
          rel="noopener noreferrer"
          class="app-button app-button--md app-button--primary shrink-0"
        >
          查看原文
        </a>
      </div>

      <div v-if="tags.length > 0" class="flex flex-wrap gap-2">
        <AppStatusBadge
          v-for="tag in tags"
          :key="tag.label"
          :label="tag.label"
          :tone="tag.tone === 'info' ? 'info' : tag.tone === 'success' ? 'success' : tag.tone === 'warning' ? 'warning' : 'neutral'"
        />
      </div>

      <div class="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.95fr)]">
        <div class="rounded-[18px] border border-slate-200/70 bg-white/78 px-5 py-5">
          <p class="text-base font-medium leading-8 text-slate-800">
            {{ summary }}
          </p>
        </div>

        <AppFactList
          v-if="headlineFacts.length > 0"
          :items="headlineFacts"
          :columns="2"
          compact
          tone="muted"
        />
      </div>

      <div v-if="freshnessNote" class="max-w-3xl">
        <AppNotice
          title="最近抓取"
          :description="freshnessNote"
        />
      </div>
    </div>
  </AppSurface>
</template>

<script setup>
import AppFactList from '../../components/ui/AppFactList.vue'
import AppNotice from '../../components/ui/AppNotice.vue'
import AppStatusBadge from '../../components/ui/AppStatusBadge.vue'
import AppSurface from '../../components/ui/AppSurface.vue'

defineEmits(['back'])

defineProps({
  title: { type: String, required: true },
  publishDateLabel: { type: String, default: '' },
  sourceName: { type: String, default: '' },
  tags: { type: Array, default: () => [] },
  summary: { type: String, default: '' },
  headlineFacts: { type: Array, default: () => [] },
  freshnessNote: { type: String, default: '' },
  originalUrl: { type: String, default: '' }
})

</script>
