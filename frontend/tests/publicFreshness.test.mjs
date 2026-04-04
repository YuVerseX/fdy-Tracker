import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'

import { postsApi } from '../src/api/posts.js'
import { getPublicFreshnessHeadline } from '../src/utils/publicFreshness.js'
import { normalizeLatestSuccessTask } from '../src/utils/taskFreshness.js'
import { getPublicTaskTypeLabel } from '../src/utils/taskTypeLabels.js'
import { usePostDetailState } from '../src/views/post-detail/usePostDetailState.js'

function createDeferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

async function flushAsyncWork() {
  await Promise.resolve()
  await new Promise((resolve) => setTimeout(resolve, 0))
}

test('getPublicFreshnessHeadline should describe all-sources public scope when success exists', () => {
  assert.equal(
    getPublicFreshnessHeadline({
      taskLabel: '定时抓取',
      finishedAt: '2026-03-27T10:00:00+00:00',
      scope: 'all_sources'
    }),
    '当前公开范围最近一次成功抓取'
  )
})

test('getPublicFreshnessHeadline should describe source scope when success exists', () => {
  assert.equal(
    getPublicFreshnessHeadline({
      taskLabel: '定时抓取',
      finishedAt: '2026-03-27T10:00:00+00:00',
      scope: 'source',
      requestedSourceId: 7
    }),
    '当前数据源最近一次成功抓取'
  )
})

test('getPublicFreshnessHeadline should fallback when no success exists', () => {
  assert.equal(getPublicFreshnessHeadline(null), '最近抓取记录暂时不可用。')
})

test('getPublicTaskTypeLabel should normalize public-facing freshness copy', () => {
  assert.equal(getPublicTaskTypeLabel('manual_scrape'), '手动抓取')
  assert.equal(getPublicTaskTypeLabel('scheduled_scrape'), '定时抓取')
  assert.equal(getPublicTaskTypeLabel('job_extraction'), '岗位整理')
})

test('normalizeLatestSuccessTask should fallback to top-level latest_success_at when run payload is absent', () => {
  assert.deepEqual(
    normalizeLatestSuccessTask({
      scope: 'all_sources',
      latest_success_at: '2026-03-31T10:00:00+00:00'
    }),
    {
      scope: 'all_sources',
      requestedSourceId: null,
      sourceId: null,
      taskType: '',
      taskLabel: '',
      finishedAt: '2026-03-31T10:00:00+00:00'
    }
  )
})

test('normalizeLatestSuccessTask should preserve scope and source ids from freshness payload', () => {
  assert.deepEqual(
    normalizeLatestSuccessTask({
      scope: 'source',
      requested_source_id: 9,
      latest_success_run: {
        task_type: 'scheduled_scrape',
        task_label: '定时抓取',
        finished_at: '2026-03-31T10:00:00+00:00',
        source_id: 9
      }
    }),
    {
      scope: 'source',
      requestedSourceId: 9,
      sourceId: 9,
      taskType: 'scheduled_scrape',
      taskLabel: '定时抓取',
      finishedAt: '2026-03-31T10:00:00+00:00'
    }
  )
})

test('usePostDetailState should ignore stale freshness responses from the previous source', async (t) => {
  const detailOne = createDeferred()
  const detailTwo = createDeferred()
  const freshnessOne = createDeferred()
  const freshnessTwo = createDeferred()
  const route = reactive({ params: { id: 1 } })

  t.mock.method(postsApi, 'getPostById', async (id) => (
    Number(id) === 1 ? detailOne.promise : detailTwo.promise
  ))
  t.mock.method(postsApi, 'getFreshnessSummary', async (params = {}) => {
    if (params.source_id === 1) return freshnessOne.promise
    if (params.source_id === 2) return freshnessTwo.promise
    return { data: null }
  })

  const state = usePostDetailState(route)

  detailOne.resolve({ data: { id: 1, source: { id: 1 } } })
  await flushAsyncWork()

  route.params.id = 2
  await nextTick()
  detailTwo.resolve({ data: { id: 2, source: { id: 2 } } })
  await flushAsyncWork()

  freshnessOne.resolve({
    data: {
      scope: 'source',
      requested_source_id: 1,
      latest_success_run: {
        task_type: 'scheduled_scrape',
        task_label: '定时抓取',
        finished_at: '2026-03-31T10:00:00+00:00',
        source_id: 1
      }
    }
  })
  await flushAsyncWork()

  assert.equal(state.latestSuccessTask.value, null)

  freshnessTwo.resolve({
    data: {
      scope: 'source',
      requested_source_id: 2,
      latest_success_run: {
        task_type: 'scheduled_scrape',
        task_label: '定时抓取',
        finished_at: '2026-04-01T10:00:00+00:00',
        source_id: 2
      }
    }
  })
  await flushAsyncWork()

  assert.equal(state.post.value?.source?.id, 2)
  assert.equal(state.latestSuccessTask.value?.sourceId, 2)
  assert.equal(state.latestSuccessTask.value?.requestedSourceId, 2)
})
