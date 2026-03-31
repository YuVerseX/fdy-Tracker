<template>
  <component
    :is="as"
    class="app-surface"
    :class="[toneClass, paddingClass]"
  >
    <slot />
  </component>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  as: { type: String, default: 'section' },
  tone: { type: String, default: 'default' },
  padding: { type: String, default: 'lg' }
})

const toneMap = {
  default: '',
  hero: 'app-surface--hero',
  muted: 'app-surface--muted',
  info: 'app-surface--info',
  success: 'app-surface--success',
  warning: 'app-surface--warning',
  danger: 'app-surface--danger'
}

const paddingMap = {
  none: '',
  sm: 'app-surface--padding-sm',
  md: 'app-surface--padding-md',
  lg: 'app-surface--padding-lg'
}

const toneClass = computed(() => toneMap[props.tone] || '')
const paddingClass = computed(() => paddingMap[props.padding] || paddingMap.lg)
</script>
