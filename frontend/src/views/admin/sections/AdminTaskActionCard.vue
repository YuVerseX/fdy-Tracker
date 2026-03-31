<template>
  <article class="app-surface px-4 py-4 sm:p-5" :class="toneClass.panel">
    <div class="flex flex-col gap-2.5 sm:gap-3">
      <div class="flex flex-wrap items-center gap-2.5 sm:gap-3">
        <span v-if="card.badge" class="inline-flex items-center rounded-full px-3 py-1 text-xs font-medium" :class="toneClass.badge">
          {{ card.badge }}
        </span>
        <h3 class="text-base font-semibold text-slate-950">{{ card.title }}</h3>
      </div>

      <p class="text-sm leading-6 text-slate-600">{{ card.description }}</p>

      <div v-if="card.summary" class="rounded-[16px] border bg-white/90 px-3.5 py-2.5 text-sm font-medium leading-6 text-slate-900" :class="toneClass.summary">
        {{ card.summary }}
      </div>

      <div v-if="card.chips?.length" class="flex flex-wrap gap-1.5 sm:gap-2">
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

      <div class="flex flex-wrap gap-2.5 sm:gap-3">
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

      <p v-if="card.footer" class="text-xs leading-5 text-slate-500">{{ card.footer }}</p>

      <AppDisclosure
        v-if="card.disclosure?.fields?.length"
        class="px-3.5 py-3 sm:px-4 sm:py-4"
        :summary="card.disclosure.summary"
      >
        <p v-if="card.disclosure.hint" class="mb-3 text-xs leading-5 text-slate-500">{{ card.disclosure.hint }}</p>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div v-for="field in card.disclosure.fields" :key="field.id" :class="field.type === 'checkbox' ? 'sm:col-span-2' : ''">
            <label v-if="field.type !== 'checkbox'" class="mb-1.5 block text-xs font-medium uppercase tracking-[0.08em] text-slate-500">
              {{ field.label }}
            </label>

            <select
              v-if="field.type === 'select'"
              :value="field.model?.[field.modelKey]"
              class="app-select app-select--compact"
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
              class="app-input app-input--compact"
              @input="updateNumberField(field, $event)"
            >

            <label v-else class="inline-flex cursor-pointer items-start text-sm leading-5 text-slate-700">
              <input
                :checked="Boolean(field.model?.[field.modelKey])"
                type="checkbox"
                class="app-checkbox"
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
    panel: 'app-surface--info',
    badge: 'bg-sky-100 text-sky-800',
    summary: 'border-sky-100',
    primaryButtonVariant: 'sky'
  },
  amber: {
    panel: 'app-surface--warning',
    badge: 'bg-amber-100 text-amber-800',
    summary: 'border-amber-100',
    primaryButtonVariant: 'amber'
  },
  slate: {
    panel: 'app-surface--muted',
    badge: 'bg-slate-200 text-slate-700',
    summary: 'border-slate-200',
    primaryButtonVariant: 'slate'
  },
  cyan: {
    panel: 'app-surface--info',
    badge: 'bg-cyan-100 text-cyan-800',
    summary: 'border-cyan-100',
    primaryButtonVariant: 'cyan'
  },
  emerald: {
    panel: 'app-surface--success',
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
