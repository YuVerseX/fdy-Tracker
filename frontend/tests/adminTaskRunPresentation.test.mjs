import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildTaskRunCardPresentation,
  buildTaskDetailSections,
  buildTaskMetricItems,
  buildTaskProgressView
} from '../src/views/admin/adminTaskRunPresentation.js'

test('buildTaskProgressView should keep stage_only runs truthful about phase progress', () => {
  const view = buildTaskProgressView({
    task_type: 'manual_scrape',
    status: 'running',
    stage_label: '正在抓取源站并写入数据库',
    progress_mode: 'stage_only',
    progress: 55,
    metrics: {
      posts_seen: 18,
      posts_created: 8,
      posts_updated: 4
    }
  }, {
    nowTs: Date.parse('2026-03-31T10:20:00Z'),
    heartbeatStaleMs: 10 * 60 * 1000
  })

  assert.equal(view.mode, 'stage_only')
  assert.equal(view.showProgressBar, false)
  assert.equal(view.modeLabel, '按阶段更新')
  assert.equal(view.progressLabel, '按阶段推进')
  assert.equal(view.progressPercentLabel, '')
  assert.equal(view.stageLabel, '正在抓取源站并写入数据库')
})

test('buildTaskProgressView should summarize processed counts for stage_only runs when totals are available', () => {
  const view = buildTaskProgressView({
    task_type: 'job_extraction',
    status: 'running',
    stage_label: '正在抽取岗位数据',
    progress_mode: 'stage_only',
    metrics: {
      posts_scanned: 8,
      posts_total: 20,
      jobs_saved: 14
    }
  }, {
    nowTs: Date.parse('2026-03-31T10:20:00Z'),
    heartbeatStaleMs: 10 * 60 * 1000
  })

  assert.equal(view.showProgressBar, false)
  assert.equal(view.modeLabel, '按阶段更新')
  assert.equal(view.progressLabel, '已检查 8 / 20 条公告')
  assert.equal(view.progressPercentLabel, '')
})

test('buildTaskProgressView should summarize duplicate comparison progress when detailed metrics are available', () => {
  const view = buildTaskProgressView({
    task_type: 'duplicate_backfill',
    status: 'running',
    stage_label: '正在比对重复候选',
    progress_mode: 'stage_only',
    metrics: {
      completed: 46,
      total: 100,
      unit: 'percent',
      compared_pairs: 120,
      total_comparisons: 300
    }
  }, {
    nowTs: Date.parse('2026-03-31T10:20:00Z'),
    heartbeatStaleMs: 10 * 60 * 1000
  })

  assert.equal(view.showProgressBar, false)
  assert.equal(view.modeLabel, '按阶段更新')
  assert.equal(view.progressLabel, '已比对 120 / 300 组候选')
  assert.equal(view.progressPercentLabel, '')
})

test('buildTaskProgressView should hide estimated percent bars when determinate progress is only a stage estimate', () => {
  const view = buildTaskProgressView({
    task_type: 'duplicate_backfill',
    status: 'running',
    stage_label: '正在识别重复分组',
    progress_mode: 'determinate',
    progress: 45,
    metrics: {
      completed: 45,
      total: 100,
      unit: 'percent'
    }
  }, {
    nowTs: Date.parse('2026-03-31T10:20:00Z'),
    heartbeatStaleMs: 10 * 60 * 1000
  })

  assert.equal(view.showProgressBar, false)
  assert.equal(view.modeLabel, '阶段估算')
  assert.equal(view.progressLabel, '当前百分比仅用于提示阶段位置')
  assert.equal(view.progressPercentLabel, '约 45%')
  assert.equal(view.stageLabel, '正在识别重复分组')
})

