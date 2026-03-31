<template>
  <article class="app-stat-card" :class="wrapperClass">
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <div :class="labelClass">{{ label }}</div>
      </div>
      <div v-if="$slots.badge" class="shrink-0">
        <slot name="badge" />
      </div>
    </div>

    <div class="font-semibold" :class="[valueClass, sizeClass.value]">
      {{ value }}
    </div>

    <p v-if="description" class="text-sm leading-6 text-slate-600" :class="sizeClass.description">
      {{ description }}
    </p>

    <div v-if="metaLines.length > 0" class="space-y-1" :class="sizeClass.meta">
      <p v-for="(line, index) in metaLines" :key="`${label}-${index}`" class="text-xs leading-5 text-slate-500">
        {{ line }}
      </p>
    </div>

    <div v-if="$slots.footer" class="mt-3">
      <slot name="footer" />
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], required: true },
  description: { type: String, default: '' },
  meta: { type: [Array, String], default: () => [] },
  size: { type: String, default: 'md' },
  valueTone: { type: String, default: 'default' }
})

const sizeMap = {
  sm: {
    label: 'text-xs app-meta',
    value: 'mt-1 text-lg',
    description: 'mt-2',
    meta: 'mt-1'
  },
  md: {
    label: 'text-xs app-meta',
    value: 'mt-2 text-lg',
    description: 'mt-2',
    meta: 'mt-1'
  },
  lg: {
    label: 'text-sm font-medium text-slate-900',
    value: 'mt-3 text-2xl',
    description: 'mt-2',
    meta: 'mt-1'
  }
}

const valueToneMap = {
  default: 'text-slate-900',
  info: 'text-sky-900',
  success: 'text-emerald-900',
  warning: 'text-amber-900'
}

const sizeClass = computed(() => sizeMap[props.size] || sizeMap.md)
const wrapperClass = computed(() => (props.size === 'lg' ? 'app-stat-card--lg' : ''))
const labelClass = computed(() => sizeClass.value.label)
const valueClass = computed(() => valueToneMap[props.valueTone] || valueToneMap.default)

const metaLines = computed(() => {
  if (Array.isArray(props.meta)) return props.meta.filter(Boolean)
  return props.meta ? [props.meta] : []
})
</script>
