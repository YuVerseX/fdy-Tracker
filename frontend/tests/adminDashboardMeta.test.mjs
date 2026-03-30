import test from 'node:test'
import assert from 'node:assert/strict'

import {
  ADMIN_SECTION_OPTIONS,
  ADMIN_SECTION_LEGACY_ALIASES,
  getAdminRuntimeCopy,
  getAdminRuntimeMode
} from '../src/utils/adminDashboardMeta.js'

test('ADMIN_SECTION_OPTIONS should expose the target navigation order', () => {
  assert.deepEqual(
    ADMIN_SECTION_OPTIONS.map((item) => item.value),
    ['overview', 'processing', 'ai-enhancement', 'system', 'tasks']
  )
})

test('ADMIN_SECTION_LEGACY_ALIASES should document governance migration intent', () => {
  assert.equal(ADMIN_SECTION_LEGACY_ALIASES.governance, 'processing')
})

test('getAdminRuntimeMode should resolve basic and ai_enhanced modes from runtime flags', () => {
  assert.equal(getAdminRuntimeMode({ analysis_enabled: false, openai_ready: false }), 'basic')
  assert.equal(getAdminRuntimeMode({ analysis_enabled: true, openai_ready: false }), 'basic')
  assert.equal(getAdminRuntimeMode({ analysis_enabled: true, openai_ready: true }), 'ai_enhanced')
})

test('getAdminRuntimeMode should prefer canonical runtime.mode when it is valid', () => {
  assert.equal(
    getAdminRuntimeMode({ mode: 'disabled', analysis_enabled: true, openai_ready: true }),
    'disabled'
  )
})

test('getAdminRuntimeMode should return unknown for null runtime', () => {
  assert.equal(getAdminRuntimeMode(null), 'unknown')
})

test('getAdminRuntimeMode should return unknown when runtime fields are incomplete', () => {
  assert.equal(getAdminRuntimeMode({ analysis_enabled: true }), 'unknown')
  assert.equal(getAdminRuntimeMode({ openai_ready: false }), 'unknown')
})

test('getAdminRuntimeCopy should describe basic mode as available local analysis capability', () => {
  const copy = getAdminRuntimeCopy({ analysis_enabled: true, openai_ready: false })

  assert.equal(copy.badge, '基础模式')
  assert.match(copy.description, /规则分析/)
  assert.match(copy.description, /结构化字段/)
  assert.match(copy.emphasis, /本地岗位索引可正常使用/)
  assert.doesNotMatch(copy.description, /不可用|不可做|无法使用/)
  assert.doesNotMatch(copy.emphasis, /不可用|不可做|无法使用/)
})

test('getAdminRuntimeCopy should describe ai_enhanced mode as ready for AI enhancement', () => {
  const copy = getAdminRuntimeCopy({ analysis_enabled: true, openai_ready: true })

  assert.equal(copy.badge, 'AI 增强模式')
  assert.match(copy.description, /基础处理已就绪/)
  assert.match(copy.emphasis, /AI 增强/)
})

test('getAdminRuntimeCopy should keep disabled mode truthful about base capability when explicitly provided', () => {
  const copy = getAdminRuntimeCopy({ mode: 'disabled', analysis_enabled: false, openai_ready: false })

  assert.equal(copy.badge, '增强已关闭')
  assert.match(copy.description, /AI 增强开关关闭/)
  assert.match(copy.emphasis, /本地岗位索引仍可正常使用/)
})

test('getAdminRuntimeCopy should expose loading wording for unknown runtime', () => {
  const copy = getAdminRuntimeCopy({ analysis_enabled: true })

  assert.equal(copy.badge, '状态未知')
  assert.match(copy.description, /加载中|未获取完整信息/)
  assert.match(copy.emphasis, /未获取完整信息|稍后刷新/)
})