test('buildTaskProgressView should keep determinate bars for item-based progress snapshots', () => {
  const view = buildTaskProgressView({
    task_type: 'manual_scrape',
    status: 'running',
    stage_label: '正在保存抓取结果',
    progress_mode: 'determinate',
    progress: 40,
    metrics: {
      completed: 4,
      total: 10,
      unit: '条'
    }
  }, {
    nowTs: Date.parse('2026-03-31T10:20:00Z'),
    heartbeatStaleMs: 10 * 60 * 1000
  })

  assert.equal(view.showProgressBar, true)
  assert.equal(view.modeLabel, '按完成量更新')
  assert.equal(view.progressLabel, '已处理 4 / 10 条')
  assert.equal(view.progressPercentLabel, '40%')
})

test('buildTaskMetricItems should expose user-facing metric labels in stable order', () => {
  const items = buildTaskMetricItems({
    task_type: 'manual_scrape',
    metrics: {
      posts_updated: 4,
      posts_seen: 18,
      posts_created: 8,
      failures: 1
    }
  })

  assert.deepEqual(
    items.map((item) => item.label),
    ['发现公告', '新增公告', '更新公告', '失败']
  )
  assert.deepEqual(
    items.map((item) => item.value),
    ['18', '8', '4', '1']
  )
})

test('buildTaskMetricItems should omit zero-value failure metrics from successful runs', () => {
  const items = buildTaskMetricItems({
    task_type: 'manual_scrape',
    metrics: {
      posts_seen: 18,
      posts_created: 8,
      posts_updated: 4,
      failures: 0,
      processed_records: 12
    }
  })

  assert.deepEqual(
    items.map((item) => item.label),
    ['发现公告', '新增公告', '更新公告', '处理记录']
  )
  assert.deepEqual(
    items.map((item) => item.value),
    ['18', '8', '4', '12']
  )
})

test('buildTaskMetricItems should omit percent-only fallback metrics that only represent stage estimates', () => {
  const items = buildTaskMetricItems({
    task_type: 'duplicate_backfill',
    metrics: {
      completed: 45,
      total: 100,
      unit: 'percent'
    }
  })

  assert.deepEqual(items, [])
})

test('buildTaskMetricItems should expose duplicate progress metrics in user-facing order', () => {
  const items = buildTaskMetricItems({
    task_type: 'duplicate_backfill',
    metrics: {
      selected: 20,
      candidate_posts: 42,
      compared_pairs: 120,
      total_comparisons: 300,
      processed_groups: 3,
      total_groups: 8,
      duplicates: 6
    }
  })

  assert.deepEqual(
    items.map((item) => item.label),
    ['检查公告', '待比对帖子', '已确认重复组', '重复组总数', '折叠记录', '已比对候选', '候选总对数']
  )
})

test('buildTaskDetailSections should group task facts ahead of result metrics', () => {
  const sections = buildTaskDetailSections({
    task_type: 'manual_scrape',
    started_at: '2026-03-31T09:00:00Z',
    finished_at: '2026-03-31T09:03:00Z',
    params: {
      source_id: 1,
      max_pages: 5,
      limit: 20
    },
    metrics: {
      posts_seen: 18,
      posts_created: 8,
      posts_updated: 4,
      processed_records: 12,
      posts_total: 20
    }
  }, {
    sourceOptions: [{ label: '江苏省人社厅', value: 1 }],
    nowTs: Date.parse('2026-03-31T09:05:00Z')
  })

  assert.deepEqual(
    sections.map((section) => section.title),
    ['任务信息', '处理结果']
  )
  assert.equal(sections[0].items[0].label, '开始时间')
  assert.equal(sections[0].items[3].value, '江苏省人社厅')
  assert.deepEqual(
    sections[1].items.map((item) => item.label),
    ['预计公告']
  )
})

