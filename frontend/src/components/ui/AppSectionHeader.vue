<template>
  <div class="flex flex-col gap-2.5 md:flex-row md:items-start md:justify-between md:gap-4">
    <div class="max-w-3xl md:flex-1">
      <div class="flex flex-wrap items-center gap-2.5">
        <h2 class="app-title-section">
          {{ title }}
        </h2>
        <slot name="badge" />
      </div>
      <p v-if="description" class="mt-2 text-sm leading-6 app-copy">
        {{ description }}
      </p>
    </div>
    <div v-if="aside" class="max-w-md text-xs leading-5 app-meta md:max-w-xs md:shrink-0 md:text-right lg:max-w-sm">
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
