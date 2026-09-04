import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { JobResponse } from '../src/api/jobs'

const getJob = vi.fn()

vi.mock('../src/api/jobs', () => ({
  getJob: (jobId: string) => getJob(jobId)
}))

// Imported after the mock so the composable binds to the stub.
const { useJobPolling } = await import('../src/composables/useJobPolling')

function job(overrides: Partial<JobResponse> = {}): JobResponse {
  return {
    id: 'job-1',
    job_type: 'agent_run',
    status: 'queued',
    ...overrides
  } as JobResponse
}

describe('useJobPolling', () => {
  beforeEach(() => {
    getJob.mockReset()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('resolves with the extracted result once the job completes', async () => {
    getJob
      .mockResolvedValueOnce(job({ status: 'running' }))
      .mockResolvedValueOnce(job({ status: 'completed', result: { value: 42 } } as Partial<JobResponse>))
    const polling = useJobPolling()

    const promise = polling.poll('job-1', {
      extract: j => (j as JobResponse & { result?: { value: number } }).result?.value,
      intervalMs: 10
    })
    await vi.advanceTimersByTimeAsync(50)

    await expect(promise).resolves.toBe(42)
  })

  it('rejects when the job fails, surfacing the server error', async () => {
    getJob.mockResolvedValue(job({ status: 'failed', error: 'provider exploded' }))
    const polling = useJobPolling()

    // The rejection handler is attached before timers advance; otherwise the
    // promise rejects with nobody listening and Vitest reports it as unhandled.
    const promise = polling.poll('job-1', { extract: () => 1, intervalMs: 10 })
    const assertion = expect(promise).rejects.toThrow('provider exploded')
    await vi.advanceTimersByTimeAsync(20)

    await assertion
  })

  it('rejects when the job is cancelled', async () => {
    getJob.mockResolvedValue(job({ status: 'cancelled' }))
    const polling = useJobPolling()

    const promise = polling.poll('job-1', { extract: () => 1, intervalMs: 10 })
    const assertion = expect(promise).rejects.toThrow('任务已取消')
    await vi.advanceTimersByTimeAsync(20)

    await assertion
  })

  it('rejects a completed job whose result is empty', async () => {
    getJob.mockResolvedValue(job({ status: 'completed' }))
    const polling = useJobPolling()

    const promise = polling.poll('job-1', { extract: () => undefined, intervalMs: 10 })
    const assertion = expect(promise).rejects.toThrow('任务已完成，但结果为空')
    await vi.advanceTimersByTimeAsync(20)

    await assertion
  })

  it('stops polling once aborted', async () => {
    getJob.mockResolvedValue(job({ status: 'running' }))
    const polling = useJobPolling()

    const promise = polling.poll('job-1', { extract: () => 1, intervalMs: 10 })
    const assertion = expect(promise).rejects.toThrow('已停止')
    await vi.advanceTimersByTimeAsync(15)
    polling.abort()
    await vi.advanceTimersByTimeAsync(30)

    await assertion
    expect(polling.isAborted()).toBe(true)
  })

  it('reset clears an earlier abort so the composable is reusable', async () => {
    const polling = useJobPolling()
    polling.abort()
    expect(polling.isAborted()).toBe(true)

    polling.reset()

    expect(polling.isAborted()).toBe(false)
  })

  it('rejects once the timeout budget is spent', async () => {
    getJob.mockResolvedValue(job({ status: 'running' }))
    const polling = useJobPolling()

    const promise = polling.poll('job-1', { extract: () => 1, intervalMs: 10, timeoutMs: 40 })
    const assertion = expect(promise).rejects.toThrow('任务等待超时')
    await vi.advanceTimersByTimeAsync(200)

    await assertion
  })

  it('forwards every poll to onUpdate for progress rendering', async () => {
    const onUpdate = vi.fn()
    getJob
      .mockResolvedValueOnce(job({ status: 'running' }))
      .mockResolvedValueOnce(job({ status: 'completed', result: 'x' } as Partial<JobResponse>))
    const polling = useJobPolling()

    const promise = polling.poll('job-1', {
      extract: () => 'x',
      onUpdate,
      intervalMs: 10
    })
    await vi.advanceTimersByTimeAsync(50)
    await promise

    expect(onUpdate).toHaveBeenCalledTimes(2)
  })
})
