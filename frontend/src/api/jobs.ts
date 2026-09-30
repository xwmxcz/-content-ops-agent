import { api } from './index'
import { assertWorkspaceSession, contentChanged, publicationChanged } from '../query/client'
import { workspaceSessionId } from '../workspaceSession'
import type { AgentRunPayload, AgentRunResponse } from './agent'
import type { ContentItem, GeneratePayload, RefinePayload } from './content'
import type { Publication } from './publish'

export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
export type JobType = 'content_generation' | 'agent_run' | 'refine' | 'titles' | 'seo' | 'publish_xiaohongshu'

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
  max_retries?: number
  next_retry_at?: string | null
  error_type?: string | null
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
  const session = workspaceSessionId.value
  const { data } = await api.get<JobResponse>(`/jobs/${jobId}`)
  if (data.status === 'completed') {
    const publication = extractPublication(data)
    const content = extractContent(data)
    const agent = extractAgentRun(data)
    if (publication) publicationChanged(session, publication.content_id)
    else if (content || agent?.saved_content_id) contentChanged(session, content?.id ?? agent?.saved_content_id)
  }
  return data
}

export async function cancelJob(jobId: string) {
  const { data } = await api.delete<JobResponse>(`/jobs/${jobId}`)
  return data
}

export async function waitForJobResult<T>(
  jobId: string,
  extract: (job: JobResponse) => T | undefined,
  onUpdate?: (job: JobResponse) => void,
  timeoutMs = 360000
) {
  const session = workspaceSessionId.value
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    assertWorkspaceSession(session)
    const job = await getJob(jobId)
    assertWorkspaceSession(session)
    onUpdate?.(job)
    if (job.status === 'completed') {
      const result = extract(job)
      if (result === undefined) throw new Error('任务已完成，但结果为空')
      return result
    }
    if (job.status === 'failed' && !job.next_retry_at) {
      throw new Error(job.error || '任务执行失败')
    }
    if (job.status === 'cancelled') {
      throw new Error(job.error || '任务已取消')
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

export function extractPublication(job: JobResponse) {
  return job.result?.publication as Publication | undefined
}
