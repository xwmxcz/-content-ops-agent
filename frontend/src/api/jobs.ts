import { api } from './index'
import type { AgentRunPayload, AgentRunResponse } from './agent'
import type { ContentItem, GeneratePayload, RefinePayload } from './content'

export type JobStatus = 'queued' | 'running' | 'completed' | 'failed'
export type JobType = 'content_generation' | 'agent_run' | 'refine' | 'titles' | 'seo'

export interface JobResponse {
  id: string
  job_type: JobType
  status: JobStatus
  progress: number
  result?: Record<string, unknown> | null
  error?: string | null
  provider?: string
  model?: string
  attempts: number
  created_at?: string
  updated_at?: string
  started_at?: string
  completed_at?: string
}

export async function createContentGenerationJob(payload: GeneratePayload) {
  const { data } = await api.post<JobResponse>('/jobs/content-generation', payload)
  return data
}

export async function createAgentRunJob(payload: AgentRunPayload) {
  const { data } = await api.post<JobResponse>('/jobs/agent-run', payload)
  return data
}

export async function createRefineJob(payload: RefinePayload) {
  const { data } = await api.post<JobResponse>('/jobs/refine', payload)
  return data
}

export async function createTitlesJob(payload: Record<string, unknown>) {
  const { data } = await api.post<JobResponse>('/jobs/titles', payload)
  return data
}

export async function createSeoJob(payload: Record<string, unknown>) {
  const { data } = await api.post<JobResponse>('/jobs/seo', payload)
  return data
}

export async function getJob(jobId: string) {
  const { data } = await api.get<JobResponse>(`/jobs/${jobId}`)
  return data
}

export async function waitForJobResult<T>(
  jobId: string,
  extract: (job: JobResponse) => T | undefined,
  onUpdate?: (job: JobResponse) => void,
  timeoutMs = 360000
) {
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    const job = await getJob(jobId)
    onUpdate?.(job)
    if (job.status === 'completed') {
      const result = extract(job)
      if (result === undefined) throw new Error('任务已完成，但结果为空')
      return result
    }
    if (job.status === 'failed') {
      throw new Error(job.error || '任务执行失败')
    }
    await new Promise(resolve => window.setTimeout(resolve, 1500))
  }
  throw new Error('任务等待超时')
}

export function extractAgentRun(job: JobResponse) {
  return job.result?.agent_run as AgentRunResponse | undefined
}

export function extractContent(job: JobResponse) {
  return job.result?.content as ContentItem | undefined
}

export function extractText(job: JobResponse) {
  return job.result?.text as string | undefined
}
