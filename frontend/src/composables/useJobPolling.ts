import { getJob, type JobResponse } from '../api/jobs'
import { assertWorkspaceSession } from '../query/client'
import { workspaceSessionId } from '../workspaceSession'

export interface JobPollingOptions<T> {
  extract(job: JobResponse): T | undefined
  onUpdate?: (job: JobResponse) => void
  intervalMs?: number
  timeoutMs?: number
}

export function useJobPolling() {
  let aborted = false
  let attempt = 0

  function abort() {
    aborted = true
    attempt += 1
  }

  function reset() {
    aborted = false
    return ++attempt
  }

  function isAborted(expectedAttempt = attempt) {
    return aborted || expectedAttempt !== attempt
  }

  async function poll<T>(jobId: string, options: JobPollingOptions<T>): Promise<T> {
    const session = workspaceSessionId.value
    const currentAttempt = attempt
    function ensureCurrent() {
      if (isAborted(currentAttempt)) throw new Error('已停止')
      assertWorkspaceSession(session)
    }
    const timeoutMs = options.timeoutMs ?? 360000
    const intervalMs = options.intervalMs ?? 1500
    const started = Date.now()

    while (Date.now() - started < timeoutMs) {
      ensureCurrent()

      const job = await getJob(jobId).catch(error => { ensureCurrent(); throw error })
      ensureCurrent()
      options.onUpdate?.(job)

      if (job.status === 'completed') {
        const result = options.extract(job)
        if (result === undefined) throw new Error('任务已完成，但结果为空')
        return result
      }
      if (job.status === 'failed' && !job.next_retry_at) {
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
