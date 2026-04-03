import test from 'node:test'
import assert from 'node:assert/strict'

import {
  formatAdminDurationMs,
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

test('formatAdminDurationMs should not coerce nullish durations into 0ms', () => {
  assert.equal(formatAdminDurationMs(null), '--')
  assert.equal(formatAdminDurationMs(undefined), '--')
  assert.equal(formatAdminDurationMs(''), '--')
})

test('buildDataProcessingPanels should surface live task metrics while scrape and job extraction are running', () => {
  const panels = buildDataProcessingPanels({
    sourceOptions: [{ label: '江苏省人社厅（source_id=1）', value: 1, isActive: true }],
    jobsOverview: {
      total_jobs: 18,
      posts_with_jobs: 6,
      pending_posts: 4,
      counselor_jobs: 10
    },
    taskRuns: [
      {
        task_type: 'manual_scrape',
        status: 'running',
        details: {
          metrics: {
            posts_seen: 12,
            posts_total: 30,
            posts_created: 4,
            posts_updated: 3
          }
        }
      },
      {
        task_type: 'job_extraction',
        status: 'running',
        params: { use_ai: false },
        details: {
          metrics: {
            posts_scanned: 8,
            posts_total: 20,
            posts_updated: 5,
            jobs_saved: 14
          }
        }
      }
    ]
  })

  const collectPanel = panels.find((panel) => panel.id === 'collect-and-backfill')
  const jobsPanel = panels.find((panel) => panel.id === 'job-index')

  assert.match(collectPanel.stats[0].meta[0], /进行中：本轮已处理 12\/30 条/)
  assert.match(collectPanel.stats[0].meta[0], /新增 4 条/)
  assert.match(collectPanel.stats[0].meta[0], /更新 3 条/)
  assert.match(jobsPanel.stats[0].meta[0], /进行中：本轮已检查 8\/20 条/)
  assert.match(jobsPanel.stats[0].meta[0], /写入 14 个岗位/)
})

test('buildDataProcessingPanels should format duplicate live progress as percent when metrics are percentage-based', () => {
  const panels = buildDataProcessingPanels({
    duplicateOverview: {
      duplicate_groups: 7,
      duplicate_posts: 13,
      unchecked_posts: 5
    },
    taskRuns: [
      {
        task_type: 'duplicate_backfill',
        status: 'running',
        details: {
          metrics: {
            completed: 46,
            total: 100,
            groups: 3,
            duplicates: 6
          }
        }
      }
    ]
  })

  const duplicatePanel = panels.find((panel) => panel.id === 'duplicate-governance')

  assert.match(duplicatePanel.stats[0].meta[0], /进行中：本轮已完成 46%/)
  assert.doesNotMatch(duplicatePanel.stats[0].meta[0], /46\/100 %/)
})

test('buildDataProcessingPanels should surface duplicate comparison detail while duplicate checks are running', () => {
  const panels = buildDataProcessingPanels({
    duplicateOverview: {
      duplicate_groups: 7,
      duplicate_posts: 13,
      unchecked_posts: 5
    },
    taskRuns: [
      {
        task_type: 'duplicate_backfill',
        status: 'running',
        details: {
          metrics: {
            completed: 46,
            total: 100,
            unit: 'percent',
            candidate_posts: 42,
            compared_pairs: 120,
            total_comparisons: 300,
            groups: 3,
            duplicates: 6
          }
        }
      }
    ]
  })

  const duplicatePanel = panels.find((panel) => panel.id === 'duplicate-governance')

  assert.match(duplicatePanel.stats[0].meta[0], /进行中：本轮已比对 120\/300 组候选/)
  assert.match(duplicatePanel.stats[0].meta[0], /候选 42 条/)
  assert.match(duplicatePanel.stats[0].meta[0], /发现 3 个重复组/)
})

test('buildAiEnhancementPanels should mark panels disabled when OpenAI is not ready', () => {
  const panels = buildAiEnhancementPanels({
    openaiReady: false,
    disabledReason: '智能整理当前不可用，基础处理仍可继续。',
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
  assert.match(panels[2].disabledReason, /智能整理当前不可用/)
})

test('buildAiEnhancementPanels should expose readiness wording on the first card', () => {
  const panels = buildAiEnhancementPanels({
    openaiReady: false,
    disabledReason: '智能整理暂时不可用，基础处理仍可继续。',
    analysisRuntime: {
      analysis_enabled: true,
      openai_ready: false
    }
  })

  assert.equal(panels[0].title, '当前可用能力')
  assert.equal(panels[0].value, '未就绪')
  assert.match(panels[0].helper, /基础处理|智能整理/)
})

test('buildAiEnhancementPanels should show live metrics while ai tasks are running', () => {
  const panels = buildAiEnhancementPanels({
    openaiReady: true,
    analysisRuntime: {
      analysis_enabled: true,
      openai_ready: true,
      model_name: 'gpt-5.4'
    },
    analysisOverview: {
      total_posts: 20,
      openai_analyzed_posts: 8,
      openai_pending_posts: 12
    },
    jobsOverview: {
      posts_with_jobs: 10,
      ai_job_posts: 2,
      attachment_job_posts: 4
    },
    taskRuns: [
      {
        task_type: 'ai_analysis',
        status: 'running',
        details: {
          metrics: {
            posts_scanned: 9,
            posts_total: 20,
            success_count: 5,
            insight_success_count: 4
          }
        }
      },
      {
        task_type: 'job_extraction',
        status: 'running',
        params: { use_ai: true },
        details: {
          metrics: {
            posts_scanned: 6,
            posts_total: 10,
            ai_posts: 3,
            jobs_saved: 11
          }
        }
      }
    ]
  })

  assert.match(String(panels[2].meta), /进行中：本轮已处理 9\/20 条/)
  assert.match(String(panels[2].meta), /AI 成功 5 条/)
  assert.match(String(panels[3].meta), /进行中：本轮已检查 6\/10 条/)
  assert.match(String(panels[3].meta), /AI 参与 3 条/)
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

  assert.equal(panels[1].title, '当前模型')
  assert.equal(panels[1].value, 'gpt-5.4')
  assert.doesNotMatch(panels[1].helper, /provider/i)
  assert.doesNotMatch(panels[1].meta, /接口|https?:\/\//)
})

test('buildTaskRunsPresentation should separate current tasks, recent results, and history', () => {
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
    ['当前任务', '未完成', '已完成', '历史记录']
  )
  assert.deepEqual(
    presentation.currentRuns.map((run) => run.id),
    ['running-1']
  )
  assert.deepEqual(
    presentation.recentResultRuns.map((run) => run.id),
    ['failed-1', 'success-1', 'success-2', 'success-3']
  )
  assert.deepEqual(
    presentation.historyRuns.map((run) => run.id),
    ['success-4']
  )
  assert.equal(presentation.counts.current, 1)
  assert.equal(presentation.counts.failed, 1)
  assert.equal(presentation.counts.success, 4)
  assert.equal(presentation.counts.results, 5)
  assert.match(presentation.summaryCards[0].description, /排队|处理/)
  assert.match(String(presentation.summaryCards[1].meta), /1 条未完成/)
})

test('buildTaskRunsPresentation should include cancelled runs inside recent results', () => {
  const presentation = buildTaskRunsPresentation({
    nowTs: Date.parse('2026-04-01T10:20:00Z'),
    heartbeatStaleMs: 10 * 60 * 1000,
    taskRuns: [
      { id: 'running-1', task_type: 'manual_scrape', status: 'running', heartbeat_at: '2026-04-01T10:18:00Z' },
      { id: 'cancelled-1', task_type: 'ai_analysis', status: 'cancelled', finished_at: '2026-04-01T10:10:00Z' },
      { id: 'success-1', task_type: 'attachment_backfill', status: 'success', finished_at: '2026-04-01T09:50:00Z' }
    ]
  })

  assert.deepEqual(
    presentation.recentResultRuns.map((run) => run.id),
    ['cancelled-1', 'success-1']
  )
  assert.equal(presentation.counts.cancelled, 1)
})

test('buildTaskRunsPresentation should keep all active runs out of history even when there are more than four', () => {
  const presentation = buildTaskRunsPresentation({
    nowTs: Date.parse('2026-04-01T10:20:00Z'),
    heartbeatStaleMs: 10 * 60 * 1000,
    taskRuns: [
      { id: 'running-1', task_type: 'manual_scrape', status: 'running', heartbeat_at: '2026-04-01T10:18:00Z' },
      { id: 'running-2', task_type: 'ai_analysis', status: 'running', heartbeat_at: '2026-04-01T10:18:00Z' },
      { id: 'running-3', task_type: 'job_extraction', status: 'running', heartbeat_at: '2026-04-01T10:18:00Z' },
      { id: 'running-4', task_type: 'duplicate_backfill', status: 'running', heartbeat_at: '2026-04-01T10:18:00Z' },
      { id: 'running-5', task_type: 'attachment_backfill', status: 'pending', heartbeat_at: '2026-04-01T10:18:00Z' },
      { id: 'success-1', task_type: 'attachment_backfill', status: 'success', finished_at: '2026-04-01T09:50:00Z' }
    ]
  })

  assert.deepEqual(
    presentation.currentRuns.map((run) => run.id),
    ['running-1', 'running-2', 'running-3', 'running-4', 'running-5']
  )
  assert.deepEqual(
    presentation.historyRuns.map((run) => run.id),
    []
  )
})
