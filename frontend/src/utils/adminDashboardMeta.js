const VALID_RUNTIME_MODES = new Set(['unknown', 'disabled', 'basic', 'ai_enhanced'])

// 这是面向后续 task-oriented dashboard 的目标分区 taxonomy。
// 当前页面在视图层仍可能保留 legacy key，迁移阶段不要把这里当成现状唯一真相。
export const ADMIN_SECTION_OPTIONS = [
  { value: 'overview', label: '总览' },
  { value: 'processing', label: '数据处理' },
  { value: 'ai-enhancement', label: 'AI 增强' },
  { value: 'system', label: '系统配置' },
  { value: 'tasks', label: '任务记录' }
]

export const ADMIN_SECTION_LEGACY_ALIASES = Object.freeze({
  governance: 'processing'
})

const RUNTIME_COPY = {
  unknown: {
    badge: '状态未知',
    description: '分析运行状态加载中，或后端暂未返回完整运行信息。',
    emphasis: '当前未获取完整信息，稍后刷新后再判断是否可执行基础处理或 AI 增强。'
  },
  disabled: {
    badge: '增强已关闭',
    description: '当前 AI 增强开关关闭，系统继续保留基础分析、结构化字段和岗位索引链路。',
    emphasis: '基础分析、结构化字段和本地岗位索引仍可正常使用。'
  },
  basic: {
    badge: '基础模式',
    description: '规则分析会继续产出结构化字段，当前仍可依赖本地能力完成基础处理。',
    emphasis: '规则分析、结构化字段和本地岗位索引可正常使用。'
  },
  ai_enhanced: {
    badge: 'AI 增强模式',
    description: '基础处理已就绪，当前可以在已有结构化结果之上继续执行 AI 增强。',
    emphasis: '基础处理已就绪，可做 AI 增强。'
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
