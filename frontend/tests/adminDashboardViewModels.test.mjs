import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildAiEnhancementPanels,
  buildDataProcessingPanels
} from '../src/utils/adminDashboardViewModels.js'

test('buildDataProcessingPanels should keep task-oriented ids in taxonomy order', () => {
  const panels = buildDataProcessingPanels({
    sourceOptions: [{ label: '江苏省人社厅（source_id=1）', value: 1, isActive: true }]
  })

  assert.deepEqual(
    panels.map((panel) => panel.id),
    ['collect-and-backfill', 'duplicate-governance', 'content-analysis', 'job-index']
  )
})

test('buildAiEnhancementPanels should mark panels disabled when OpenAI is not ready', () => {
  const panels = buildAiEnhancementPanels({
    openaiReady: false,
    disabledReason: 'AI 增强当前不可用，基础模式仍可继续补齐。',
    analysisRuntime: {
      analysis_enabled: true,
      openai_ready: false
    },
    analysisOverview: {
      total_posts: 12,
      openai_analyzed_posts: 0,
      openai_pending_posts: 12
    },
    jobsOverview: {
      posts_with_jobs: 6,
      ai_job_posts: 0,
      pending_posts: 4
    }
  })

  assert.deepEqual(
    panels.map((panel) => panel.id),
    ['ai-runtime-status', 'ai-models', 'ai-analysis-coverage', 'ai-job-extraction-coverage']
  )
  assert.ok(panels.every((panel) => panel.disabled))
  assert.ok(panels.every((panel) => panel.disabledReason))
  assert.match(panels[2].disabledReason, /AI 增强当前不可用/)
})

test('buildAiEnhancementPanels should expose readiness wording on the first card', () => {
  const panels = buildAiEnhancementPanels({
    openaiReady: false,
    disabledReason: 'AI 增强当前不可用，基础模式仍可继续补齐。',
    analysisRuntime: {
      analysis_enabled: true,
      openai_ready: false
    }
  })

  assert.equal(panels[0].title, 'OpenAI 就绪状态')
  assert.equal(panels[0].value, '未就绪')
  assert.match(panels[0].helper, /规则分析|基础处理/)
})
