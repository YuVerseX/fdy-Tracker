import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { postsApi } from '../../api/posts.js'
import {
  DEFAULT_COUNSELOR_SCOPE,
  DEFAULT_PUBLIC_EVENT_TYPE,
  buildEventTypeOptionParams as buildEventTypeOptionRequestParams,
  buildPostParams as buildPostRequestParams,
} from '../../utils/postFilters.js'
import { normalizeLatestSuccessTask } from '../../utils/taskFreshness.js'

const FETCH_DEBOUNCE_MS = 400
const FILTER_DEBOUNCE_FIELDS = new Set(['search', 'location'])
const LIST_SCOPE_OPTIONS = ['any', 'dedicated', 'contains', 'all']

const getSingleQueryValue = (value) => {
  if (Array.isArray(value)) {
    return value[0] ?? ''
  }
  return value ?? ''
}

const parseQueryText = (value) => String(getSingleQueryValue(value) || '').trim()

const parseQueryBoolean = (value, fallback = false) => {
  const normalized = parseQueryText(value).toLowerCase()
  if (['1', 'true', 'yes'].includes(normalized)) return true
  if (['0', 'false', 'no'].includes(normalized)) return false
  return fallback
}

const parseQueryPage = (value) => {
  const parsed = Number.parseInt(parseQueryText(value), 10)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1
}

const parseRouteScope = (value) => {
  const normalized = parseQueryText(value)
  return LIST_SCOPE_OPTIONS.includes(normalized) ? normalized : DEFAULT_COUNSELOR_SCOPE
}

const normalizeEventTypeFilter = (value) => parseQueryText(value) || DEFAULT_PUBLIC_EVENT_TYPE

const createDefaultFilters = () => ({
  gender: '',
  education: '',
  location: '',
  eventType: DEFAULT_PUBLIC_EVENT_TYPE,
  counselorScope: DEFAULT_COUNSELOR_SCOPE,
  hasContent: false
})

const hasAdvancedFilterSelection = (nextFilters) => {
  return Boolean(
    nextFilters.gender ||
    nextFilters.education ||
    nextFilters.location ||
    nextFilters.eventType !== DEFAULT_PUBLIC_EVENT_TYPE ||
    nextFilters.hasContent
  )
}

const getErrorMessage = (error, fallback) => {
  const status = error?.response?.status

  if (status === 404) {
    return '当前页码没有对应结果，可以返回上一页继续浏览。'
  }
  if (status >= 500) {
    return '服务暂时不可用，请稍后再试。'
  }
  if (error?.code === 'ECONNABORTED') {
    return '请求超时，请稍后再试。'
  }
  if (error?.response) {
    return fallback
  }

  return '暂时无法连接服务，请稍后再试。'
}

