import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.trim() || ''
const LONG_RUNNING_TIMEOUT = 10 * 60 * 1000

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

  getFreshnessSummary() {
    return api.get('/api/posts/freshness-summary')
  },

  healthCheck() {
    return api.get('/api/health')
  }
}

export const adminApi = {
  login(username, password) {
    return adminApiClient.post('/api/admin/session/login', { username, password })
  },

  getSession() {
    return adminApiClient.get('/api/admin/session/me')
  },

  logout() {
    return adminApiClient.post('/api/admin/session/logout')
  },

  getTaskRuns(params = {}) {
    return adminApiClient.get('/api/admin/task-runs', { params })
  },

  getTaskSummary() {
    return adminApiClient.get('/api/admin/task-runs/summary')
  },

  getSources() {
    return adminApiClient.get('/api/admin/sources')
  },

  getSchedulerConfig() {
    return adminApiClient.get('/api/admin/scheduler-config')
  },

  updateSchedulerConfig(payload = {}) {
    return adminApiClient.put('/api/admin/scheduler-config', payload)
  },

  runScrape(payload = {}) {
    return adminApiClient.post('/api/admin/run-scrape', payload, { timeout: LONG_RUNNING_TIMEOUT })
  },

  backfillAttachments(payload = {}) {
    return adminApiClient.post('/api/admin/backfill-attachments', payload, { timeout: LONG_RUNNING_TIMEOUT })
  },

  getAnalysisSummary() {
    return adminApiClient.get('/api/admin/analysis-summary')
  },

  getInsightSummary() {
    return adminApiClient.get('/api/admin/insight-summary')
  },

  getDuplicateSummary() {
    return adminApiClient.get('/api/admin/duplicate-summary')
  },

  backfillDuplicates(payload = {}) {
    return adminApiClient.post('/api/admin/backfill-duplicates', payload, { timeout: LONG_RUNNING_TIMEOUT })
  },

  runAiAnalysis(payload = {}) {
    return adminApiClient.post('/api/admin/run-ai-analysis', payload, { timeout: LONG_RUNNING_TIMEOUT })
  },

  getJobSummary(params = {}) {
    return requestWithFallback([
      () => adminApiClient.get('/api/admin/job-summary', { params }),
      () => adminApiClient.get('/api/admin/jobs-summary', { params }),
      () => adminApiClient.get('/api/admin/job-extraction-summary', { params })
    ])
  },

  runJobExtraction(payload = {}) {
    return requestWithFallback([
      () => adminApiClient.post('/api/admin/run-job-extraction', payload, { timeout: LONG_RUNNING_TIMEOUT }),
      () => adminApiClient.post('/api/admin/run-ai-job-extraction', payload, { timeout: LONG_RUNNING_TIMEOUT }),
      () => adminApiClient.post('/api/admin/run-job-analysis', payload, { timeout: LONG_RUNNING_TIMEOUT })
    ])
  }
}

export default api
