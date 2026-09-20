import { api } from './index'

export interface ContentMetrics {
  id: number
  content_id: number
  platform: string | null
  views: number
  likes: number
  comments: number
  shares: number
  engagement_rate: number
  recorded_at?: string | null
}

export interface ContentMetricsPayload {
  platform: string
  views: number
  likes: number
  comments: number
  shares: number
}

export interface MetricsImportRow extends ContentMetricsPayload {
  content_id: number
}

export interface MetricsImportResult {
  recorded: number
  missing_content_ids: number[]
}

export async function getContentMetrics(contentId: number) {
  const { data } = await api.get<ContentMetrics[]>(`/content/${contentId}/metrics`)
  return data
}

export async function recordContentMetrics(contentId: number, payload: ContentMetricsPayload) {
  const { data } = await api.put<ContentMetrics>(`/content/${contentId}/metrics`, payload)
  return data
}

export async function importContentMetrics(rows: MetricsImportRow[]) {
  const { data } = await api.post<MetricsImportResult>('/content/metrics/import', { rows })
  return data
}
