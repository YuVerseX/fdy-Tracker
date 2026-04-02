const VALID_RUNTIME_MODES = new Set(['unknown', 'disabled', 'basic', 'ai_enhanced'])

export const ADMIN_SECTION_OPTIONS = [
  { value: 'overview', label: '总览' },
  { value: 'processing', label: '处理任务' },
  { value: 'tasks', label: '任务中心' },
  { value: 'system', label: '系统设置' }
]

export const ADMIN_PROCESSING_TAB_OPTIONS = [
  { value: 'base', label: '基础处理' },
  { value: 'ai', label: '智能整理' }
]

export const ADMIN_SECTION_LEGACY_ALIASES = Object.freeze({
  governance: 'processing'
})

const RUNTIME_COPY = {
  unknown: {
    badge: '状态更新中',
    description: '当前能力信息正在更新，可以先继续查看现有概览。',
    emphasis: '如果刚完成设置或提交任务，相关状态会在后续同步后更新。'
  },
  disabled: {
    badge: '智能整理已关闭',
    description: '当前只保留基础处理和岗位整理。',
    emphasis: '抓取、关键信息整理和岗位整理仍可继续。'
  },
  basic: {
    badge: '基础整理可用',
    description: '基础处理已经可用，可以继续抓取、关键信息整理和岗位整理。',
    emphasis: '当前基础处理可继续使用；需要更细的摘要或岗位识别时，再开启智能整理。'
  },
  ai_enhanced: {
    badge: '智能整理可用',
    description: '智能整理已经就绪，可以继续补充摘要和岗位识别。',
    emphasis: '基础处理和智能整理都可以继续使用。'
  }
}

function isRuntimeObject(runtime) {
  return Boolean(runtime) && typeof runtime === 'object'
}

function hasCompleteRuntimeFlags(runtime) {
  return typeof runtime.analysis_enabled === 'boolean' && typeof runtime.openai_ready === 'boolean'
}

export function getAdminRuntimeMode(runtime) {
  if (!isRuntimeObject(runtime)) {
    return 'unknown'
  }
  if (typeof runtime.mode === 'string' && VALID_RUNTIME_MODES.has(runtime.mode)) {
    return runtime.mode
  }
  if (!hasCompleteRuntimeFlags(runtime)) {
    return 'unknown'
  }
  return runtime.openai_ready ? 'ai_enhanced' : 'basic'
}

export function getAdminRuntimeCopy(runtime) {
  return RUNTIME_COPY[getAdminRuntimeMode(runtime)] || RUNTIME_COPY.unknown
}
