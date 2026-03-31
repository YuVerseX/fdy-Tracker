<template>
  <dl class="app-fact-list" :class="[layoutClass, toneClass, compact ? 'app-fact-list--compact' : '']">
    <div
      v-for="item in items"
      :key="item.label"
      class="app-fact-list__item"
    >
      <dt class="app-fact-list__term">{{ item.label }}</dt>
      <dd class="app-fact-list__definition app-break">{{ item.value }}</dd>
    </div>
  </dl>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  items: { type: Array, required: true },
  columns: { type: Number, default: 2 },
  tone: { type: String, default: 'default' },
  compact: { type: Boolean, default: false }
})

const layoutClass = computed(() => (props.columns === 3 ? 'app-fact-list--three' : ''))
const toneClass = computed(() => (props.tone === 'muted' ? 'app-fact-list--muted' : ''))
</script>
