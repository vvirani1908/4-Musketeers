import assert from 'node:assert/strict'
import test from 'node:test'

import { getRetryableUploads } from './uploadState.js'

test('successful and duplicate files are not retried from the same batch', () => {
  const files = [
    { id: 'success', status: 'success' },
    { id: 'duplicate', status: 'duplicate' },
    { id: 'failed', status: 'failed' },
  ]

  assert.deepEqual(getRetryableUploads(files).map((file) => file.id), ['failed'])
})

test('a successful batch has no retryable uploads on repeated submission', () => {
  const files = [
    { id: 'one', status: 'success' },
    { id: 'two', status: 'success' },
  ]

  assert.deepEqual(getRetryableUploads(files), [])
})
