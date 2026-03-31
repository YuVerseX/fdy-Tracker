import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const readSource = (relativePath) => readFileSync(new URL(`../src/${relativePath}`, import.meta.url), 'utf8')

test('admin sections should use shared stat card and action button primitives', () => {
  const sources = [
    readSource('views/admin/sections/AdminOverviewSection.vue'),
    readSource('views/admin/sections/AdminDataProcessingSection.vue'),
    readSource('views/admin/sections/AdminAiEnhancementSection.vue'),
    readSource('views/admin/sections/AdminTaskRunsSection.vue'),
    readSource('views/admin/sections/AdminSystemSection.vue')
  ]

  const combined = sources.join('\n')

  assert.match(combined, /AppStatCard/)
  assert.match(combined, /AppActionButton/)
})

test('admin overview, processing, ai, and system sections should use compact summary primitives', () => {
  const overviewSource = readSource('views/admin/sections/AdminOverviewSection.vue')
  const processingSource = readSource('views/admin/sections/AdminDataProcessingSection.vue')
  const aiSource = readSource('views/admin/sections/AdminAiEnhancementSection.vue')
  const systemSource = readSource('views/admin/sections/AdminSystemSection.vue')

  assert.match(overviewSource, /AppMetricPill/)
  assert.match(overviewSource, /AppFactList/)
  assert.match(processingSource, /AppMetricPill/)
  assert.match(aiSource, /AppMetricPill/)
  assert.match(systemSource, /AppMetricPill/)
  assert.match(systemSource, /AppFactList/)
})

test('admin data processing section should render compact metric pills and preserve summary context', () => {
  const source = readSource('views/admin/sections/AdminDataProcessingSection.vue')

  assert.match(source, /AppMetricPill/)
  assert.match(source, /item\.label/)
  assert.match(source, /item\.value/)
  assert.match(source, /item\.description/)
  assert.match(source, /item\.meta/)
})

test('admin processing sections should switch to denser medium breakpoint layouts before desktop xl', () => {
  const processingSource = readSource('views/admin/sections/AdminDataProcessingSection.vue')
  const aiSource = readSource('views/admin/sections/AdminAiEnhancementSection.vue')
  const sectionHeaderSource = readSource('components/ui/AppSectionHeader.vue')

  assert.match(processingSource, /md:flex-row/)
  assert.match(processingSource, /md:grid-cols-2/)
  assert.match(processingSource, /lg:grid-cols-2/)
  assert.match(aiSource, /md:flex-row/)
  assert.match(aiSource, /md:grid-cols-2/)
  assert.match(aiSource, /lg:grid-cols-2/)
  assert.match(sectionHeaderSource, /md:text-right/)
  assert.match(sectionHeaderSource, /md:max-w-xs/)
})

test('admin system section should keep long scheduler fields readable at medium breakpoints', () => {
  const systemSource = readSource('views/admin/sections/AdminSystemSection.vue')

  assert.match(systemSource, /md:flex-row/)
  assert.match(systemSource, /md:shrink-0/)
  assert.match(systemSource, /md:grid-cols-2/)
  assert.match(systemSource, /xl:grid-cols-4/)
  assert.match(systemSource, /md:col-span-2 xl:col-span-2/)
  assert.match(systemSource, /md:col-span-2 xl:col-span-4/)
})

test('shared metric pill should support semantic tones for status summaries', () => {
  const source = readSource('components/ui/AppMetricPill.vue')
  const styles = readSource('style.css')

  assert.match(source, /info:/)
  assert.match(source, /success:/)
  assert.match(source, /warning:/)
  assert.match(source, /danger:/)
  assert.match(styles, /app-pill--info/)
  assert.match(styles, /app-pill--success/)
  assert.match(styles, /app-pill--warning/)
  assert.match(styles, /app-pill--danger/)
})

test('shared disclosure and tab navigation should expose visible, stateful accessibility cues', () => {
  const disclosureSource = readSource('components/ui/AppDisclosure.vue')
  const tabsSource = readSource('components/ui/AppTabNav.vue')

  assert.match(disclosureSource, /@toggle=/)
  assert.match(disclosureSource, /isOpen \? collapseLabel : expandLabel/)
  assert.match(disclosureSource, /aria-expanded/)
  assert.match(disclosureSource, /aria-controls/)
  assert.match(tabsSource, /focus-visible:outline-none/)
  assert.match(tabsSource, /focus-visible:ring-2/)
  assert.match(tabsSource, /overflow-x-auto/)
  assert.match(tabsSource, /whitespace-nowrap/)
})
