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
  status: 'completed' | 'failed'
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
  tool_events: ChatToolEvent[]
  plan: PlanStep[]
}

export interface AgentThread {
  id: string
  title?: string
  last_provider?: string
  last_model?: string
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
  tool_events: ChatToolEvent[]
  plan: PlanStep[]
  status: string
  created_at?: string
}

export async function chat(payload: ChatPayload) {
  const { data } = await api.post<ChatResponse>('/agent/chat', payload)
  return data
}

export async function runAgentPipeline(payload: AgentRunPayload) {
  const { data } = await api.post<AgentRunResponse>('/agent/run', payload)
  return data
}

export async function getAgentThreads() {
  const { data } = await api.get<AgentThread[]>('/agent/threads')
  return data
}

export async function getAgentMessages(threadId: string) {
  const { data } = await api.get<AgentMessage[]>(`/agent/threads/${threadId}/messages`)
  return data
}

export async function deleteAgentThread(threadId: string) {
  const { data } = await api.delete<{ deleted: boolean }>(`/agent/threads/${threadId}`)
  return data
}