test('buildTaskRunCardPresentation should expose canonical stage timeline items', () => {
  const card = buildTaskRunCardPresentation({
    id: 'run-manual-1',
    task_type: 'manual_scrape',
    status: 'running',
    stage: 'persisting',
    stage_label: '正在写入抓取结果',
    stage_started_at: '2026-03-31T09:02:00Z',
    started_at: '2026-03-31T09:00:00Z',
    heartbeat_at: '2026-03-31T09:04:00Z',
    summary: '本轮正在更新最新公告。',
    live_metrics: {
      posts_seen: 18,
      posts_total: 20,
      posts_created: 8,
      posts_updated: 4
    }
  }, {
    nowTs: Date.parse('2026-03-31T09:05:00Z'),
    heartbeatStaleMs: 10 * 60 * 1000
  })

  assert.equal(card.stageTitle, '当前阶段')
  assert.equal(card.resultTitle, '当前结果')
  assert.deepEqual(
    card.stageTimelineItems.map((item) => [item.key, item.state]),
    [
      ['submitted', 'done'],
      ['collecting', 'done'],
      ['persisting', 'current'],
      ['finalizing', 'upcoming']
    ]
  )
  assert.deepEqual(
    card.stageFacts.map((item) => item.label),
    ['最近更新', '已运行']
  )
  assert.deepEqual(
    card.resultItems.map((item) => item.label),
    ['发现公告', '新增公告', '更新公告']
  )
  assert.equal(card.failureNotice, null)
})

test('buildTaskRunCardPresentation should map raw stage keys into canonical timeline stages', () => {
  const card = buildTaskRunCardPresentation({
    task_type: 'attachment_backfill',
    status: 'running',
    stage: 'persist-attachments',
    stage_key: 'persist-attachments',
    stage_label: '正在补处理历史附件',
    live_metrics: {
      posts_scanned: 3,
      posts_updated: 1
    }
  })

  assert.deepEqual(
    card.stageTimelineItems.map((item) => [item.key, item.state]),
    [
      ['submitted', 'done'],
      ['collecting', 'done'],
      ['persisting', 'current'],
      ['finalizing', 'upcoming']
    ]
  )
})

test('buildTaskRunCardPresentation should show collecting-state result copy when no live result metrics exist yet', () => {
  const card = buildTaskRunCardPresentation({
    task_type: 'manual_scrape',
    status: 'running',
    stage: 'collecting',
    stage_label: '正在采集源站页面',
    summary: '正在准备抓取任务',
    live_metrics: {}
  })

  assert.equal(card.resultTitle, '当前结果')
  assert.equal(card.resultHint, '当前阶段还没有结果。')
  assert.equal(card.resultEmptyText, '当前阶段还没有结果。')
})

test('buildTaskRunCardPresentation should keep current-result copy once visible metrics exist', () => {
  const card = buildTaskRunCardPresentation({
    task_type: 'manual_scrape',
    status: 'running',
    stage: 'persisting',
    stage_label: '正在整理抓取结果',
    live_metrics: {
      posts_seen: 18,
      posts_created: 8,
      posts_updated: 4
    }
  })

  assert.equal(card.resultTitle, '当前结果')
  assert.equal(card.resultEmptyText, '')
})

test('buildTaskRunCardPresentation should keep queued scrape runs on pre-start result copy', () => {
  const card = buildTaskRunCardPresentation({
    task_type: 'manual_scrape',
    status: 'queued',
    stage_label: '等待开始抓取',
    metrics: {}
  })

  assert.equal(card.resultTitle, '当前结果')
  assert.equal(card.resultHint, '开始处理后，会逐步更新可核对的结果数量。')
  assert.equal(card.resultEmptyText, '开始处理后，会逐步出现可核对的结果数量。')
})

test('buildTaskRunCardPresentation should stop implying live result changes when a task is stuck', () => {
  const card = buildTaskRunCardPresentation({
    task_type: 'manual_scrape',
    status: 'running',
    stage_label: '正在抓取源站',
    heartbeat_at: '2026-03-31T09:00:00Z',
    metrics: {
      posts_seen: 18,
      posts_created: 8
    }
  }, {
    nowTs: Date.parse('2026-03-31T09:20:01Z'),
    heartbeatStaleMs: 10 * 60 * 1000
  })

  assert.equal(card.statusLabel, '进度停滞')
  assert.equal(card.resultHint, '结果暂未继续更新，请先刷新状态确认任务是否仍在处理。')
})

