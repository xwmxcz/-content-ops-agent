import { api } from './index'
import { contentChanged, contentDeleted } from '../query/client'
import { workspaceSessionId } from '../workspaceSession'

export interface ContentItem {
  id: number
  title?: string
  content: string
  content_type: string
  style: string
  tags?: string[]
  status: string
  created_at?: string
  updated_at?: string
}

export interface GeneratePayload {
  topic: string
  content_type: string
  style: string
  keywords?: string[]
  length: string
  provider?: string
  model?: string
  temperature: number
  max_tokens: number
}

export interface RefinePayload {
  content_id: number
  instruction?: string
  new_style?: string
  provider?: string
  model?: string
  temperature: number
  max_tokens: number
}

export interface ProviderInfo {
  id: string
  name: string
  configured: boolean
  default_model: string
  models: Array<{ id: string; name: string }>
}

export async function getModels() {
  const { data } = await api.get<ProviderInfo[]>('/models')
  return data
}

export async function generateContent(payload: GeneratePayload) {
  const session = workspaceSessionId.value
  const { data } = await api.post<ContentItem>('/content/generate', payload)
  contentChanged(session, data.id)
  return data
}

export async function refineContent(payload: RefinePayload) {
  const session = workspaceSessionId.value
  const { data } = await api.post<ContentItem>('/content/refine', payload)
  contentChanged(session, data.id)
  return data
}

export interface ContentListParams {
  limit?: number
  offset?: number
  content_type?: string
  status?: string
  q?: string
}

export async function getContents(params: ContentListParams = {}, signal?: AbortSignal) {
  const { data } = await api.get<ContentItem[]>('/content', { params, signal })
  return data
}

export async function getContent(id: number, signal?: AbortSignal) {
  const { data } = await api.get<ContentItem>(`/content/${id}`, { signal })
  return data
}

export async function archiveContent(id: number) {
  const session = workspaceSessionId.value
  const { data } = await api.post<{ archived: boolean }>(`/content/${id}/archive`)
  contentChanged(session, id)
  return data
}

export async function deleteContentLocal(id: number) {
  const session = workspaceSessionId.value
  const { data } = await api.delete<{ deleted: boolean }>(`/content/${id}`)
  contentDeleted(session, id)
  return data
}

export async function generateTitles(payload: Record<string, unknown>) {
  const { data } = await api.post<{ result: string }>('/content/titles', payload)
  return data.result
}

export async function analyzeSeo(payload: Record<string, unknown>) {
  const { data } = await api.post<{ result: string }>('/content/seo', payload)
  return data.result
}
