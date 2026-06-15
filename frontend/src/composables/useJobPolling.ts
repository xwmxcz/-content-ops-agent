import { getJob, type JobResponse } from '../api/jobs'

export interface JobPollingOptions<T> {
  extract(job: JobResponse): T | undefined
  onUpdate?: (job: JobResponse) => void
  intervalMs?: number
  timeoutMs?: number
}

export function useJobPolling() {
  let aborted = false

  function abort() {
    aborted = true
  }

  function reset() {
    aborted = false
  }

  function isAborted() {
    return aborted
  }

  async function poll<T>(jobId: string, options: JobPollingOptions<T>): Promise<T> {
    const timeoutMs = options.timeoutMs ?? 360000
    const intervalMs = options.intervalMs ?? 1500
    const started = Date.now()

    while (Date.now() - started < timeoutMs) {
      if (aborted) throw new Error('已停止')

      const job = await getJob(jobId)
      options.onUpdate?.(job)

      if (job.status === 'completed') {
        const result = options.extract(job)
        if (result === undefined) throw new Error('任务已完成，但结果为空')
        return result
      }
      if (job.status === 'failed') {
        throw new Error(job.error || '任务执行失败')
      }
      if (job.status === 'cancelled') {
        throw new Error(job.error || '任务已取消')
      }

      await sleep(intervalMs)
    }

    throw new Error('任务等待超时')
  }

  return {
    abort,
    isAborted,
    poll,
    reset
  }
}

function sleep(ms: number) {
  return new Promise(resolve => window.setTimeout(resolve, ms))
}
