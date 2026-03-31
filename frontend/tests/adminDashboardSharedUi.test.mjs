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

test('admin data processing section should pass live stat descriptions and meta into shared stat cards', () => {
  const source = readSource('views/admin/sections/AdminDataProcessingSection.vue')

  assert.match(source, /:description="item\.description"/)
  assert.match(source, /:meta="item\.meta"/)
})
