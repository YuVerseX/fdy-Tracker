<template>
  <button
    :type="type"
    :disabled="isDisabled"
    :aria-busy="busy ? 'true' : 'false'"
    class="inline-flex cursor-pointer items-center justify-center rounded-full font-medium transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
    :class="[sizeClass, variantClass, fullWidth ? 'w-full' : '']"
  >
    {{ currentLabel }}
  </button>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  busyLabel: { type: String, default: '' },
  busy: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  type: { type: String, default: 'button' },
  variant: { type: String, default: 'secondary' },
  size: { type: String, default: 'md' },
  fullWidth: { type: Boolean, default: false }
})

const variantMap = {
  primary: 'bg-sky-700 text-white hover:bg-sky-800 focus:ring-sky-200',
  secondary: 'border border-slate-300 bg-white text-slate-700 hover:border-sky-300 hover:text-sky-700 focus:ring-sky-200',
  neutral: 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-100 focus:ring-slate-200',
  sky: 'bg-sky-700 text-white hover:bg-sky-800 focus:ring-sky-200',
  amber: 'bg-amber-600 text-white hover:bg-amber-700 focus:ring-amber-200',
  slate: 'bg-slate-800 text-white hover:bg-slate-900 focus:ring-slate-200',
  cyan: 'bg-cyan-600 text-white hover:bg-cyan-700 focus:ring-cyan-200',
  emerald: 'bg-emerald-600 text-white hover:bg-emerald-700 focus:ring-emerald-200',
  'sky-soft': 'border border-sky-300 bg-sky-50 text-sky-700 hover:bg-sky-100 focus:ring-sky-200'
}

const sizeMap = {
  sm: 'px-4 py-2 text-sm',
  md: 'px-4 py-2.5 text-sm'
}

const currentLabel = computed(() => {
  if (props.busy && props.busyLabel) return props.busyLabel
  return props.label
})

const isDisabled = computed(() => props.disabled || props.busy)
const variantClass = computed(() => variantMap[props.variant] || variantMap.secondary)
const sizeClass = computed(() => sizeMap[props.size] || sizeMap.md)
</script>
