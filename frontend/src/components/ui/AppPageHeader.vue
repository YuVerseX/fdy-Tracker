<template>
  <section class="overflow-hidden rounded-[28px] border border-sky-200/70 bg-white/90 shadow-[0_24px_60px_-36px_rgba(30,64,175,0.45)] backdrop-blur">
    <div class="flex flex-col gap-6 px-6 py-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
      <div class="max-w-3xl">
        <p v-if="eyebrow" class="text-xs font-semibold uppercase tracking-[0.24em] text-sky-700">
          {{ eyebrow }}
        </p>
        <h1 class="mt-2 text-3xl font-semibold text-slate-950 lg:text-[2.2rem]">
          {{ title }}
        </h1>
        <p v-if="description" class="mt-3 max-w-2xl text-sm leading-7 text-slate-600">
          {{ description }}
        </p>
      </div>

      <div class="flex shrink-0 items-center gap-3">
        <slot name="actions" />
        <router-link
          v-if="actionLabel && actionTo"
          :to="actionTo"
          class="inline-flex items-center justify-center rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors duration-200 hover:border-sky-300 hover:text-sky-700"
        >
          {{ actionLabel }}
        </router-link>
      </div>
    </div>
  </section>
</template>

<script setup>
defineProps({
  eyebrow: { type: String, default: '' },
  title: { type: String, required: true },
  description: { type: String, default: '' },
  actionLabel: { type: String, default: '' },
  actionTo: { type: [Object, String], default: null }
})
</script>
