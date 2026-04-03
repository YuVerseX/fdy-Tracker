<template>
  <ol class="grid gap-2 sm:grid-cols-2 xl:grid-cols-4" aria-label="任务阶段">
    <li
      v-for="item in items"
      :key="item.key"
      :aria-current="['current', 'failed', 'cancelled'].includes(item.state) ? 'step' : undefined"
      class="rounded-2xl border px-3 py-3 transition-colors duration-200"
      :class="getItemClass(item.state)"
    >
      <div class="flex items-start gap-3">
        <span
          class="mt-1 inline-flex h-2.5 w-2.5 shrink-0 rounded-full"
          :class="getDotClass(item.state)"
          aria-hidden="true"
        />
        <div class="min-w-0">
          <p class="text-xs font-medium uppercase tracking-[0.18em]" :class="getEyebrowClass(item.state)">
            {{ item.eyebrow || item.key }}
          </p>
          <p class="mt-1 text-sm font-semibold text-slate-900">{{ item.label }}</p>
          <p v-if="item.description" class="mt-1 text-xs leading-5 text-slate-500">
            {{ item.description }}
          </p>
        </div>
      </div>
    </li>
  </ol>
</template>

<script setup>
const props = defineProps({
  items: {
    type: Array,
    default: () => []
  }
})

const getItemClass = (state) => {
  if (state === 'done') return 'border-emerald-200 bg-emerald-50/80'
  if (state === 'failed') return 'border-rose-200 bg-rose-50/85'
  if (state === 'cancelled') return 'border-amber-200 bg-amber-50/85'
  if (state === 'current') return 'border-sky-200 bg-sky-50/85 shadow-sm'
  return 'border-slate-200 bg-slate-50/85'
}

const getDotClass = (state) => {
  if (state === 'done') return 'bg-emerald-500'
  if (state === 'failed') return 'bg-rose-500'
  if (state === 'cancelled') return 'bg-amber-500'
  if (state === 'current') return 'bg-sky-500'
  return 'bg-slate-300'
}

const getEyebrowClass = (state) => {
  if (state === 'done') return 'text-emerald-700'
  if (state === 'failed') return 'text-rose-700'
  if (state === 'cancelled') return 'text-amber-700'
  if (state === 'current') return 'text-sky-700'
  return 'text-slate-400'
}
</script>
