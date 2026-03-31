<template>
  <article class="rounded-[24px] border p-5 shadow-sm" :class="toneClass.panel">
    <div class="flex flex-col gap-3">
      <div class="flex flex-wrap items-center gap-3">
        <span v-if="card.badge" class="inline-flex items-center rounded-full px-3 py-1 text-xs font-medium" :class="toneClass.badge">
          {{ card.badge }}
        </span>
        <h3 class="text-base font-semibold text-slate-950">{{ card.title }}</h3>
      </div>

      <p class="text-sm leading-6 text-slate-600">{{ card.description }}</p>

      <div v-if="card.summary" class="rounded-2xl border bg-white/90 px-4 py-3 text-sm font-medium text-slate-900" :class="toneClass.summary">
        {{ card.summary }}
      </div>

      <div v-if="card.chips?.length" class="flex flex-wrap gap-2">
        <AppMetricPill
          v-for="chip in card.chips"
          :key="chip"
          :label="chip"
        />
      </div>

      <AppNotice
        v-if="card.notice"
        :tone="card.notice.tone || 'info'"
        :description="card.notice.description"
      />

      <div class="flex flex-wrap gap-3">
        <AppActionButton
          :label="card.primaryAction?.label || ''"
          :busy-label="card.primaryAction?.busyLabel || ''"
          :busy="Boolean(card.primaryAction?.busy)"
          :disabled="card.primaryAction?.disabled"
          :variant="toneClass.primaryButtonVariant"
          @click="card.primaryAction?.onClick?.()"
        />
        <AppActionButton
          v-if="card.secondaryAction"
          :label="card.secondaryAction.label"
          :busy-label="card.secondaryAction.busyLabel"
          :busy="Boolean(card.secondaryAction.busy)"
          :disabled="card.secondaryAction.disabled"
          variant="neutral"
          @click="card.secondaryAction.onClick?.()"
        />
      </div>

      <p v-if="card.footer" class="text-xs text-slate-500">{{ card.footer }}</p>

      <AppDisclosure v-if="card.disclosure?.fields?.length" :summary="card.disclosure.summary">
        <p v-if="card.disclosure.hint" class="mb-4 text-xs leading-6 text-slate-500">{{ card.disclosure.hint }}</p>
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div v-for="field in card.disclosure.fields" :key="field.id" :class="field.type === 'checkbox' ? 'sm:col-span-2' : ''">
            <label v-if="field.type !== 'checkbox'" class="mb-2 block text-sm font-medium text-slate-700">
              {{ field.label }}
            </label>

            <select
              v-if="field.type === 'select'"
              :value="field.model?.[field.modelKey]"
              class="w-full rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-200"
              @change="updateSelectField(field, $event)"
            >
              <option
                v-for="option in field.options"
                :key="`${field.id}-${option.value}`"
                :value="option.value"
                :disabled="option.disabled"
              >
                {{ option.label }}
              </option>
            </select>

            <input
              v-else-if="field.type === 'number'"
              :value="field.model?.[field.modelKey]"
              :min="field.min"
              :max="field.max"
              type="number"
              class="w-full rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-200"
              @input="updateNumberField(field, $event)"
            >

            <label v-else class="inline-flex cursor-pointer items-center text-sm text-slate-700">
              <input
                :checked="Boolean(field.model?.[field.modelKey])"
                type="checkbox"
                class="h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-sky-500"
                @change="updateCheckboxField(field, $event)"
              >
              <span class="ml-2">{{ field.label }}</span>
            </label>
          </div>
        </div>
      </AppDisclosure>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'

import AppActionButton from '../../../components/ui/AppActionButton.vue'
import AppDisclosure from '../../../components/ui/AppDisclosure.vue'
import AppMetricPill from '../../../components/ui/AppMetricPill.vue'
import AppNotice from '../../../components/ui/AppNotice.vue'

const props = defineProps({
  card: { type: Object, required: true }
})

const toneMap = {
  sky: {
    panel: 'border-sky-200 bg-sky-50/70',
    badge: 'bg-sky-100 text-sky-800',
    summary: 'border-sky-100',
    primaryButtonVariant: 'sky'
  },
  amber: {
    panel: 'border-amber-200 bg-amber-50/70',
    badge: 'bg-amber-100 text-amber-800',
    summary: 'border-amber-100',
    primaryButtonVariant: 'amber'
  },
  slate: {
    panel: 'border-slate-200 bg-slate-50/80',
    badge: 'bg-slate-200 text-slate-700',
    summary: 'border-slate-200',
    primaryButtonVariant: 'slate'
  },
  cyan: {
    panel: 'border-cyan-200 bg-cyan-50/70',
    badge: 'bg-cyan-100 text-cyan-800',
    summary: 'border-cyan-100',
    primaryButtonVariant: 'cyan'
  },
  emerald: {
    panel: 'border-emerald-200 bg-emerald-50/70',
    badge: 'bg-emerald-100 text-emerald-800',
    summary: 'border-emerald-100',
    primaryButtonVariant: 'emerald'
  }
}

const toneClass = computed(() => toneMap[props.card.tone] || toneMap.sky)

const updateSelectField = (field, event) => {
  const rawValue = event.target.value
  field.model[field.modelKey] = field.numeric
    ? (rawValue === '' ? '' : Number(rawValue))
    : rawValue
}

const updateNumberField = (field, event) => {
  const rawValue = event.target.value
  field.model[field.modelKey] = rawValue === '' ? '' : Number(rawValue)
}

const updateCheckboxField = (field, event) => {
  field.model[field.modelKey] = event.target.checked
}
</script>
