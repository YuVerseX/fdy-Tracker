<template>
  <section
    class="app-notice"
    :class="panelClass"
    :role="liveRegionRole"
    :aria-live="liveRegionMode"
    aria-atomic="true"
  >
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
  announce: { type: Boolean, default: false },
  description: { type: String, required: true }
})

const toneMap = {
  info: {
    panel: 'app-notice--info',
    body: ''
  },
  success: {
    panel: 'app-notice--success',
    body: ''
  },
  warning: {
    panel: 'app-notice--warning',
    body: ''
  },
  danger: {
    panel: 'app-notice--danger',
    body: ''
  }
}

const panelClass = computed(() => (toneMap[props.tone] || toneMap.info).panel)
const bodyClass = computed(() => (toneMap[props.tone] || toneMap.info).body)
const liveRegionRole = computed(() => (
  props.announce ? (props.tone === 'danger' ? 'alert' : 'status') : undefined
))
const liveRegionMode = computed(() => (
  props.announce ? (props.tone === 'danger' ? 'assertive' : 'polite') : undefined
))
</script>
