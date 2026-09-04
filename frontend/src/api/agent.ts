import { api } from './index'

export interface AgentRunPayload {
  topic: string
  content_type: string
  style: string
  keywords?: string[]
  length: string
  provider?: string
  model?: string
  temperature: number
  max_tokens: number
  save_final?: boolean
  thread_id?: string
}

export interface AgentStep {
  id: string
  name: string
  role: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  input_summary: string
  output: string
  duration_ms: number
  error?: string
}

export interface AgentFinalContent {
  title?: string
  content: string
  content_type: string
  style: string
  tags: string[]
  status: string
}

export interface AgentRunResponse {
  run_id: string
  thread_id: string
  steps: AgentStep[]
  final_content: AgentFinalContent
  saved_content_id?: number
  provider: string
  model: string
}

export interface ChatToolEvent {
  name: string
  args: Record<string, unknown>
  output: string
  status: 'completed' | 'failed' | 'proposed'
  error?: string
  plan_step_index?: number | null
  attempt?: number
  duration_ms?: number
}

export interface PlanStep {
  index: number
  description: string
  tool_hint?: string | null
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
}

export type ChatIntentName =
  | 'content_create'
  | 'content_refine'
  | 'title_generate'
  | 'seo_optimize'
  | 'content_search'
  | 'topic_strategy'
  | 'performance_review'
  | 'calendar_view'
  | 'schedule_propose'
  | 'schedule_commit'
  | 'memory_update'
  | 'action_confirm'
  | 'smalltalk'
  | 'clarify'
  | 'unknown'

export interface ChatIntent {
  name: ChatIntentName
  confidence: number
  slots: Record<string, unknown>
  requires_confirmation: boolean
  allowed_tools: string[]
  route_surface: 'chat' | 'studio' | 'publish' | 'none'
  route_reason?: string | null
  clarification?: string | null
}

export interface ChatPayload {
  message: string
  thread_id?: string
  provider?: string
  model?: string
  temperature: number
  max_tokens: number
}

export interface ChatResponse {
  message_id: number
  thread_id: string
  response: string
  provider: string
  model: string
  intent?: ChatIntent | null
  tool_events: ChatToolEvent[]
  plan: PlanStep[]
}

export interface AgentThread {
  id: string
  title?: string
  last_provider?: string
  last_model?: string
  pinned: boolean
  archived: boolean
  title_pinned: boolean
  message_count: number
  created_at?: string
  updated_at?: string
}

export interface AgentMessage {
  id: number
  thread_id: string
  role: 'user' | 'assistant'
  content: string
  provider?: string
  model?: string
  intent?: ChatIntent | null
  tool_events: ChatToolEvent[]
  plan: PlanStep[]
  status: string
  created_at?: string
}

export interface AgentSearchHit {
  message_id: number
  thread_id: string
  role: 'user' | 'assistant'
  content: string
  provider?: string
  model?: string
  created_at?: string
}

export interface ListThreadsParams {
  limit?: number
  offset?: number
  include_archived?: boolean
  q?: string
}

export interface ListMessagesParams {
  limit?: number
  before_id?: number
}

export interface UpdateThreadPatch {
  title?: string
  pinned?: boolean
  archived?: boolean
}

export async function chat(payload: ChatPayload) {
  const { data } = await api.post<ChatResponse>('/agent/chat', payload)
  return data
}

export async function runAgentPipeline(payload: AgentRunPayload) {
  const { data } = await api.post<AgentRunResponse>('/agent/run', payload)
  return data
}

export async function getAgentThreads(params: ListThreadsParams = {}) {
  const { data } = await api.get<AgentThread[]>('/agent/threads', { params })
  return data
}

export async function getAgentMessages(threadId: string, params: ListMessagesParams = {}) {
  const { data } = await api.get<AgentMessage[]>(`/agent/threads/${threadId}/messages`, { params })
  return data
}

export async function deleteAgentThread(threadId: string) {
  const { data } = await api.delete<{ deleted: boolean }>(`/agent/threads/${threadId}`)
  return data
}

export async function updateAgentThread(threadId: string, patch: UpdateThreadPatch) {
  const { data } = await api.patch<AgentThread>(`/agent/threads/${threadId}`, patch)
  return data
}

export async function searchAgentMessages(q: string, opts: { limit?: number; thread_id?: string } = {}) {
  const { data } = await api.get<AgentSearchHit[]>('/agent/threads/search', {
    params: { q, ...opts }
  })
  return data
}

// ---------- Dynamic pipeline (Studio v2) -----------------------------------

export type SubAgentId =
  | 'strategy'
  | 'writer'
  | 'editor'
  | 'reviewer'
  | 'researcher'
  | 'fact_checker'

export interface SubAgentToolEvent {
  name: string
  args: Record<string, unknown>
  status: 'started' | 'completed' | 'failed'
  preview: string
  error?: string | null
  duration_ms: number
}

export interface PipelinePlanStep {
  index: number
  agent_id: SubAgentId
  description: string
  instruction?: string
  inputs_from: number[]
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
  output: string
  duration_ms: number
  prompt_tokens: number
  completion_tokens: number
  cost_estimate: number
  revised_at?: number | null
  tool_events?: SubAgentToolEvent[]
}

export interface PipelineRunPayload {
  topic: string
  content_type: string
  style: string
  keywords?: string[]
  length: string
  provider?: string
  model?: string
  temperature: number
  max_tokens: number
  save_final?: boolean
  thread_id?: string
  use_web_search?: boolean
  use_history_search?: boolean
  research_focus?: string
}

export interface PipelineRunHandle {
  run_id: string
  thread_id: string
  provider: string
  model: string
}

export async function createPipelineRun(payload: PipelineRunPayload) {
  const { data } = await api.post<PipelineRunHandle>('/agent/runs', payload)
  return data
}

export function pipelineStreamUrl(runId: string, afterSeq?: number) {
  // EventSource ignores axios baseURL. The browser sends the HttpOnly resource
  // session cookie; no bearer or ticket material is placed in the URL.
  const base = (api.defaults.baseURL || '').replace(/\/$/, '')
  const url = `${base}/agent/runs/${runId}/stream`
  // Resume cursor goes in the query string, not Last-Event-ID: the native
  // EventSource sends that header only for its own automatic reconnects, and we
  // manage reconnection ourselves so backoff and state are observable.
  if (afterSeq && afterSeq > 0) return `${url}?after_seq=${afterSeq}`
  return url
}

export interface PipelineRunSnapshot {
  id: string
  thread_id: string
  status: 'running' | 'completed' | 'failed' | 'cancelled' | string
  plan: PipelinePlanStep[]
  revision_count: number
  total_prompt_tokens: number
  total_completion_tokens: number
  total_cost: number
  saved_content_id?: number | null
  error?: string | null
  next_event_seq: number
  created_at?: string | null
  completed_at?: string | null
}

/**
 * Authoritative run state, used to reconcile after the stream gives up. A dead
 * transport does not mean a dead run, so the UI must ask instead of assuming.
 */
export async function getPipelineRun(runId: string) {
  const { data } = await api.get<PipelineRunSnapshot>(`/agent/runs/${runId}`)
  return data
}

export async function cancelPipelineRun(runId: string) {
  const { data } = await api.delete<{ run_id: string; status: string; cancelled: boolean }>(
    `/agent/runs/${runId}`
  )
  return data
}
