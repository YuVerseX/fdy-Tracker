import { ref, watch } from 'vue'

import { postsApi } from '../../api/posts.js'
import { normalizeLatestSuccessTask } from '../../utils/taskFreshness.js'

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
  let detailRequestSeq = 0
  let freshnessRequestSeq = 0

  async function fetchPostDetail() {
    const requestId = ++detailRequestSeq
    loading.value = true
    error.value = ''

    try {
      const response = await postsApi.getPostById(route.params.id)
      if (requestId !== detailRequestSeq) return
      post.value = response.data || null
      void fetchLatestSuccessTask(response?.data?.source?.id || null)
    } catch (requestError) {
      if (requestId !== detailRequestSeq) return
      post.value = null
      latestSuccessTask.value = null
      freshnessUnavailable.value = false
      error.value = getErrorMessage(requestError)
      console.error('Error fetching post detail:', requestError)
    } finally {
      if (requestId === detailRequestSeq) {
        loading.value = false
      }
    }
  }

  async function fetchLatestSuccessTask(sourceId = null) {
    const requestId = ++freshnessRequestSeq
    freshnessLoading.value = true
    freshnessUnavailable.value = false
    latestSuccessTask.value = null

    try {
      const response = await postsApi.getFreshnessSummary(sourceId ? { source_id: sourceId } : {})
      if (requestId !== freshnessRequestSeq) return
      latestSuccessTask.value = normalizeLatestSuccessTask(response?.data || null)
    } catch (requestError) {
      if (requestId !== freshnessRequestSeq) return
      freshnessUnavailable.value = true
      if (requestError?.response?.status && requestError.response.status !== 404) {
        console.warn('获取公开任务新鲜度失败:', requestError)
      }
    } finally {
      if (requestId === freshnessRequestSeq) {
        freshnessLoading.value = false
      }
    }
  }

  watch(
    () => route.params.id,
    async () => {
      await fetchPostDetail()
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
