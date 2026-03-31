<template>
  <TabsRoot :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)">
    <TabsList
      class="flex flex-wrap gap-2 rounded-[22px] border border-slate-200 bg-slate-100/90 p-1.5"
      :aria-label="ariaLabel"
    >
      <TabsTrigger
        v-for="item in items"
        :key="item.value"
        :value="item.value"
        class="rounded-full px-4 py-2 text-sm font-medium text-slate-600 transition-colors duration-200 hover:text-slate-900 data-[state=active]:bg-sky-700 data-[state=active]:text-white"
      >
        {{ item.label }}
      </TabsTrigger>
    </TabsList>
  </TabsRoot>
</template>

<script setup>
import { TabsList, TabsRoot, TabsTrigger } from 'reka-ui'

defineProps({
  modelValue: { type: String, required: true },
  items: { type: Array, required: true },
  ariaLabel: { type: String, default: '切换分区' }
})

const emit = defineEmits(['update:modelValue'])
</script>
