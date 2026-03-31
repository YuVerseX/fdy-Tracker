import { ref, watch } from 'vue'

import { postsApi } from '../../api/posts.js'

const normalizeTaskRun = (run) => {
  if (!run) return null

  const finishedAt = run.finished_at || run.finishedAt || run.last_success_at || run.lastSuccessAt
  if (!finishedAt) return null

  return {
    taskType: run.task_type || run.taskType || '',
    taskLabel: run.task_label || run.taskLabel || '',
    finishedAt
  }
}

const normalizeSummaryResponse = (data) => {
  if (!data) return null

  const candidate =
    data.latest_success_run ||
    data.latest_success_task ||
    data.latest_success ||
    data.last_success ||
    data

  return normalizeTaskRun(candidate)
}

const getErrorMessage = (error) => {
  const status = error?.response?.status

  if (status === 404) {
    return '这条招聘信息不存在，可能已经被删除。'
  }
  if (status >= 500) {
    return '服务暂时不可用，请稍后再试。'
  }
  if (error?.code === 'ECONNABORTED') {
    return '请求超时，请稍后重试。'
  }
  if (error?.response) {
    return '获取招聘详情失败，请稍后重试。'
  }

  return '暂时无法连接服务，请稍后再试。'
}

export function usePostDetailState(route) {
  const post = ref(null)
  const loading = ref(false)
  const error = ref('')
  const latestSuccessTask = ref(null)
  const freshnessLoading = ref(false)
  const freshnessUnavailable = ref(false)

  async function fetchPostDetail() {
    loading.value = true
    error.value = ''

    try {
      const response = await postsApi.getPostById(route.params.id)
      post.value = response.data || null
    } catch (requestError) {
      post.value = null
      error.value = getErrorMessage(requestError)
      console.error('Error fetching post detail:', requestError)
    } finally {
      loading.value = false
    }
  }

  async function fetchLatestSuccessTask() {
    freshnessLoading.value = true
    freshnessUnavailable.value = false
    latestSuccessTask.value = null

    try {
      const response = await postsApi.getFreshnessSummary()
      latestSuccessTask.value = normalizeSummaryResponse({
        latest_success_run: response?.data?.latest_success_run || null,
        latest_success_at: response?.data?.latest_success_at || null
      })
    } catch (requestError) {
      freshnessUnavailable.value = true
      if (requestError?.response?.status && requestError.response.status !== 404) {
        console.warn('获取公开任务新鲜度失败:', requestError)
      }
    } finally {
      freshnessLoading.value = false
    }
  }

  watch(
    () => route.params.id,
    async () => {
      await Promise.all([fetchPostDetail(), fetchLatestSuccessTask()])
    },
    { immediate: true }
  )

  return {
    post,
    loading,
    error,
    latestSuccessTask,
    freshnessLoading,
    freshnessUnavailable,
    fetchPostDetail,
    fetchLatestSuccessTask
  }
}
