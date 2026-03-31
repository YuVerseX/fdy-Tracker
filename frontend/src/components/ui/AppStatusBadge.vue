<template>
  <span class="app-status-badge" :class="badgeClass">
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
  info: 'app-status-badge--info',
  success: 'app-status-badge--success',
  warning: 'app-status-badge--warning',
  danger: 'app-status-badge--danger',
  neutral: 'app-status-badge--neutral'
}

const badgeClass = computed(() => toneMap[props.tone] || toneMap.neutral)
</script>
