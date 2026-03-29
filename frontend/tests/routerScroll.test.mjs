import test from 'node:test'
import assert from 'node:assert/strict'

import { resolveScrollBehavior } from '../src/router/scrollBehavior.js'

test('resolveScrollBehavior should reuse saved position when available', () => {
  const saved = { left: 0, top: 860 }
  assert.deepEqual(resolveScrollBehavior({}, {}, saved), saved)
})

test('resolveScrollBehavior should reset to top on normal navigation', () => {
  assert.deepEqual(resolveScrollBehavior({}, {}, null), { left: 0, top: 0 })
})
