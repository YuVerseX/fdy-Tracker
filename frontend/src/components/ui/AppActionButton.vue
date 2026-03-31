<template>
  <button
    :type="type"
    :disabled="isDisabled"
    :aria-busy="busy ? 'true' : 'false'"
    class="app-button"
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
  primary: 'app-button--primary',
  secondary: 'app-button--secondary',
  neutral: 'app-button--neutral',
  sky: 'app-button--primary',
  amber: 'app-button--warning',
  slate: 'app-button--secondary',
  cyan: 'app-button--info-soft',
  emerald: 'app-button--success',
  'sky-soft': 'app-button--info-soft'
}

const sizeMap = {
  sm: 'app-button--sm',
  md: 'app-button--md'
}

const currentLabel = computed(() => {
  if (props.busy && props.busyLabel) return props.busyLabel
  return props.label
})

const isDisabled = computed(() => props.disabled || props.busy)
const variantClass = computed(() => variantMap[props.variant] || variantMap.secondary)
const sizeClass = computed(() => sizeMap[props.size] || sizeMap.md)
</script>
