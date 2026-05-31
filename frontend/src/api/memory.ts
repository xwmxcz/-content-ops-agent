import { api } from './index'

export interface MemoryFile {
  content: string
  char_count: number
  char_limit: number
}

export interface SessionSearchHit {
  id: number
  thread_id: string
  role: string
  content: string
  provider?: string | null
  model?: string | null
  status?: string | null
  created_at?: string | null
}

export interface SessionSearchResult {
  messages: SessionSearchHit[]
  count: number
}

export async function getAgentMemory() {
  const { data } = await api.get<MemoryFile>('/memory/agent')
  return data
}

export async function saveAgentMemory(content: string) {
  const { data } = await api.put<MemoryFile>('/memory/agent', { content })
  return data
}

export async function getUserMemory() {
  const { data } = await api.get<MemoryFile>('/memory/user')
  return data
}

export async function saveUserMemory(content: string) {
  const { data } = await api.put<MemoryFile>('/memory/user', { content })
  return data
}

export async function searchSessions(q: string, limit = 10, threadId?: string) {
  const { data } = await api.post<SessionSearchResult>('/memory/search', {
    q,
    limit,
    thread_id: threadId ?? null,
  })
  return data
}

export async function refreshSnapshot(threadId?: string) {
  await api.post('/memory/refresh-snapshot', { thread_id: threadId ?? null })
}
