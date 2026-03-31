<template>
  <span class="inline-flex items-center rounded-full px-3 py-1 text-xs font-medium" :class="badgeClass">
    {{ label }}
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  tone: { type: String, default: 'neutral' }
})

const toneMap = {
  info: 'bg-sky-100 text-sky-700',
  success: 'bg-emerald-100 text-emerald-700',
  warning: 'bg-amber-100 text-amber-800',
  danger: 'bg-rose-100 text-rose-700',
  neutral: 'bg-slate-100 text-slate-700'
}

const badgeClass = computed(() => toneMap[props.tone] || toneMap.neutral)
</script>
