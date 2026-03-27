import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.trim() || ''
const LONG_RUNNING_TIMEOUT = 10 * 60 * 1000
const ADMIN_AUTH_STORAGE_KEY = 'fdy.admin.auth'

const getSessionStorage = () => {
  if (typeof window === 'undefined') {
    return null
  }

  try {
    return window.sessionStorage
  } catch (_error) {
    return null
  }
}

const encodeBasicToken = (username, password) => {
  if (typeof window === 'undefined' || typeof window.btoa !== 'function') {
    return ''
  }

  const payload = new TextEncoder().encode(`${username}:${password}`)
  let binary = ''
  payload.forEach((byte) => {
    binary += String.fromCharCode(byte)
  })
  return `Basic ${window.btoa(binary)}`
}

const readAdminAuth = () => {
  const storage = getSessionStorage()
  if (!storage) return null

  const rawValue = storage.getItem(ADMIN_AUTH_STORAGE_KEY)
  if (!rawValue) return null

  try {
    const parsed = JSON.parse(rawValue)
    if (!parsed?.username || !parsed?.token) {
      return null
    }
    return parsed
  } catch (_error) {
    return null
  }
}

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

api.interceptors.request.use((config) => {
  const requestUrl = String(config?.url || '')
  if (!requestUrl.startsWith('/api/admin/')) {
    return config
  }

  const adminAuth = readAdminAuth()
  if (!adminAuth?.token) {
    return config
  }

  config.headers = config.headers || {}
  config.headers.Authorization = adminAuth.token
  return config
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
  setCredentials(username, password) {
    const normalizedUsername = String(username || '').trim()
    const normalizedPassword = String(password || '')
    if (!normalizedUsername || !normalizedPassword) {
      return false
    }

    const token = encodeBasicToken(normalizedUsername, normalizedPassword)
    if (!token) {
      return false
    }

    const storage = getSessionStorage()
    if (!storage) {
      return false
    }

    storage.setItem(ADMIN_AUTH_STORAGE_KEY, JSON.stringify({
      username: normalizedUsername,
      token,
    }))
    return true
  },

  clearCredentials() {
    const storage = getSessionStorage()
    storage?.removeItem(ADMIN_AUTH_STORAGE_KEY)
  },

  hasCredentials() {
    return Boolean(readAdminAuth()?.token)
  },

  getSavedUsername() {
    return readAdminAuth()?.username || ''
  },

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
    return api.post('/api/admin/run-scrape', payload, { timeout: LONG_RUNNING_TIMEOUT })
  },

  backfillAttachments(payload = {}) {
    return api.post('/api/admin/backfill-attachments', payload, { timeout: LONG_RUNNING_TIMEOUT })
  },

  getAnalysisSummary() {
    return api.get('/api/admin/analysis-summary')
  },

  getInsightSummary() {
    return api.get('/api/admin/insight-summary')
  },

  getDuplicateSummary() {
    return api.get('/api/admin/duplicate-summary')
  },

  backfillDuplicates(payload = {}) {
    return api.post('/api/admin/backfill-duplicates', payload, { timeout: LONG_RUNNING_TIMEOUT })
  },

  runAiAnalysis(payload = {}) {
    return api.post('/api/admin/run-ai-analysis', payload, { timeout: LONG_RUNNING_TIMEOUT })
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
      () => api.post('/api/admin/run-job-extraction', payload, { timeout: LONG_RUNNING_TIMEOUT }),
      () => api.post('/api/admin/run-ai-job-extraction', payload, { timeout: LONG_RUNNING_TIMEOUT }),
      () => api.post('/api/admin/run-job-analysis', payload, { timeout: LONG_RUNNING_TIMEOUT })
    ])
  }
}

export default api
