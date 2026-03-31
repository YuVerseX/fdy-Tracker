<template>
  <span class="inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs" :class="toneClass">
    <span>{{ label }}</span>
    <span v-if="hasValue" class="font-semibold" :class="valueClass">{{ value }}</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], default: '' },
  tone: { type: String, default: 'default' }
})

const toneMap = {
  default: {
    pill: 'bg-white/90 text-slate-700',
    value: 'text-slate-900'
  },
  muted: {
    pill: 'bg-slate-100 text-slate-600',
    value: 'text-slate-900'
  }
}

const hasValue = computed(() => String(props.value ?? '').trim() !== '')
const toneClass = computed(() => (toneMap[props.tone] || toneMap.default).pill)
const valueClass = computed(() => (toneMap[props.tone] || toneMap.default).value)
</script>
