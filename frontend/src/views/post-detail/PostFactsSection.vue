<template>
  <section v-if="facts.length > 0" class="rounded-[28px] border border-slate-200 bg-white/90 p-6 shadow-sm">
    <h2 class="text-lg font-semibold text-slate-950">关键信息</h2>
    <dl class="mt-5 grid grid-cols-1 gap-x-6 gap-y-4 md:grid-cols-2">
      <div
        v-for="item in facts"
        :key="item.label"
        class="rounded-2xl border border-slate-100 bg-slate-50/70 px-4 py-4"
      >
        <dt class="text-sm text-slate-500">{{ item.label }}</dt>
        <dd class="mt-2 text-base font-medium leading-7 text-slate-900">{{ item.value }}</dd>
      </div>
    </dl>

    <div v-if="supplementalFacts.length > 0" class="mt-6 rounded-2xl border border-slate-200 bg-slate-50/75 px-4 py-4">
      <h3 class="text-sm font-semibold text-slate-900">补充信息</h3>
      <dl class="mt-4 grid grid-cols-1 gap-x-6 gap-y-3 md:grid-cols-2">
        <div v-for="item in supplementalFacts" :key="item.label" class="border-b border-slate-200/70 pb-3 last:border-b-0">
          <dt class="text-sm text-slate-500">{{ item.label }}</dt>
          <dd class="mt-1 text-sm leading-6 text-slate-700">{{ item.value }}</dd>
        </div>
      </dl>
    </div>
  </section>
</template>

<script setup>
defineProps({
  facts: { type: Array, required: true },
  supplementalFacts: { type: Array, default: () => [] }
})
</script>
