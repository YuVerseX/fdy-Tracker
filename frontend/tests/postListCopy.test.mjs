import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

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
