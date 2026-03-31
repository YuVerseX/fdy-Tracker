const DEFAULT_SOURCE_LABEL = '全部数据源'

const toNumber = (value) => {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

const joinSummary = (parts = []) => parts.filter(Boolean).join(' · ')

const getSourceLabel = (sourceOptions = [], sourceId, fallback = DEFAULT_SOURCE_LABEL) => {
  if (sourceId === '' || sourceId === null || sourceId === undefined) return fallback
  const matchedSource = sourceOptions.find((source) => String(source.value) === String(sourceId))
  return matchedSource?.label || fallback
}

const getNumberLabel = (value, suffix, fallback = `-- ${suffix}`) => {
  const numeric = toNumber(value)
  return numeric === null ? fallback : `${numeric} ${suffix}`
}

const buildSelectOptions = (sourceOptions = [], { includeAll = false, allLabel = DEFAULT_SOURCE_LABEL, stringify = false } = {}) => {
  const items = sourceOptions.map((source) => ({
    label: source.label,
    value: stringify ? String(source.value) : source.value,
    disabled: source.isActive === false
  }))

  return includeAll
    ? [{ label: allLabel, value: '', disabled: false }, ...items]
    : items
}

const buildPrimaryAction = ({ label, busyLabel, busy, disabled, onClick, tone = 'solid' }) => ({
  label,
  busyLabel,
  busy: Boolean(busy),
  disabled: Boolean(disabled),
  onClick,
  tone
})

const buildSecondaryAction = ({ label, busyLabel, busy, disabled, onClick }) => ({
  label,
  busyLabel,
  busy: Boolean(busy),
  disabled: Boolean(disabled),
  onClick,
  tone: 'outline'
})

export function buildBaseProcessingGroups({
  collectPanel,
  duplicatePanel,
  analysisPanel,
  jobsPanel,
  sourceOptions = [],
  jobsSummaryUnavailable = false,
  scrapeForm,
  backfillForm,
  duplicateForm,
  baseAnalysisForm,
  jobIndexForm,
  scrapeBusy = false,
  backfillBusy = false,
  duplicateBusy = false,
  baseAnalysisBusy = false,
  jobIndexBusy = false,
  duplicateLoading = false,
  analysisLoading = false,
  jobsLoading = false,
  runScrapeTask,
  runBackfillTask,
  runDuplicateBackfillTask,
  runBaseAnalysisTask,
  runJobIndexTask,
  refreshDuplicateSummary,
  refreshAnalysisSummary,
  refreshJobSummary
} = {}) {
  return [
    {
      id: 'collect-and-backfill',
      panel: collectPanel,
      helper: '建议先更新最新公告，再决定是否补跑历史数据。',
      cards: [
        {
          id: 'scrape',
          tone: 'sky',
          badge: '建议先做',
          title: '立即抓取最新数据',
          description: '把最新公告拉进系统，新的记录会自动进入后续整理链路。',
          summary: `默认范围：${joinSummary([
            getSourceLabel(sourceOptions, scrapeForm?.sourceId, '默认数据源'),
            `抓 ${getNumberLabel(scrapeForm?.maxPages, '页', '-- 页')}`
          ])}`,
          chips: [
            `数据源：${getSourceLabel(sourceOptions, scrapeForm?.sourceId, '默认数据源')}`,
            `抓 ${getNumberLabel(scrapeForm?.maxPages, '页', '-- 页')}`
          ],
          primaryAction: buildPrimaryAction({
            label: '立即抓取最新数据',
            busyLabel: '抓取中...',
            busy: scrapeBusy,
            disabled: scrapeBusy,
            onClick: runScrapeTask
          }),
          disclosure: {
            summary: '调整抓取范围',
            hint: '只有在需要缩小范围时再展开。',
            fields: [
              {
                id: 'scrape-source',
                type: 'select',
                label: '数据源',
                model: scrapeForm,
                modelKey: 'sourceId',
                numeric: true,
                options: buildSelectOptions(sourceOptions)
              },
              {
                id: 'scrape-max-pages',
                type: 'number',
                label: '抓取页数',
                model: scrapeForm,
                modelKey: 'maxPages',
                min: 1,
                max: 20
              }
            ]
          }
        },
        {
          id: 'attachment-backfill',
          tone: 'amber',
          badge: '历史补齐',
          title: '补处理历史附件',
          description: '给历史公告补齐附件发现、下载和解析结果。',
          summary: `默认范围：${joinSummary([
            getSourceLabel(sourceOptions, backfillForm?.sourceId),
            `单次补 ${getNumberLabel(backfillForm?.limit, '条', '-- 条')}`
          ])}`,
          chips: [
            `数据源：${getSourceLabel(sourceOptions, backfillForm?.sourceId)}`,
            `单次补 ${getNumberLabel(backfillForm?.limit, '条', '-- 条')}`
          ],
          primaryAction: buildPrimaryAction({
            label: '补处理历史附件',
            busyLabel: '补处理中...',
            busy: backfillBusy,
            disabled: backfillBusy,
            onClick: runBackfillTask
          }),
          disclosure: {
            summary: '调整补处理范围',
            hint: '只在需要限制数据源或处理数量时再展开。',
            fields: [
              {
                id: 'backfill-source',
                type: 'select',
                label: '数据源',
                model: backfillForm,
                modelKey: 'sourceId',
                options: buildSelectOptions(sourceOptions, { includeAll: true, stringify: true })
              },
              {
                id: 'backfill-limit',
                type: 'number',
                label: '处理条数上限',
                model: backfillForm,
                modelKey: 'limit',
                min: 1,
                max: 1000
              }
            ]
          }
        }
      ]
    },
    {
      id: 'duplicate-governance',
      panel: duplicatePanel,
      helper: '重复检查可以按批次运行，不需要一次跑完。',
      refreshAction: buildSecondaryAction({
        label: '刷新重复摘要',
        busyLabel: '刷新中...',
        busy: duplicateLoading,
        disabled: duplicateLoading,
        onClick: refreshDuplicateSummary
      }),
      cards: [
        {
          id: 'duplicate-backfill',
          tone: 'slate',
          badge: '按需运行',
          title: '检查重复记录',
          description: '检查尚未整理的公告，并刷新重复记录结果。',
          summary: `默认范围：单次补 ${getNumberLabel(duplicateForm?.limit, '条', '-- 条')}`,
          chips: [`单次补 ${getNumberLabel(duplicateForm?.limit, '条', '-- 条')}`],
          primaryAction: buildPrimaryAction({
            label: '补齐去重检查',
            busyLabel: '补齐中...',
            busy: duplicateBusy,
            disabled: duplicateBusy,
            onClick: runDuplicateBackfillTask
          }),
          secondaryAction: buildSecondaryAction({
            label: '刷新重复摘要',
            busyLabel: '刷新中...',
            busy: duplicateLoading,
            disabled: duplicateLoading,
            onClick: refreshDuplicateSummary
          }),
          disclosure: {
            summary: '调整单次批量',
            hint: '推荐先用默认批量，确认结果后再逐步放大。',
            fields: [
              {
                id: 'duplicate-limit',
                type: 'number',
                label: '单次补齐条数',
                model: duplicateForm,
                modelKey: 'limit',
                min: 1,
                max: 2000
              }
            ]
          }
        }
      ]
    },
    {
      id: 'content-analysis',
      panel: analysisPanel,
      helper: '关键信息整理完成后，任务中心会显示更完整的阶段和统计。',
      refreshAction: buildSecondaryAction({
        label: '刷新分析摘要',
        busyLabel: '刷新中...',
        busy: analysisLoading,
        disabled: analysisLoading,
        onClick: refreshAnalysisSummary
      }),
      cards: [
        {
          id: 'base-analysis',
          tone: 'sky',
          badge: '建议随后做',
          title: '补齐关键信息整理',
          description: '补齐摘要、分类和关键信息，为后续智能整理准备基础结果。',
          summary: `默认范围：${joinSummary([
            getSourceLabel(sourceOptions, baseAnalysisForm?.sourceId),
            `单次补 ${getNumberLabel(baseAnalysisForm?.limit, '条', '-- 条')}`,
            baseAnalysisForm?.onlyPending ? '只补未整理内容' : '包含已整理内容'
          ])}`,
          chips: [
            `数据源：${getSourceLabel(sourceOptions, baseAnalysisForm?.sourceId)}`,
            `单次补 ${getNumberLabel(baseAnalysisForm?.limit, '条', '-- 条')}`,
            baseAnalysisForm?.onlyPending ? '只补未整理内容' : '包含已整理内容'
          ],
          primaryAction: buildPrimaryAction({
            label: '补齐关键信息整理',
            busyLabel: '补齐中...',
            busy: baseAnalysisBusy,
            disabled: baseAnalysisBusy,
            onClick: runBaseAnalysisTask
          }),
          secondaryAction: buildSecondaryAction({
            label: '刷新分析摘要',
            busyLabel: '刷新中...',
            busy: analysisLoading,
            disabled: analysisLoading,
            onClick: refreshAnalysisSummary
          }),
          disclosure: {
            summary: '调整分析范围',
            hint: '只在需要改数据源、批量或筛选条件时再展开。',
            fields: [
              {
                id: 'base-analysis-source',
                type: 'select',
                label: '数据源',
                model: baseAnalysisForm,
                modelKey: 'sourceId',
                options: buildSelectOptions(sourceOptions, { includeAll: true, stringify: true })
              },
              {
                id: 'base-analysis-limit',
                type: 'number',
                label: '处理条数上限',
                model: baseAnalysisForm,
                modelKey: 'limit',
                min: 1,
                max: 1000
              },
              {
                id: 'base-analysis-only-pending',
                type: 'checkbox',
                label: '只补未整理内容',
                model: baseAnalysisForm,
                modelKey: 'onlyPending'
              }
            ]
          }
        }
      ]
    },
    {
      id: 'job-index',
      panel: jobsPanel,
      helper: '岗位总数会在任务写入后更新，不需要等到所有任务都完成。',
      refreshAction: buildSecondaryAction({
        label: '刷新岗位摘要',
        busyLabel: '刷新中...',
        busy: jobsLoading,
        disabled: jobsLoading,
        onClick: refreshJobSummary
      }),
      cards: [
        {
          id: 'job-index',
          tone: 'cyan',
          badge: '按需运行',
          title: '补齐岗位整理',
          description: '从正文和附件整理岗位信息，新的岗位数量会在写入后更新到统计里。',
          summary: `默认范围：${joinSummary([
            getSourceLabel(sourceOptions, jobIndexForm?.sourceId),
            `单次补 ${getNumberLabel(jobIndexForm?.limit, '条', '-- 条')}`,
            jobIndexForm?.onlyPending ? '只补未整理内容' : '包含已整理内容'
          ])}`,
          chips: [
            `数据源：${getSourceLabel(sourceOptions, jobIndexForm?.sourceId)}`,
            `单次补 ${getNumberLabel(jobIndexForm?.limit, '条', '-- 条')}`,
            jobIndexForm?.onlyPending ? '只补未整理内容' : '包含已整理内容'
          ],
          primaryAction: buildPrimaryAction({
            label: '补齐岗位整理',
            busyLabel: '补齐中...',
            busy: jobIndexBusy,
            disabled: jobIndexBusy,
            onClick: runJobIndexTask
          }),
          secondaryAction: buildSecondaryAction({
            label: '刷新岗位摘要',
            busyLabel: '刷新中...',
            busy: jobsLoading,
            disabled: jobsLoading,
            onClick: refreshJobSummary
          }),
          disclosure: {
            summary: '调整索引范围',
            hint: '只有在需要限制处理范围时再展开。',
            fields: [
              {
                id: 'job-index-source',
                type: 'select',
                label: '数据源',
                model: jobIndexForm,
                modelKey: 'sourceId',
                options: buildSelectOptions(sourceOptions, { includeAll: true, stringify: true })
              },
              {
                id: 'job-index-limit',
                type: 'number',
                label: '处理条数上限',
                model: jobIndexForm,
                modelKey: 'limit',
                min: 1,
                max: 1000
              },
              {
                id: 'job-index-only-pending',
                type: 'checkbox',
                label: '只补未整理内容',
                model: jobIndexForm,
                modelKey: 'onlyPending'
              }
            ]
          },
          notice: jobsSummaryUnavailable
            ? {
                tone: 'warning',
                description: '岗位统计暂时无法读取，不影响继续补齐岗位信息。'
              }
            : null
        }
      ]
    }
  ]
}

export function buildAiProcessingCards({
  sourceOptions = [],
  jobsSummaryUnavailable = false,
  analysisForm,
  jobsForm,
  analysisBusy = false,
  jobsBusy = false,
  analysisLoading = false,
  jobsLoading = false,
  openaiReady = false,
  disabledReason = '',
  latestAnalysisLabel = '未获取',
  latestJobsLabel = '未获取',
  runAiAnalysisTask,
  runAiJobExtractionTask,
  refreshAnalysisSummary,
  refreshJobSummary
} = {}) {
  const runtimeNotice = openaiReady
    ? null
    : {
        tone: 'warning',
        description: disabledReason || '智能服务准备完成后，这里的任务会开放；基础处理现在仍可继续。'
      }

  return [
    {
      id: 'ai-analysis',
      tone: 'emerald',
      badge: '按需补充',
      title: '补充智能摘要整理',
      description: '适合基础整理已完成后，继续补更细的摘要、阶段判断和标签时使用。',
      summary: `默认范围：${joinSummary([
        getSourceLabel(sourceOptions, analysisForm?.sourceId),
        `最多 ${getNumberLabel(analysisForm?.limit, '条', '-- 条')}`,
        analysisForm?.onlyUnanalyzed ? '只处理未补充内容' : '允许重扫已有智能结果'
      ])}`,
      chips: [
        `数据源：${getSourceLabel(sourceOptions, analysisForm?.sourceId)}`,
        `最多 ${getNumberLabel(analysisForm?.limit, '条', '-- 条')}`,
        analysisForm?.onlyUnanalyzed ? '只处理未补充内容' : '允许重扫已有智能结果'
      ],
      primaryAction: buildPrimaryAction({
        label: '补充智能摘要整理',
        busyLabel: '整理中...',
        busy: analysisBusy,
        disabled: analysisBusy || !openaiReady,
        onClick: runAiAnalysisTask
      }),
      secondaryAction: buildSecondaryAction({
        label: '刷新分析摘要',
        busyLabel: '刷新中...',
        busy: analysisLoading,
        disabled: analysisLoading,
        onClick: refreshAnalysisSummary
      }),
      disclosure: {
        summary: '调整整理范围',
        hint: '只有在需要改数据源、批量或放宽筛选时再展开。',
        fields: [
          {
            id: 'ai-analysis-source',
            type: 'select',
            label: '数据源',
            model: analysisForm,
            modelKey: 'sourceId',
            options: buildSelectOptions(sourceOptions, { includeAll: true, stringify: true })
          },
          {
            id: 'ai-analysis-limit',
            type: 'number',
            label: '处理条数上限',
            model: analysisForm,
            modelKey: 'limit',
            min: 1,
            max: 500
          },
          {
            id: 'ai-analysis-only-unanalyzed',
            type: 'checkbox',
            label: '只处理未补充内容',
            model: analysisForm,
            modelKey: 'onlyUnanalyzed'
          }
        ]
      },
      notice: runtimeNotice,
      footer: `最近智能摘要整理时间：${latestAnalysisLabel || '未获取'}`
    },
    {
      id: 'ai-job-extraction',
      tone: 'cyan',
      badge: '按需补充',
      title: '补充智能岗位识别',
      description: '适合岗位已经整理过一轮，但还需要补更复杂的岗位识别时使用。',
      summary: `默认范围：${joinSummary([
        getSourceLabel(sourceOptions, jobsForm?.sourceId),
        `最多 ${getNumberLabel(jobsForm?.limit, '条', '-- 条')}`,
        jobsForm?.onlyPending ? '只补未整理内容' : '允许覆盖已有岗位结果'
      ])}`,
      chips: [
        `数据源：${getSourceLabel(sourceOptions, jobsForm?.sourceId)}`,
        `最多 ${getNumberLabel(jobsForm?.limit, '条', '-- 条')}`,
        jobsForm?.onlyPending ? '只补未整理内容' : '允许覆盖已有岗位结果'
      ],
      primaryAction: buildPrimaryAction({
        label: '补充智能岗位识别',
        busyLabel: '识别中...',
        busy: jobsBusy,
        disabled: jobsBusy || !openaiReady,
        onClick: runAiJobExtractionTask
      }),
      secondaryAction: buildSecondaryAction({
        label: '刷新岗位摘要',
        busyLabel: '刷新中...',
        busy: jobsLoading,
        disabled: jobsLoading,
        onClick: refreshJobSummary
      }),
      disclosure: {
        summary: '调整识别范围',
        hint: '只有在需要改数据源或放宽筛选时再展开。',
        fields: [
          {
            id: 'ai-job-source',
            type: 'select',
            label: '数据源',
            model: jobsForm,
            modelKey: 'sourceId',
            options: buildSelectOptions(sourceOptions, { includeAll: true, stringify: true })
          },
          {
            id: 'ai-job-limit',
            type: 'number',
            label: '处理条数上限',
            model: jobsForm,
            modelKey: 'limit',
            min: 1,
            max: 1000
          },
          {
            id: 'ai-job-only-pending',
            type: 'checkbox',
            label: '只补未整理内容',
            model: jobsForm,
            modelKey: 'onlyPending'
          }
        ]
      },
      notice: jobsSummaryUnavailable
        ? {
            tone: 'warning',
            description: '岗位统计暂时无法读取，不影响继续运行智能岗位识别。'
          }
        : runtimeNotice,
      footer: `最近智能岗位识别时间：${latestJobsLabel || '未获取'}`
    }
  ]
}
