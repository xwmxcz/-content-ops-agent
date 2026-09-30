import { api } from './index'

export interface StatsPayload {
  total_contents: number
  by_type: Record<string, number>
  by_status: Record<string, number>
}

export async function getStats(signal?: AbortSignal) {
  const { data } = await api.get<StatsPayload>('/stats', { signal })
  return data
}

export interface PerformanceTotals {
  metric_rows: number
  views: number
  likes: number
  comments: number
  shares: number
  interactions: number
  engagement_rate: number | null
}

export interface PerformanceStats {
  window_days: number
  window_start: string
  window_end: string
  platform: string | null
  available_platforms: string[]
  total_contents: number
  measured_contents: number
  missing_contents: number
  last_recorded_at: string | null
  totals: PerformanceTotals
  by_platform: (PerformanceTotals & { platform: string })[]
  by_creation_date: (PerformanceTotals & { date: string; total_contents: number; measured_contents: number })[]
  top_contents: (PerformanceTotals & { content_id: number; title: string | null; platform: string })[]
}

export async function getPerformanceStats(params: { days: number; platform?: string }, signal?: AbortSignal) {
  const { data } = await api.get<PerformanceStats>('/stats/performance', { params, signal })
  return data
}
