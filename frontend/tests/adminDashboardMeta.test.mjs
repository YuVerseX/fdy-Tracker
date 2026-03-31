import test from 'node:test'
import assert from 'node:assert/strict'

import {
  ADMIN_PROCESSING_TAB_OPTIONS,
  ADMIN_SECTION_OPTIONS,
  ADMIN_SECTION_LEGACY_ALIASES,
  getAdminRuntimeCopy,
  getAdminRuntimeMode
} from '../src/utils/adminDashboardMeta.js'

test('ADMIN_SECTION_OPTIONS should expose the new navigation order', () => {
  assert.deepEqual(
    ADMIN_SECTION_OPTIONS.map((item) => item.value),
    ['overview', 'processing', 'tasks', 'system']
  )
  assert.deepEqual(
    ADMIN_SECTION_OPTIONS.map((item) => item.label),
    ['总览', '处理任务', '任务中心', '系统设置']
  )
})

test('ADMIN_SECTION_LEGACY_ALIASES should document governance migration intent', () => {
  assert.equal(ADMIN_SECTION_LEGACY_ALIASES.governance, 'processing')
})

test('ADMIN_PROCESSING_TAB_OPTIONS should expose base and ai sub-modes', () => {
  assert.deepEqual(
    ADMIN_PROCESSING_TAB_OPTIONS.map((item) => item.value),
    ['base', 'ai']
  )
  assert.deepEqual(
    ADMIN_PROCESSING_TAB_OPTIONS.map((item) => item.label),
    ['基础处理', '智能整理']
  )
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

  assert.equal(copy.badge, '基础整理可用')
  assert.match(copy.description, /关键信息整理|岗位整理|基础处理/)
  assert.match(copy.emphasis, /继续|可用/)
  assert.doesNotMatch(copy.description, /不可用|不可做|无法使用/)
  assert.doesNotMatch(copy.emphasis, /不可用|不可做|无法使用/)
})

test('getAdminRuntimeCopy should describe ai_enhanced mode as ready for AI enhancement', () => {
  const copy = getAdminRuntimeCopy({ analysis_enabled: true, openai_ready: true })

  assert.equal(copy.badge, '智能整理可用')
  assert.match(copy.description, /智能整理|岗位识别/)
  assert.match(copy.emphasis, /智能整理/)
})

test('getAdminRuntimeCopy should keep disabled mode truthful about base capability when explicitly provided', () => {
  const copy = getAdminRuntimeCopy({ mode: 'disabled', analysis_enabled: false, openai_ready: false })

  assert.equal(copy.badge, '智能整理已关闭')
  assert.match(copy.description, /基础处理|岗位整理/)
  assert.match(copy.emphasis, /仍可继续/)
})

test('getAdminRuntimeCopy should expose loading wording for unknown runtime', () => {
  const copy = getAdminRuntimeCopy({ analysis_enabled: true })

  assert.equal(copy.badge, '状态更新中')
  assert.match(copy.description, /更新|稍后刷新|能力信息/)
  assert.match(copy.emphasis, /稍后刷新|未获取完整信息/)
})
