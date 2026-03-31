<template>
  <AppDisclosure v-if="items.length > 0" summary="查看信息说明">
    <dl class="space-y-4">
      <div v-for="item in items" :key="item.key">
        <dt class="text-sm font-medium text-slate-900">{{ item.label }}</dt>
        <dd class="app-break mt-1 text-sm leading-6 app-copy">{{ item.value }}</dd>
      </div>
    </dl>
  </AppDisclosure>
</template>

<script setup>
import AppDisclosure from '../../components/ui/AppDisclosure.vue'

defineProps({
  items: { type: Array, required: true }
})
</script>
