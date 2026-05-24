import { api } from './index'

export interface Memory {
  id: string
  content: string
  category: string
  importance: number
  access_count: number
  last_used_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface MemoryCreatePayload {
  content: string
  category: string
  importance: number
}

export interface MemoryUpdatePayload {
  content?: string
  category?: string
  importance?: number
}

export interface MemorySearchResult {
  memories: Memory[]
  count: number
}

export async function getMemories(category?: string, limit = 50) {
  const { data } = await api.get<Memory[]>('/memories', { params: { category, limit } })
  return data
}

export async function createMemory(payload: MemoryCreatePayload) {
  const { data } = await api.post<Memory>('/memories', payload)
  return data
}

export async function deleteMemory(id: string) {
  await api.delete(`/memories/${id}`)
}

export async function updateMemory(id: string, payload: MemoryUpdatePayload) {
  const { data } = await api.put<Memory>(`/memories/${id}`, payload)
  return data
}

export async function searchMemories(q: string, category?: string, limit = 10) {
  const { data } = await api.get<MemorySearchResult>('/memories/search/query', {
    params: { q, category, limit }
  })
  return data
}
