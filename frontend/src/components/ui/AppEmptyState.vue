<template>
  <section class="app-empty-state">
    <h3 class="text-base font-semibold text-slate-900">
      {{ title }}
    </h3>
    <p class="mt-2 text-sm leading-6 app-copy">
      {{ description }}
    </p>
  </section>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  description: { type: String, required: true }
})
</script>
