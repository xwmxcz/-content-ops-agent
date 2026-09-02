import { api } from './index'

export interface MediaAsset {
  id: number
  content_id: number
  media_type: 'image' | 'video'
  source_type: 'upload' | 'generated' | 'external_url'
  file_name: string
  file_path: string
  file_url: string
  mime_type?: string
  sort_order: number
  provider?: string
  generation_params?: Record<string, unknown> | null
  created_at?: string
}

export async function getContentMedia(contentId: number) {
  const { data } = await api.get<MediaAsset[]>(`/content/${contentId}/media`)
  return data
}

export async function uploadMedia(contentId: number, mediaType: 'image' | 'video', file: File) {
  const formData = new FormData()
  formData.append('content_id', String(contentId))
  formData.append('media_type', mediaType)
  formData.append('file', file)

  const { data } = await api.post<MediaAsset>('/media/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
  return data
}

export async function deleteMedia(mediaId: number) {
  const { data } = await api.delete<{ deleted: boolean }>(`/media/${mediaId}`)
  return data
}
