import { api } from './index'

export interface CalendarEvent {
  event_id: number
  content_id: number
  platform: string
  scheduled_date: string
  status: string
  content_title?: string
  content_type?: string
}

export async function getEvents(days = 30) {
  const { data } = await api.get<CalendarEvent[]>('/calendar/events', { params: { days } })
  return data
}

export async function createEvent(payload: { content_id: number; platform: string; scheduled_date: string }) {
  const { data } = await api.post<{ event_id: number }>('/calendar/events', payload)
  return data
}
