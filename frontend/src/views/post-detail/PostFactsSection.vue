<template>
  <AppSurface v-if="shouldShowSection" padding="lg">
    <h2 class="text-lg font-semibold text-slate-950">{{ sectionTitle }}</h2>
    <AppFactList v-if="facts.length > 0" class="mt-5" :items="facts" />

    <div
      v-if="supplementalFacts.length > 0"
      class="mt-6 pt-6"
      :class="facts.length > 0 ? 'border-t app-divider' : ''"
    >
      <h3 v-if="facts.length > 0" class="text-sm font-semibold text-slate-900">补充信息</h3>
      <AppFactList class="mt-4" :items="supplementalFacts" tone="muted" compact />
    </div>
  </AppSurface>
</template>

<script setup>
import { computed } from 'vue'

import AppFactList from '../../components/ui/AppFactList.vue'
import AppSurface from '../../components/ui/AppSurface.vue'
import { shouldShowPostFactsSection } from '../../utils/postFactsSection.js'

const props = defineProps({
  facts: { type: Array, required: true },
  supplementalFacts: { type: Array, default: () => [] }
})

const shouldShowSection = computed(() => (
  shouldShowPostFactsSection(props.facts, props.supplementalFacts)
))
const sectionTitle = computed(() => (props.facts.length > 0 ? '公告要求' : '补充信息'))
</script>
