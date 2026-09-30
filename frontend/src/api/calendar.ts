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

export interface CalendarEventInput {
  content_id: number
  platform: string
  scheduled_date: string
}

export async function getEvents(range: number | { start_date: string; end_date: string } = 30) {
  const { data } = await api.get<CalendarEvent[]>('/calendar/events', {
    params: typeof range === 'number' ? { days: range } : range
  })
  return data
}

export async function createEvent(payload: CalendarEventInput) {
  const { data } = await api.post<{ event_id: number }>('/calendar/events', payload)
  return data
}

export async function updateEvent(eventId: number, payload: CalendarEventInput) {
  const { data } = await api.put<{ event_id: number }>(`/calendar/events/${eventId}`, payload)
  return data
}

export async function deleteEvent(eventId: number) {
  await api.delete(`/calendar/events/${eventId}`)
}
