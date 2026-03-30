import test from 'node:test'
import assert from 'node:assert/strict'

import { createAdminApi, LONG_RUNNING_TIMEOUT } from '../src/api/posts.js'

test('backfillBaseAnalysis should call the long-running admin endpoint with POST', async () => {
  const calls = []
  const fakeClient = {
    post(url, payload, config) {
      calls.push({ url, payload, config })
      return Promise.resolve({ data: { accepted: true } })
    }
  }
  const payload = { source_id: 3, limit: 25 }

  const api = createAdminApi(fakeClient)
  const response = await api.backfillBaseAnalysis(payload)

  assert.deepEqual(response, { data: { accepted: true } })
  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, '/api/admin/backfill-base-analysis')
  assert.deepEqual(calls[0].payload, payload)
  assert.equal(calls[0].config?.timeout, LONG_RUNNING_TIMEOUT)
})
