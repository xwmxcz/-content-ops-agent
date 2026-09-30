import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { waitForJobResult } from '../src/api/jobs'

const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../src/api/index', () => ({ api }))

describe('waitForJobResult retries', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('waits for scheduled retries without reporting an intermediate failure or busy polling', async () => {
    api.get
      .mockResolvedValueOnce({ data: { status: 'failed', next_retry_at: '2026-09-29T10:00:00', error: 'temporary' } })
      .mockResolvedValueOnce({ data: { status: 'completed', result: { text: 'done' } } })
    const result = waitForJobResult('job-1', job => job.result?.text)
    await vi.advanceTimersByTimeAsync(1499)
    expect(api.get).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    await expect(result).resolves.toBe('done')
  })

  it('surfaces a final failure after retries are exhausted', async () => {
    api.get.mockResolvedValue({ data: { status: 'failed', next_retry_at: null, error: '最终失败' } })
    await expect(waitForJobResult('job-1', () => undefined)).rejects.toThrow('最终失败')
  })
})
