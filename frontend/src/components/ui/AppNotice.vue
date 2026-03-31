<template>
  <section class="rounded-2xl border px-4 py-4 shadow-sm" :class="panelClass">
    <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div>
        <div v-if="title" class="text-sm font-semibold">
          {{ title }}
        </div>
        <p class="text-sm leading-6" :class="bodyClass">
          {{ description }}
        </p>
      </div>
      <div v-if="$slots.actions" class="shrink-0">
        <slot name="actions" />
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  tone: { type: String, default: 'info' },
  title: { type: String, default: '' },
  description: { type: String, required: true }
})

const toneMap = {
  info: {
    panel: 'border-sky-200 bg-sky-50/90 text-sky-900',
    body: 'text-sky-800'
  },
  success: {
    panel: 'border-emerald-200 bg-emerald-50/90 text-emerald-900',
    body: 'text-emerald-800'
  },
  warning: {
    panel: 'border-amber-200 bg-amber-50/95 text-amber-900',
    body: 'text-amber-800'
  },
  danger: {
    panel: 'border-rose-200 bg-rose-50/95 text-rose-900',
    body: 'text-rose-800'
  }
}

const panelClass = computed(() => (toneMap[props.tone] || toneMap.info).panel)
const bodyClass = computed(() => (toneMap[props.tone] || toneMap.info).body)
</script>
