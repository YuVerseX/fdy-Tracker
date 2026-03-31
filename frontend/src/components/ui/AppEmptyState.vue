<template>
  <section class="rounded-2xl border border-dashed border-slate-300 bg-slate-50/90 px-5 py-8 text-center">
    <h3 class="text-base font-semibold text-slate-900">
      {{ title }}
    </h3>
    <p class="mt-2 text-sm leading-6 text-slate-600">
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
