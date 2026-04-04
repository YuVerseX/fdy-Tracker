import axios from 'axios'

const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL?.trim() || ''
export const LONG_RUNNING_TIMEOUT = 10 * 60 * 1000

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

const adminApiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  withCredentials: true,
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
  getPosts(params = {}) {
    return api.get('/api/posts', { params })
  },

  getStatsSummary(params = {}) {
    return api.get('/api/posts/stats/summary', { params })
  },

  getPostById(id) {
    return api.get(`/api/posts/${id}`)
  },

  getFreshnessSummary(params = {}) {
    return api.get('/api/posts/freshness-summary', { params })
  },

  healthCheck() {
    return api.get('/api/health')
  }
}

export const createAdminApi = (client) => ({
  login(username, password) {
    return client.post('/api/admin/session/login', { username, password })
  },

  getSession() {
    return client.get('/api/admin/session/me')
  },

  logout() {
    return client.post('/api/admin/session/logout')
  },

  getTaskRuns(params = {}) {
    return client.get('/api/admin/task-runs', { params })
  },

  getTaskSummary() {
    return client.get('/api/admin/task-runs/summary')
  },

  cancelTaskRun(taskId) {
    return client.post(`/api/admin/task-runs/${taskId}/cancel`)
  },

  getSources() {
    return client.get('/api/admin/sources')
  },

  getSchedulerConfig() {
    return client.get('/api/admin/scheduler-config')
  },

  updateSchedulerConfig(payload = {}) {
    return client.put('/api/admin/scheduler-config', payload)
  },

  runScrape(payload = {}) {
    return client.post('/api/admin/run-scrape', payload, { timeout: LONG_RUNNING_TIMEOUT })
  },

  backfillAttachments(payload = {}) {
    return client.post('/api/admin/backfill-attachments', payload, { timeout: LONG_RUNNING_TIMEOUT })
  },

  backfillBaseAnalysis(payload = {}) {
    return client.post('/api/admin/backfill-base-analysis', payload, { timeout: LONG_RUNNING_TIMEOUT })
  },

  getAnalysisSummary() {
    return client.get('/api/admin/analysis-summary')
  },

  getInsightSummary() {
    return client.get('/api/admin/insight-summary')
  },

  getDuplicateSummary() {
    return client.get('/api/admin/duplicate-summary')
  },

  backfillDuplicates(payload = {}) {
    return client.post('/api/admin/backfill-duplicates', payload, { timeout: LONG_RUNNING_TIMEOUT })
  },

  runAiAnalysis(payload = {}) {
    return client.post('/api/admin/run-ai-analysis', payload, { timeout: LONG_RUNNING_TIMEOUT })
  },

  getJobSummary(params = {}) {
    return requestWithFallback([
      () => client.get('/api/admin/job-summary', { params }),
      () => client.get('/api/admin/jobs-summary', { params }),
      () => client.get('/api/admin/job-extraction-summary', { params })
    ])
  },

  runJobExtraction(payload = {}) {
    return requestWithFallback([
      () => client.post('/api/admin/run-job-extraction', payload, { timeout: LONG_RUNNING_TIMEOUT }),
      () => client.post('/api/admin/run-ai-job-extraction', payload, { timeout: LONG_RUNNING_TIMEOUT }),
      () => client.post('/api/admin/run-job-analysis', payload, { timeout: LONG_RUNNING_TIMEOUT })
    ])
  }
})

export const adminApi = createAdminApi(adminApiClient)

export default api
