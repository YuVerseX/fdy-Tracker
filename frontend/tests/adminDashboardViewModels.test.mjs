import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildAiEnhancementPanels,
  buildDataProcessingPanels,
  buildTaskRunsPresentation
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

  assert.equal(panels[0].title, '当前运行模式')
  assert.equal(panels[0].value, '未就绪')
  assert.match(panels[0].helper, /规则分析|基础处理/)
})

test('buildAiEnhancementPanels should avoid exposing provider and base url details', () => {
  const panels = buildAiEnhancementPanels({
    openaiReady: true,
    analysisRuntime: {
      analysis_enabled: true,
      openai_ready: true,
      model_name: 'gpt-5.4',
      provider: 'openai',
      base_url: 'https://example.invalid'
    }
  })

  assert.equal(panels[1].title, '增强模型')
  assert.equal(panels[1].value, 'gpt-5.4')
  assert.doesNotMatch(panels[1].helper, /provider/i)
  assert.doesNotMatch(panels[1].meta, /接口|https?:\/\//)
})

test('buildTaskRunsPresentation should prioritize attention runs and fold the rest into history', () => {
  const presentation = buildTaskRunsPresentation({
    nowTs: Date.parse('2026-03-30T10:20:00Z'),
    heartbeatStaleMs: 10 * 60 * 1000,
    taskRuns: [
      { id: 'failed-1', task_type: 'ai_analysis', status: 'failed', started_at: '2026-03-30T10:00:00Z', finished_at: '2026-03-30T10:01:00Z' },
      { id: 'running-1', task_type: 'manual_scrape', status: 'running', started_at: '2026-03-30T10:00:00Z', heartbeat_at: '2026-03-30T10:18:00Z' },
      { id: 'success-1', task_type: 'base_analysis_backfill', status: 'success', started_at: '2026-03-30T09:00:00Z', finished_at: '2026-03-30T09:05:00Z' },
      { id: 'success-2', task_type: 'job_extraction', status: 'success', started_at: '2026-03-30T08:00:00Z', finished_at: '2026-03-30T08:10:00Z' },
      { id: 'success-3', task_type: 'attachment_backfill', status: 'success', started_at: '2026-03-30T07:00:00Z', finished_at: '2026-03-30T07:20:00Z' },
      { id: 'success-4', task_type: 'duplicate_backfill', status: 'success', started_at: '2026-03-30T06:00:00Z', finished_at: '2026-03-30T06:12:00Z' }
    ]
  })

  assert.deepEqual(
    presentation.summaryCards.map((card) => card.label),
    ['需关注', '运行中', '最近完成', '历史记录']
  )
  assert.deepEqual(
    presentation.attentionRuns.map((run) => run.id),
    ['failed-1', 'running-1']
  )
  assert.deepEqual(
    presentation.recentSuccessRuns.map((run) => run.id),
    ['success-1', 'success-2', 'success-3']
  )
  assert.deepEqual(
    presentation.historyRuns.map((run) => run.id),
    ['success-4']
  )
  assert.equal(presentation.counts.attention, 2)
  assert.equal(presentation.counts.running, 1)
  assert.equal(presentation.counts.success, 4)
})