test('buildTaskRunCardPresentation should expose failure reason and action summary for failed tasks', () => {
  const card = buildTaskRunCardPresentation({
    id: 'run-ai-1',
    task_type: 'ai_analysis',
    status: 'failed',
    stage: '',
    stage_label: '处理失败',
    started_at: '2026-03-31T09:00:00Z',
    finished_at: '2026-03-31T09:02:00Z',
    failure_reason: '智能服务暂时不可用，请稍后再试。',
    final_metrics: {
      posts_scanned: 8,
      success_count: 5,
      failure_count: 3
    }
  }, {
    nowTs: Date.parse('2026-03-31T09:05:00Z'),
    heartbeatStaleMs: 10 * 60 * 1000
  })

  assert.equal(card.stageTitle, '未完成位置')
  assert.equal(card.resultTitle, '本次结果')
  assert.equal(card.failureNotice.title, '这次处理未完成')
  assert.match(card.failureNotice.description, /智能服务暂时不可用/)
  assert.equal(card.actionSummary, null)
  assert.deepEqual(card.actionItems.map((item) => item.key), ['retry'])
  assert.equal(card.stageTimelineItems.find((item) => item.key === 'finalizing')?.state, 'failed')
  assert.equal(card.stageTimelineItems.find((item) => item.key === 'finalizing')?.label, '处理失败')
  assert.match(card.timelineText, /^失败于 /)
  assert.deepEqual(
    card.stageFacts.map((item) => item.label),
    ['失败时间', '耗时']
  )
  assert.deepEqual(
    card.resultItems.map((item) => item.label),
    ['完成分析', '成功完成', '失败']
  )
})

test('buildTaskRunCardPresentation should surface cancelling notice while request is pending', () => {
  const card = buildTaskRunCardPresentation({
    task_type: 'ai_analysis',
    status: 'cancel_requested',
    summary: 'AI 分析进行中',
    stage: 'finalizing',
    details: { cancel_requested_at: '2026-04-01T10:00:00Z' }
  })

  assert.equal(card.statusLabel, '正在终止')
  assert.equal(card.cancellationNotice.title, '终止请求已提交')
  assert.equal(card.stageTimelineItems.find((item) => item.key === 'finalizing')?.label, '正在终止')
  assert.deepEqual(card.actionItems, [])
})

test('buildTaskRunCardPresentation should treat cancelled run as non-failure final state', () => {
  const card = buildTaskRunCardPresentation({
    task_type: 'job_extraction',
    status: 'cancelled',
    summary: '用户已提前终止，已处理 4 条，已写入 12 条岗位',
    final_metrics: { posts_scanned: 4, jobs_saved: 12 }
  })

  assert.equal(card.statusLabel, '已终止')
  assert.equal(card.failureNotice, null)
  assert.equal(card.cancellationNotice?.description, '已完成的结果已保留，可按当前建议操作继续处理。')
  assert.deepEqual(
    card.stageTimelineItems.map((item) => [item.key, item.state, item.label]),
    [
      ['submitted', 'done', '已提交'],
      ['collecting', 'done', '处理中'],
      ['persisting', 'done', '写入结果'],
      ['finalizing', 'cancelled', '已终止']
    ]
  )
})

test('buildTaskRunCardPresentation should prefer final status summary over stale final_summary copy', () => {
  const card = buildTaskRunCardPresentation({
    task_type: 'scheduled_scrape',
    status: 'failed',
    summary: '定时抓取进行中（状态过期，已自动结束）',
    final_summary: '定时抓取进行中'
  })

  assert.equal(card.summaryText, '定时抓取进行中（状态过期，已自动结束）')
})

test('buildTaskRunCardPresentation should use final metrics for finished runs', () => {
  const card = buildTaskRunCardPresentation({
    task_type: 'manual_scrape',
    status: 'success',
    stage: '',
    final_summary: '手动抓取完成，新增或更新 12 条记录',
    final_metrics: {
      posts_seen: 18,
      posts_created: 8,
      posts_updated: 4
    }
  })

  assert.equal(card.resultTitle, '本次结果')
  assert.deepEqual(card.resultItems.map((item) => item.label), ['发现公告', '新增公告', '更新公告'])
})
