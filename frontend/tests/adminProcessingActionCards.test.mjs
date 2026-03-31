import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildAiProcessingCards,
  buildBaseProcessingGroups
} from '../src/views/admin/adminProcessingActionCards.js'

const sourceOptions = [
  { label: '江苏省人社厅', value: 1, isActive: true },
  { label: '旧数据源', value: 9, isActive: false }
]

const noop = () => {}

const createBaseGroups = (overrides = {}) => buildBaseProcessingGroups({
  collectPanel: { id: 'collect-and-backfill', title: '采集与补处理', description: '抓取新公告，并补齐历史附件。', note: '常规更新可以直接使用当前设置。', stats: [] },
  duplicatePanel: { id: 'duplicate-governance', title: '重复记录整理', description: '检查重复帖子并整理列表展示。', note: '运行后会保留更稳定的主要记录。', stats: [] },
  analysisPanel: { id: 'content-analysis', title: '关键信息整理', description: '补齐摘要、分类和关键信息。', note: '整理完成后，再决定是否追加智能整理。', stats: [] },
  jobsPanel: { id: 'job-index', title: '岗位整理', description: '从正文和附件整理岗位信息。', note: '新增岗位会在写入后陆续计入总数。', stats: [] },
  sourceOptions,
  jobsSummaryUnavailable: true,
  scrapeForm: { sourceId: 1, maxPages: 5 },
  backfillForm: { sourceId: '', limit: 100 },
  duplicateForm: { limit: 200 },
  baseAnalysisForm: { sourceId: '', limit: 100, onlyPending: true },
  jobIndexForm: { sourceId: '', limit: 100, onlyPending: true },
  scrapeBusy: false,
  backfillBusy: false,
  duplicateBusy: false,
  baseAnalysisBusy: false,
  jobIndexBusy: false,
  duplicateLoading: false,
  analysisLoading: false,
  jobsLoading: false,
  runScrapeTask: noop,
  runBackfillTask: noop,
  runDuplicateBackfillTask: noop,
  runBaseAnalysisTask: noop,
  runJobIndexTask: noop,
  refreshDuplicateSummary: noop,
  refreshAnalysisSummary: noop,
  refreshJobSummary: noop,
  ...overrides
})

test('buildBaseProcessingGroups should keep processing groups and summaries in task order', () => {
  const groups = createBaseGroups()

  assert.deepEqual(
    groups.map((group) => group.id),
    ['collect-and-backfill', 'duplicate-governance', 'content-analysis', 'job-index']
  )
  assert.equal(groups[0].cards[0].summary, '默认范围：江苏省人社厅 · 抓 5 页')
  assert.deepEqual(groups[0].cards[1].chips, ['数据源：全部数据源', '单次补 100 条'])
  assert.deepEqual(groups[2].cards[0].chips, ['数据源：全部数据源', '单次补 100 条', '只补未整理内容'])
  assert.equal(groups[3].cards[0].notice.description, '岗位统计暂时无法读取，不影响继续补齐岗位信息。')
})

test('buildAiProcessingCards should disable primary actions until AI runtime is ready', () => {
  const cards = buildAiProcessingCards({
    sourceOptions,
    jobsSummaryUnavailable: false,
    analysisForm: { sourceId: '', limit: 100, onlyUnanalyzed: true },
    jobsForm: { sourceId: '', limit: 100, onlyPending: true },
    analysisBusy: false,
    jobsBusy: false,
    analysisLoading: false,
    jobsLoading: false,
    openaiReady: false,
    disabledReason: '请先完成智能服务配置后再运行智能任务。',
    latestAnalysisLabel: '2026/03/31 09:00',
    latestJobsLabel: '未获取',
    runAiAnalysisTask: noop,
    runAiJobExtractionTask: noop,
    refreshAnalysisSummary: noop,
    refreshJobSummary: noop
  })

  assert.deepEqual(
    cards.map((card) => card.id),
    ['ai-analysis', 'ai-job-extraction']
  )
  assert.equal(cards[0].primaryAction.disabled, true)
  assert.equal(cards[0].notice.description, '请先完成智能服务配置后再运行智能任务。')
  assert.equal(cards[0].summary, '默认范围：全部数据源 · 最多 100 条 · 只处理未补充内容')
  assert.match(cards[1].footer, /最近智能岗位识别时间：未获取/)
})
