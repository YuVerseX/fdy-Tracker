<template>
  <span class="app-pill" :class="toneClass">
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
    pill: 'app-pill--default',
    value: 'text-slate-900'
  },
  muted: {
    pill: 'app-pill--muted',
    value: 'text-slate-900'
  },
  info: {
    pill: 'app-pill--info',
    value: 'text-sky-900'
  },
  success: {
    pill: 'app-pill--success',
    value: 'text-emerald-900'
  },
  warning: {
    pill: 'app-pill--warning',
    value: 'text-amber-900'
  },
  danger: {
    pill: 'app-pill--danger',
    value: 'text-rose-900'
  }
}

const hasValue = computed(() => String(props.value ?? '').trim() !== '')
const toneClass = computed(() => (toneMap[props.tone] || toneMap.default).pill)
const valueClass = computed(() => (toneMap[props.tone] || toneMap.default).value)
</script>
