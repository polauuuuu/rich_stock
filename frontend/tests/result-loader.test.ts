import { test } from 'node:test'
import assert from 'node:assert/strict'
import { loadResult } from '../src/result-loader.ts'

test('a transient failure remains retryable and success is loaded once', async () => {
  const loaded = new Set<string>(), inflight = new Set<string>()
  let calls = 0, accepted = 0
  const fetcher = async () => { if (++calls === 1) throw new Error('temporary network failure'); return { source: 'demo' } }
  const accept = () => { accepted++; return true }
  await assert.rejects(loadResult('job', loaded, inflight, fetcher, accept))
  assert.equal(loaded.has('job'), false)
  assert.equal(inflight.size, 0)
  await loadResult('job', loaded, inflight, fetcher, accept)
  await loadResult('job', loaded, inflight, fetcher, accept)
  assert.equal(accepted, 1)
  assert.equal(calls, 2)
})

test('a stale view does not consume a result', async () => {
  const loaded = new Set<string>(), inflight = new Set<string>()
  await loadResult('job', loaded, inflight, async () => ({}), () => false)
  assert.equal(loaded.size, 0)
})
