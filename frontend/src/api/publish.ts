import { api } from './index'
import { publicationChanged } from '../query/client'
import { workspaceSessionId } from '../workspaceSession'

export interface Publication {
  id: number
  content_id: number
  platform: string
  publish_type: 'image_post' | 'video_post'
  status: 'draft' | 'queued' | 'running' | 'scheduled' | 'completed' | 'failed'
  title?: string
  body: string
  scheduled_at?: string
  published_at?: string
  external_post_id?: string
  error_message?: string
  request_payload?: Record<string, unknown> | null
  response_payload?: Record<string, unknown> | null
  created_at?: string
  updated_at?: string
}

export interface PublishPayload {
  content_id: number
  publish_type: 'image_post' | 'video_post'
  title?: string
  content?: string
  media_ids?: number[]
  scheduled_at?: string
  tags?: string[]
  visibility?: 'public' | 'self-only' | 'friends-only'
  is_original?: boolean
}

export interface PublishActionResponse {
  publication: Publication
  job_id: string
}

export interface XiaohongshuLoginStatus {
  connected: boolean
  status_text: string
  details?: Record<string, unknown> | null
}

export async function getXiaohongshuLoginStatus(signal?: AbortSignal) {
  const { data } = await api.get<XiaohongshuLoginStatus>('/publish/xiaohongshu/login-status', { signal })
  return data
}

export async function publishToXiaohongshu(payload: PublishPayload) {
  const session = workspaceSessionId.value
  const { data } = await api.post<PublishActionResponse>('/publish/xiaohongshu', payload)
  publicationChanged(session, payload.content_id)
  return data
}

export async function scheduleXiaohongshuPublication(payload: PublishPayload) {
  const session = workspaceSessionId.value
  const { data } = await api.post<PublishActionResponse>('/publish/xiaohongshu/schedule', payload)
  publicationChanged(session, payload.content_id)
  return data
}

export async function getContentPublications(contentId: number, signal?: AbortSignal) {
  const { data } = await api.get<Publication[]>(`/publish/content/${contentId}`, { signal })
  return data
}