export function usePostListState(route, router) {
  const posts = ref([])
  const loading = ref(false)
  const refreshing = ref(false)
  const error = ref('')
  const searchQuery = ref('')
  const currentPage = ref(1)
  const totalPages = ref(1)
  const pageSize = 20
  const showAdvancedFilters = ref(false)
  const freshnessLoading = ref(false)
  const freshnessUnavailable = ref(false)
  const latestSuccessTask = ref(null)
  const totalMatchedPosts = ref(0)
  const scopeTotals = ref({
    any: 0,
    dedicated: 0,
    contains: 0,
    all: 0
  })
  const eventTypeOptions = ref([])
  const filters = ref(createDefaultFilters())

  const hasActiveFilters = computed(() => {
    return (
      filters.value.gender ||
      filters.value.education ||
      filters.value.location ||
      filters.value.eventType !== DEFAULT_PUBLIC_EVENT_TYPE ||
      filters.value.counselorScope !== DEFAULT_COUNSELOR_SCOPE ||
      filters.value.hasContent
    )
  })

  let fetchDebounceTimer = null
  let statsDebounceTimer = null
  let postsRequestSeq = 0
  let statsRequestSeq = 0

  const buildListRouteQuery = () => {
    const query = {}
    const normalizedSearch = searchQuery.value.trim()

    if (normalizedSearch) query.search = normalizedSearch
    if (filters.value.gender) query.gender = filters.value.gender
    if (filters.value.education) query.education = filters.value.education
    if (filters.value.location) query.location = filters.value.location
    if (filters.value.eventType && filters.value.eventType !== DEFAULT_PUBLIC_EVENT_TYPE) {
      query.event_type = filters.value.eventType
    }
    if (filters.value.counselorScope !== DEFAULT_COUNSELOR_SCOPE) query.scope = filters.value.counselorScope
    if (filters.value.hasContent) query.has_content = 'true'
    if (currentPage.value > 1) query.page = String(currentPage.value)

    return query
  }

  const syncListRouteQuery = () => {
    void router.replace({
      name: 'PostList',
      query: buildListRouteQuery()
    })
  }

  const hydrateStateFromRoute = () => {
    const nextFilters = {
      ...createDefaultFilters(),
      gender: parseQueryText(route.query.gender),
      education: parseQueryText(route.query.education),
      location: parseQueryText(route.query.location),
      eventType: normalizeEventTypeFilter(route.query.event_type),
      counselorScope: parseRouteScope(route.query.scope),
      hasContent: parseQueryBoolean(route.query.has_content, false)
    }

    searchQuery.value = parseQueryText(route.query.search)
    currentPage.value = parseQueryPage(route.query.page)
    filters.value = nextFilters
    showAdvancedFilters.value = hasAdvancedFilterSelection(nextFilters)
  }

  const buildPostParams = ({ scope = filters.value.counselorScope, skip = 0, limit = pageSize } = {}) => {
    return buildPostRequestParams({
      searchQuery: searchQuery.value,
      filters: filters.value,
      scope,
      skip,
      limit,
      defaultCounselorScope: DEFAULT_COUNSELOR_SCOPE
    })
  }

  const buildEventTypeOptionParams = () => {
    return buildEventTypeOptionRequestParams({
      days: 7,
      searchQuery: searchQuery.value,
      filters: filters.value,
      defaultCounselorScope: DEFAULT_COUNSELOR_SCOPE
    })
  }

  const triggerFetch = ({ debounce = false, silent = false } = {}) => {
    if (fetchDebounceTimer) {
      clearTimeout(fetchDebounceTimer)
      fetchDebounceTimer = null
    }

    if (!debounce) {
      void fetchPosts({ silent })
      return
    }

    fetchDebounceTimer = setTimeout(() => {
      fetchDebounceTimer = null
      void fetchPosts({ silent })
    }, FETCH_DEBOUNCE_MS)
  }

  const triggerStatsFetch = ({ debounce = false } = {}) => {
    if (statsDebounceTimer) {
      clearTimeout(statsDebounceTimer)
      statsDebounceTimer = null
    }

    if (!debounce) {
      void fetchStatsSummary()
      return
    }

    statsDebounceTimer = setTimeout(() => {
      statsDebounceTimer = null
      void fetchStatsSummary()
    }, FETCH_DEBOUNCE_MS)
  }

  const fetchPosts = async ({ silent = false } = {}) => {
    const requestId = ++postsRequestSeq

    if (silent && posts.value.length > 0) {
      refreshing.value = true
    } else {
      loading.value = true
    }
    error.value = ''

    try {
      const response = await postsApi.getPosts(
        buildPostParams({
          scope: filters.value.counselorScope,
          skip: (currentPage.value - 1) * pageSize,
          limit: pageSize
        })
      )

      if (requestId !== postsRequestSeq) return

      const total = response.data.total ?? 0
      const nextItems = response.data.items || []
      const nextTotalPages = Math.max(1, Math.ceil(total / pageSize))

      totalMatchedPosts.value = total
      totalPages.value = nextTotalPages

      if (currentPage.value > nextTotalPages) {
        posts.value = []
        error.value = '当前页码没有对应结果，可以返回上一页继续浏览。'
      } else {
        posts.value = nextItems
      }

      const scopeKeys = ['any', 'dedicated', 'contains', 'all']
      const totalResponses = await Promise.allSettled(
        scopeKeys.map((scope) => postsApi.getPosts(buildPostParams({ scope, limit: 1 })))
      )

      if (requestId !== postsRequestSeq) return

      const nextScopeTotals = { ...scopeTotals.value }
      totalResponses.forEach((result, index) => {
        const scope = scopeKeys[index]
        if (result.status === 'fulfilled') {
          nextScopeTotals[scope] = result.value?.data?.total ?? 0
        }
      })
      scopeTotals.value = nextScopeTotals
    } catch (requestError) {
      if (requestId !== postsRequestSeq) return
      error.value = getErrorMessage(requestError, '招聘列表加载失败，请稍后重试。')
      console.error('Error fetching posts:', requestError)
    } finally {
      if (requestId === postsRequestSeq) {
        loading.value = false
        refreshing.value = false
      }
    }
  }

  const fetchLatestSuccessTask = async () => {
    freshnessLoading.value = true
    freshnessUnavailable.value = false
    latestSuccessTask.value = null

    try {
      const response = await postsApi.getFreshnessSummary()
      latestSuccessTask.value = normalizeLatestSuccessTask(response?.data || null)
    } catch (requestError) {
      freshnessUnavailable.value = true
      if (requestError?.response?.status && requestError.response.status !== 404) {
        console.warn('获取公开任务新鲜度失败:', requestError)
      }
    } finally {
      freshnessLoading.value = false
    }
  }

  const fetchStatsSummary = async () => {
    const requestId = ++statsRequestSeq

    try {
      const response = await postsApi.getStatsSummary(buildEventTypeOptionParams())
      if (requestId !== statsRequestSeq) return

      const selectedEventType = filters.value.eventType
      let nextOptions = Array.isArray(response?.data?.event_type_distribution)
        ? response.data.event_type_distribution
        : []

      if (
        selectedEventType &&
        selectedEventType !== DEFAULT_PUBLIC_EVENT_TYPE &&
        !nextOptions.some((item) => item.event_type === selectedEventType)
      ) {
        nextOptions = [{ event_type: selectedEventType }, ...nextOptions]
      }

      eventTypeOptions.value = nextOptions.filter(
        (item) => item?.event_type && item.event_type !== DEFAULT_PUBLIC_EVENT_TYPE
      )
    } catch (requestError) {
      if (requestId !== statsRequestSeq) return
      console.warn('获取筛选项摘要失败:', requestError)
    }
  }

  const refreshList = ({ debounce = false, silent = true } = {}) => {
    currentPage.value = 1
    syncListRouteQuery()
    triggerFetch({ debounce, silent })
    triggerStatsFetch({ debounce })
  }

  const handleSearchInput = () => {
    refreshList({ debounce: true })
  }

  const handleLocationInput = () => {
    refreshList({ debounce: true })
  }

  const handleFilter = (changedField = '') => {
    currentPage.value = 1
    syncListRouteQuery()
    const shouldDebounce = FILTER_DEBOUNCE_FIELDS.has(changedField)
    triggerFetch({ debounce: shouldDebounce, silent: true })
    triggerStatsFetch({ debounce: shouldDebounce })
  }

  const handleManualSearch = () => {
    refreshList({ debounce: false })
  }

  const clearFilters = () => {
    searchQuery.value = ''
    filters.value = createDefaultFilters()
    showAdvancedFilters.value = false
    handleFilter()
  }

  const goToPage = async (page, { force = false } = {}) => {
    if (page < 1) return
    if (!force && page > totalPages.value) return

    currentPage.value = page
    syncListRouteQuery()
    await fetchPosts()
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const toggleAdvancedFilters = () => {
    showAdvancedFilters.value = !showAdvancedFilters.value
  }

  const formatDateTime = (value) => {
    if (!value) return '--'
    return new Date(value).toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone: 'Asia/Shanghai'
    })
  }

  const getRelativeTimeLabel = (value) => {
    if (!value) return '--'

    const diffMs = Date.now() - new Date(value).getTime()
    if (diffMs < 0) return '刚刚'

    const minutes = Math.floor(diffMs / (1000 * 60))
    if (minutes < 1) return '刚刚'
    if (minutes < 60) return `${minutes} 分钟前`

    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours} 小时前`

    const days = Math.floor(hours / 24)
    if (days < 7) return `${days} 天前`

    return formatDateTime(value)
  }

  onMounted(() => {
    hydrateStateFromRoute()
    void Promise.all([fetchPosts(), fetchLatestSuccessTask(), fetchStatsSummary()])
  })

  onBeforeUnmount(() => {
    if (fetchDebounceTimer) {
      clearTimeout(fetchDebounceTimer)
    }
    if (statsDebounceTimer) {
      clearTimeout(statsDebounceTimer)
    }
  })

  return {
    currentPage,
    error,
    eventTypeOptions,
    fetchPosts,
    filters,
    freshnessLoading,
    freshnessUnavailable,
    getRelativeTimeLabel,
    goToPage,
    handleFilter,
    handleLocationInput,
    handleManualSearch,
    handleSearchInput,
    hasActiveFilters,
    latestSuccessTask,
    loading,
    posts,
    refreshing,
    scopeTotals,
    searchQuery,
    showAdvancedFilters,
    toggleAdvancedFilters,
    totalMatchedPosts,
    totalPages,
    clearFilters,
    formatDateTime
  }
}
