export const DEFAULT_COUNSELOR_SCOPE = 'any'

const normalizeSearchQuery = (searchQuery = '') => String(searchQuery || '').trim()

const applySharedFilters = (params, filters = {}, searchQuery = '') => {
  const normalizedSearch = normalizeSearchQuery(searchQuery)

  if (normalizedSearch) {
    params.search = normalizedSearch
  }

  if (filters.gender) {
    params.gender = filters.gender
  }

  if (filters.education) {
    params.education = filters.education
  }

  if (filters.location) {
    params.location = filters.location
  }

  if (filters.eventType) {
    params.event_type = filters.eventType
  }

  if (filters.hasContent) {
    params.has_content = true
  }

  return params
}

const applyCounselorScopeFilter = (params, scope, defaultCounselorScope = DEFAULT_COUNSELOR_SCOPE) => {
  if (scope === defaultCounselorScope) {
    params.is_counselor = true
  }

  if (scope === 'dedicated') {
    params.counselor_scope = 'dedicated'
    params.is_counselor = true
  }

  if (scope === 'contains') {
    params.counselor_scope = 'contains'
    params.has_counselor_job = true
  }

  return params
}

export const buildPostParams = ({
  searchQuery = '',
  filters = {},
  scope = filters.counselorScope || DEFAULT_COUNSELOR_SCOPE,
  skip = 0,
  limit = 20,
  defaultCounselorScope = DEFAULT_COUNSELOR_SCOPE
} = {}) => {
  const params = { skip, limit }
  applySharedFilters(params, filters, searchQuery)
  applyCounselorScopeFilter(params, scope, defaultCounselorScope)
  return params
}

export const buildStatsParams = ({
  days = 7,
  searchQuery = '',
  filters = {},
  defaultCounselorScope = DEFAULT_COUNSELOR_SCOPE
} = {}) => {
  const params = { days }
  applySharedFilters(params, filters, searchQuery)
  applyCounselorScopeFilter(
    params,
    filters.counselorScope || defaultCounselorScope,
    defaultCounselorScope
  )
  return params
}

export const buildEventTypeOptionParams = ({
  days = 7,
  searchQuery = '',
  filters = {},
  defaultCounselorScope = DEFAULT_COUNSELOR_SCOPE
} = {}) => {
  const params = { days }
  applySharedFilters(params, { ...filters, eventType: '' }, searchQuery)
  applyCounselorScopeFilter(
    params,
    filters.counselorScope || defaultCounselorScope,
    defaultCounselorScope
  )
  return params
}
