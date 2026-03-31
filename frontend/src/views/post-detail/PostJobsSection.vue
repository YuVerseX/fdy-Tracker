<template>
  <AppSurface v-if="jobView.rows.length > 0" padding="lg">
    <div class="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h2 class="text-lg font-semibold text-slate-950">岗位明细</h2>
        <p class="mt-1 text-sm text-slate-600">
          {{ jobView.mode === 'table' ? `共整理 ${jobView.rows.length} 个岗位，建议先看岗位表再对照补充信息。` : '当前公告整理出 1 个岗位，可直接查看岗位要求。' }}
        </p>
      </div>
    </div>

    <div v-if="jobView.mode === 'table'" class="mt-5 space-y-3 md:hidden">
      <article
        v-for="row in jobView.rows"
        :key="row.id"
        class="rounded-[18px] border border-[rgba(148,163,184,0.18)] bg-[rgba(244,247,250,0.78)] px-4 py-4"
      >
        <div class="flex items-start justify-between gap-3">
          <h3 class="min-w-0 text-base font-semibold leading-7 text-slate-950">
            {{ row.job_name }}
          </h3>
          <AppMetricPill label="人数" :value="row.headcount" tone="info" />
        </div>

        <AppFactList
          class="mt-3"
          :items="[
            { label: '学历', value: row.education },
            { label: '专业', value: row.major },
            { label: '地点', value: row.location }
          ]"
          :columns="1"
          compact
          tone="muted"
        />
      </article>
    </div>

    <div v-if="jobView.mode === 'table'" class="mt-5 hidden md:block overflow-x-auto">
      <table class="app-table">
        <caption class="sr-only">岗位名称、人数、学历、专业和地点列表</caption>
        <thead>
          <tr>
            <th
              v-for="column in jobView.columns"
              :key="column"
            >
              {{ column }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in jobView.rows" :key="row.id">
            <td>{{ row.job_name }}</td>
            <td>{{ row.headcount }}</td>
            <td>{{ row.education }}</td>
            <td>{{ row.major }}</td>
            <td>{{ row.location }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <AppFactList
      v-else
      class="mt-5"
      :items="[
        { label: '岗位名称', value: jobView.rows[0].job_name },
        { label: '人数', value: jobView.rows[0].headcount },
        { label: '学历', value: jobView.rows[0].education },
        { label: '专业', value: jobView.rows[0].major },
        { label: '地点', value: jobView.rows[0].location }
      ]"
      compact
    />
  </AppSurface>
</template>

<script setup>
import AppFactList from '../../components/ui/AppFactList.vue'
import AppMetricPill from '../../components/ui/AppMetricPill.vue'
import AppSurface from '../../components/ui/AppSurface.vue'

defineProps({
  jobView: { type: Object, required: true }
})
</script>
