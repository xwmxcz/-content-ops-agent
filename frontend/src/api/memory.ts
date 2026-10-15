import { api } from './index'

export interface MemoryFile {
  content: string
  char_count: number
  char_limit: number
  etag?: string
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

export async function saveAgentMemory(content: string, expectedEtag?: string) {
  const payload = expectedEtag !== undefined ? { content, expected_etag: expectedEtag } : { content }
  const { data } = await api.put<MemoryFile>('/memory/agent', payload)
  return data
}

export async function getUserMemory() {
  const { data } = await api.get<MemoryFile>('/memory/user')
  return data
}

export async function saveUserMemory(content: string, expectedEtag?: string) {
  const payload = expectedEtag !== undefined ? { content, expected_etag: expectedEtag } : { content }
  const { data } = await api.put<MemoryFile>('/memory/user', payload)
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
