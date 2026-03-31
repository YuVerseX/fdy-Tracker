<template>
  <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
    <div class="max-w-3xl">
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="text-lg font-semibold text-slate-950">
          {{ title }}
        </h2>
        <slot name="badge" />
      </div>
      <p v-if="description" class="mt-1 text-sm leading-6 text-slate-600">
        {{ description }}
      </p>
    </div>
    <div v-if="aside" class="text-xs leading-6 text-slate-500">
      {{ aside }}
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  aside: { type: String, default: '' }
})
</script>
