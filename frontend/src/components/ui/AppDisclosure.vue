<template>
  <details class="app-disclosure" @toggle="handleToggle">
    <summary
      class="app-disclosure__summary"
      :aria-controls="disclosureContentId"
      :aria-expanded="isOpen ? 'true' : 'false'"
    >
      <span>{{ summary }}</span>
      <span aria-hidden="true">{{ isOpen ? collapseLabel : expandLabel }}</span>
    </summary>
    <div :id="disclosureContentId" class="app-disclosure__content">
      <slot />
    </div>
  </details>
</template>

<script setup>
import { computed, getCurrentInstance, ref } from 'vue'

const props = defineProps({
  summary: { type: String, required: true },
  contentId: { type: String, default: '' },
  expandLabel: { type: String, default: '展开' },
  collapseLabel: { type: String, default: '收起' }
})

const isOpen = ref(false)
const instance = getCurrentInstance()
const disclosureContentId = computed(() => props.contentId || `app-disclosure-${instance?.uid ?? 'content'}`)

const handleToggle = (event) => {
  isOpen.value = Boolean(event.target?.open)
}
</script>
