import { api } from './index'

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
  const { data } = await api.post<ContentItem>('/content/generate', payload)
  return data
}

export async function refineContent(payload: RefinePayload) {
  const { data } = await api.post<ContentItem>('/content/refine', payload)
  return data
}

export async function getContents(params: Record<string, unknown> = {}) {
  const { data } = await api.get<ContentItem[]>('/content', { params })
  return data
}

export async function getContent(id: number) {
  const { data } = await api.get<ContentItem>(`/content/${id}`)
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
