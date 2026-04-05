import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import { postsApi } from '../src/api/posts.js'
import { usePostListState } from '../src/views/post-list/usePostListState.js'

const readSource = (relativePath) => readFileSync(new URL(`../src/${relativePath}`, import.meta.url), 'utf8')

test('public post list shell should not expose admin-only guidance', () => {
  const source = readSource('views/PostList.vue')

  assert.match(source, /AppPageHeader/)
  assert.doesNotMatch(source, /前台只看结果，运维动作请走管理台/)
  assert.doesNotMatch(source, /统计口径已跟当前搜索和筛选同步/)
  assert.doesNotMatch(source, /岗位快照：/)
  assert.doesNotMatch(source, /搜索招聘信息/)
  assert.doesNotMatch(source, /管理台/)
})

test('public post list should avoid implementation-heavy copy in the first screen', () => {
  const source = readSource('views/PostList.vue')

  assert.match(source, /postListPresentation/)
  assert.match(source, /AppMetricPill/)
  assert.match(source, /app-surface app-surface--padding-md/)
  assert.match(source, /aria-controls="post-advanced-filters"/)
  assert.match(source, /aria-label="结果分页"/)
  assert.match(source, /focus-visible:ring-2/)
  assert.match(source, /lg:grid-cols-\[minmax\(0,1\.5fr\)_220px_280px\]/)
  assert.match(source, /lg:justify-end lg:self-end/)
  assert.doesNotMatch(source, /AppStatCard/)
  assert.doesNotMatch(source, /post\.analysis\?\.summary/)
  assert.doesNotMatch(source, /school_name/)
})

test('not found page should guide users back to browsing instead of exposing route checks', () => {
  const source = readSource('views/NotFoundView.vue')

  assert.match(source, /AppPageHeader/)
  assert.doesNotMatch(source, /检查路由配置/)
  assert.doesNotMatch(source, /进入管理台/)
})

test('PostList freshness notice should keep AppNotice bindings and helper wiring complete', () => {
  const source = readSource('views/PostList.vue')

  assert.match(source, /<AppNotice[\s\S]*:tone="freshnessNotice\.tone"[\s\S]*:title="freshnessNotice\.title"[\s\S]*:description="freshnessNotice\.description"[\s\S]*\/>/)

  assert.match(source, /const freshnessNotice = computed\(\(\) => buildPostListFreshnessNotice\(\s*\{[\s\S]*\}\)\)/)
  assert.match(source, /loading:\s*freshnessLoading\.value/)
  assert.match(source, /latestSuccessTask:\s*latestSuccessTask\.value/)
  assert.match(source, /unavailable:\s*freshnessUnavailable\.value/)
  assert.match(source, /freshnessHeadline:\s*freshnessHeadline\.value/)
  assert.match(source, /formatDateTime\b/)
  assert.match(source, /formatRelativeTime:\s*getRelativeTimeLabel/)
})

test('PostList error notice should expose multiple recovery actions and announce dynamically', () => {
  const source = readSource('views/PostList.vue')

  assert.match(source, /<AppNotice[\s\S]*v-else-if="error"[\s\S]*announce/)
  assert.match(source, /title="招聘列表暂时无法显示"/)
  assert.match(source, /v-if="currentPage > 1"/)
  assert.match(source, />\s*返回上一页\s*</)
  assert.match(source, />\s*回到第一页\s*</)
  assert.match(source, /v-if="hasQueryOrFilters"/)
  assert.match(source, />\s*清空条件\s*</)
  assert.match(source, />\s*重新加载\s*</)
})

test('PostList event type option fetch should ignore current selection in stats params but preserve selected option locally', () => {
  const source = readSource('views/post-list/usePostListState.js')

  assert.match(source, /buildEventTypeOptionParams as buildEventTypeOptionRequestParams/)
  assert.match(source, /postsApi\.getStatsSummary\(buildEventTypeOptionParams\(\)\)/)
  assert.match(source, /const selectedEventType = filters\.value\.eventType/)
  assert.match(source, /selectedEventType && !nextOptions\.some\(\(item\) => item\.event_type === selectedEventType\)/)
  assert.match(source, /nextOptions = \[\{ event_type: selectedEventType \}, \.\.\.nextOptions\]/)
})

test('usePostListState should surface recovery notice when a requested page exceeds available pages', async () => {
  const originalGetPosts = postsApi.getPosts
  const originalWarn = console.warn
  const originalWindow = globalThis.window
  const replaceCalls = []

  postsApi.getPosts = async () => ({
    data: {
      items: [],
      total: 3
    }
  })
  console.warn = () => {}
  globalThis.window = { scrollTo: () => {} }

  try {
    const state = usePostListState(
      { query: {} },
      {
        replace: async (payload) => {
          replaceCalls.push(payload)
        }
      }
    )

    await state.goToPage(9, { force: true })

    assert.equal(state.currentPage.value, 9)
    assert.equal(state.totalPages.value, 1)
    assert.equal(state.posts.value.length, 0)
    assert.equal(state.error.value, '当前页码没有对应结果，可以返回上一页继续浏览。')
    assert.equal(replaceCalls.length, 1)
  } finally {
    postsApi.getPosts = originalGetPosts
    console.warn = originalWarn
    if (originalWindow === undefined) {
      delete globalThis.window
    } else {
      globalThis.window = originalWindow
    }
  }
})

test('PostDetail freshness copy should use latest-success snapshot semantics', () => {
  const source = readSource('views/PostDetail.vue')

  assert.match(source, /return '正在读取最近抓取记录。'/)
  assert.match(source, /return `\$\{freshnessHeadline\.value\}于 \$\{formatDateTime\(latestSuccessTask\.value\.finishedAt\)\}（\$\{getRelativeTimeLabel\(latestSuccessTask\.value\.finishedAt\)\}）。`/)
})

test('PostDetail state should request source-scoped freshness after loading the current post', () => {
  const source = readSource('views/post-detail/usePostDetailState.js')

  assert.match(source, /postsApi\.getFreshnessSummary\(\s*sourceId \? \{ source_id: sourceId \} : \{\}\s*\)/)
})

test('public freshness paths should not contain outdated realtime wording', () => {
  const postListSource = readSource('views/PostList.vue')
  const postListPresentationSource = readSource('utils/postListPresentation.js')
  const postDetailSource = readSource('views/PostDetail.vue')

  assert.doesNotMatch(postListSource, /正在更新最近抓取记录/)
  assert.doesNotMatch(postListSource, /最近内容已更新/)
  assert.doesNotMatch(postListPresentationSource, /正在更新最近抓取记录/)
  assert.doesNotMatch(postListPresentationSource, /最近内容已更新/)
  assert.doesNotMatch(postDetailSource, /正在更新最近抓取记录/)
  assert.doesNotMatch(postDetailSource, /最近内容已更新/)
})
