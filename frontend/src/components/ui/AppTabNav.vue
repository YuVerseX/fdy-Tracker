<template>
  <TabsRoot :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)">
    <TabsList
      class="flex gap-1.5 overflow-x-auto rounded-full border border-[rgba(148,163,184,0.26)] bg-[rgba(239,243,247,0.82)] p-1.5 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden sm:gap-2 sm:flex-wrap sm:overflow-visible"
      :aria-label="ariaLabel"
    >
      <TabsTrigger
        v-for="item in items"
        :key="item.value"
        :value="item.value"
        class="shrink-0 whitespace-nowrap rounded-full px-3 py-2 text-[13px] font-medium text-slate-600 transition-colors duration-200 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 sm:px-4 sm:text-sm data-[state=active]:bg-[var(--color-accent)] data-[state=active]:text-white"
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
