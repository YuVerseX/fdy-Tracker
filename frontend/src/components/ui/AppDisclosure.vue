<template>
  <details class="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
    <summary class="cursor-pointer list-none text-sm font-medium text-slate-700">
      {{ summary }}
    </summary>
    <div class="mt-4">
      <slot />
    </div>
  </details>
</template>

<script setup>
defineProps({
  summary: { type: String, required: true }
})
</script>
