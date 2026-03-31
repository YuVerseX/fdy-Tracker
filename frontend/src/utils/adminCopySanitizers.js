const INTERNAL_ERROR_PATTERNS = [
  /traceback/i,
  /sqlite/i,
  /sqlalchemy/i,
  /integrityerror/i,
  /constraint failed/i,
  /not null constraint/i,
  /openai_api_key/i,
  /admin_session_secret/i,
  /admin_username/i,
  /admin_password/i,
  /\bbase_url\b/i,
  /\bprovider\b/i,
  /\bsdk\b/i,
  /https?:\/\//i
]

const COPY_REPLACEMENTS = [
  ['AI 增强', '智能整理'],
  ['AI 岗位补抽', '智能岗位识别'],
  ['AI 分析', '智能摘要整理'],
  ['基础分析', '关键信息整理'],
  ['岗位索引', '岗位整理'],
  ['结构化字段', '关键信息字段'],
  ['结构化信息', '关键信息'],
  ['OpenAI', '智能服务']
]

const applyCopyReplacements = (value) => {
  let normalized = String(value || '').trim()
  for (const [from, to] of COPY_REPLACEMENTS) {
    normalized = normalized.replaceAll(from, to)
  }
  return normalized
}

export const normalizeAdminUiText = (value, fallback = '') => {
  const normalized = applyCopyReplacements(value)
  return normalized || fallback
}

export const normalizeAdminUiMessage = (value, fallback = '系统暂时无法完成这次处理，请稍后再试。') => {
  const normalized = String(value || '').trim()
  if (!normalized) return fallback
  if (INTERNAL_ERROR_PATTERNS.some((pattern) => pattern.test(normalized))) {
    return fallback
  }
  return applyCopyReplacements(normalized)
}
