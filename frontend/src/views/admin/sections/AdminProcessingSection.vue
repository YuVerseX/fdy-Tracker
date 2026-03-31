<template>
  <section class="space-y-5 lg:space-y-6">
    <AppSurface padding="md">
      <AppSectionHeader
        title="处理任务"
        description="按任务类型处理数据，并查看最近执行结果。"
        :aside="processingMode === 'base' ? '先更新数据，再补齐整理结果。' : '在已有结果上继续运行 AI 任务。'"
      />
      <div class="mt-4">
        <AppTabNav
          :model-value="processingMode"
          :items="processingTabOptions"
          aria-label="处理任务模式"
          @update:modelValue="setProcessingMode"
        />
      </div>
    </AppSurface>

    <AdminDataProcessingSection
      v-if="processingMode === 'base'"
      v-bind="baseSection"
    />
    <AdminAiEnhancementSection
      v-else
      v-bind="aiSection"
    />
  </section>
</template>

<script setup>
import AppSurface from '../../../components/ui/AppSurface.vue'
import AppSectionHeader from '../../../components/ui/AppSectionHeader.vue'
import AppTabNav from '../../../components/ui/AppTabNav.vue'
import AdminAiEnhancementSection from './AdminAiEnhancementSection.vue'
import AdminDataProcessingSection from './AdminDataProcessingSection.vue'

defineProps({
  processingMode: { type: String, required: true },
  processingTabOptions: { type: Array, required: true },
  setProcessingMode: { type: Function, required: true },
  baseSection: { type: Object, required: true },
  aiSection: { type: Object, required: true }
})
</script>
