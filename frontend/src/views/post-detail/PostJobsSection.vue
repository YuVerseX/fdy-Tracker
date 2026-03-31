<template>
  <section v-if="jobView.rows.length > 0" class="rounded-[28px] border border-slate-200 bg-white/90 p-6 shadow-sm">
    <div class="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h2 class="text-lg font-semibold text-slate-950">岗位明细</h2>
        <p class="mt-1 text-sm text-slate-600">
          {{ jobView.mode === 'table' ? `共整理 ${jobView.rows.length} 个岗位。` : '当前公告整理出 1 个岗位。' }}
        </p>
      </div>
    </div>

    <div v-if="jobView.mode === 'table'" class="mt-5 overflow-x-auto">
      <table class="min-w-full border-separate border-spacing-0 text-sm">
        <thead>
          <tr class="text-left text-slate-500">
            <th
              v-for="column in jobView.columns"
              :key="column"
              class="border-b border-slate-200 px-4 py-3 font-medium"
            >
              {{ column }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in jobView.rows" :key="row.id" class="text-slate-800">
            <td class="border-b border-slate-100 px-4 py-4 font-medium text-slate-900">{{ row.job_name }}</td>
            <td class="border-b border-slate-100 px-4 py-4">{{ row.headcount }}</td>
            <td class="border-b border-slate-100 px-4 py-4">{{ row.education }}</td>
            <td class="border-b border-slate-100 px-4 py-4">{{ row.major }}</td>
            <td class="border-b border-slate-100 px-4 py-4">{{ row.location }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-else class="mt-5 rounded-2xl border border-slate-100 bg-slate-50/70 px-5 py-5">
      <dl class="grid grid-cols-1 gap-y-3 md:grid-cols-2 md:gap-x-6">
        <div>
          <dt class="text-sm text-slate-500">岗位名称</dt>
          <dd class="mt-1 text-base font-medium text-slate-900">{{ jobView.rows[0].job_name }}</dd>
        </div>
        <div>
          <dt class="text-sm text-slate-500">人数</dt>
          <dd class="mt-1 text-base font-medium text-slate-900">{{ jobView.rows[0].headcount }}</dd>
        </div>
        <div>
          <dt class="text-sm text-slate-500">学历</dt>
          <dd class="mt-1 text-base font-medium text-slate-900">{{ jobView.rows[0].education }}</dd>
        </div>
        <div>
          <dt class="text-sm text-slate-500">专业</dt>
          <dd class="mt-1 text-base font-medium text-slate-900">{{ jobView.rows[0].major }}</dd>
        </div>
        <div>
          <dt class="text-sm text-slate-500">地点</dt>
          <dd class="mt-1 text-base font-medium text-slate-900">{{ jobView.rows[0].location }}</dd>
        </div>
      </dl>
    </div>
  </section>
</template>

<script setup>
defineProps({
  jobView: { type: Object, required: true }
})
</script>
