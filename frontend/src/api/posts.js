import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.trim() || ''

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

const canFallback = (error) => {
  const status = error?.response?.status
  return status === 404 || status === 405
}

const requestWithFallback = async (requesters = []) => {
  let lastError = null
  for (const requester of requesters) {
    try {
      return await requester()
    } catch (error) {
      lastError = error
      if (!canFallback(error)) {
        throw error
      }
    }
  }
  throw lastError || new Error('未找到可用接口')
}

export const postsApi = {
  // 获取招聘信息列表
  getPosts(params = {}) {
    return api.get('/api/posts', { params })
  },

  getStatsSummary(params = {}) {
    return api.get('/api/posts/stats/summary', { params })
  },

  // 获取招聘信息详情
  getPostById(id) {
    return api.get(`/api/posts/${id}`)
  },

  // 健康检查
  healthCheck() {
    return api.get('/api/health')
  }
}

export const adminApi = {
  getTaskRuns(params = {}) {
    return api.get('/api/admin/task-runs', { params })
  },

  getTaskSummary() {
    return api.get('/api/admin/task-runs/summary')
  },

  getSources() {
    return api.get('/api/admin/sources')
  },

  getSchedulerConfig() {
    return api.get('/api/admin/scheduler-config')
  },

  updateSchedulerConfig(payload = {}) {
    return api.put('/api/admin/scheduler-config', payload)
  },

  runScrape(payload = {}) {
    return api.post('/api/admin/run-scrape', payload)
  },

  backfillAttachments(payload = {}) {
    return api.post('/api/admin/backfill-attachments', payload)
  },

  getAnalysisSummary() {
    return api.get('/api/admin/analysis-summary')
  },

  runAiAnalysis(payload = {}) {
    return api.post('/api/admin/run-ai-analysis', payload)
  },

  getJobSummary(params = {}) {
    return requestWithFallback([
      () => api.get('/api/admin/job-summary', { params }),
      () => api.get('/api/admin/jobs-summary', { params }),
      () => api.get('/api/admin/job-extraction-summary', { params })
    ])
  },

  runJobExtraction(payload = {}) {
    return requestWithFallback([
      () => api.post('/api/admin/run-job-extraction', payload),
      () => api.post('/api/admin/run-ai-job-extraction', payload),
      () => api.post('/api/admin/run-job-analysis', payload)
    ])
  }
}

export default api
