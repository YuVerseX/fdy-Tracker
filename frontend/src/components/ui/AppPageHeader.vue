<template>
  <AppSurface tone="hero" padding="lg" class="overflow-hidden">
    <div class="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
      <div class="max-w-3xl">
        <p v-if="eyebrow" class="app-eyebrow">
          {{ eyebrow }}
        </p>
        <h1 class="mt-3 app-title-hero">
          {{ title }}
        </h1>
        <p v-if="description" class="mt-3 max-w-2xl text-sm app-copy">
          {{ description }}
        </p>
      </div>

      <div class="flex shrink-0 items-center gap-3">
        <slot name="actions" />
        <router-link
          v-if="actionLabel && actionTo"
          :to="actionTo"
          class="app-button app-button--sm app-button--secondary"
        >
          {{ actionLabel }}
        </router-link>
      </div>
    </div>
  </AppSurface>
</template>

<script setup>
import AppSurface from './AppSurface.vue'

defineProps({
  eyebrow: { type: String, default: '' },
  title: { type: String, required: true },
  description: { type: String, default: '' },
  actionLabel: { type: String, default: '' },
  actionTo: { type: [Object, String], default: null }
})
</script>
