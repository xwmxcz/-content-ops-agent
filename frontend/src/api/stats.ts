import { api } from './index'

export interface StatsPayload {
  total_contents: number
  by_type: Record<string, number>
  by_status: Record<string, number>
}

export async function getStats() {
  const { data } = await api.get<StatsPayload>('/stats')
  return data
}
