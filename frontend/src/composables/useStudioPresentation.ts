/**
 * Labels, option lists, and formatting helpers for the Studio pages.
 *
 * These are pure: no reactive state, no API calls. They live outside the
 * component so they can be unit-tested directly, and because several of them
 * encode user-visible copy (the option labels, the status wording) that a
 * component test would otherwise only reach through the rendered DOM.
 */

import type { PipelinePlanStep, SubAgentToolEvent } from '../api/agent'

export type StudioMode = 'dynamic' | 'workflow'
export type RunStatus = 'idle' | 'planning' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface SelectOption {
  label: string
  value: string
}

export const contentTypeOptions: SelectOption[] = [
  { label: '小红书', value: 'xiaohongshu' },
  { label: '微博', value: 'weibo' },
  { label: '博客文章', value: 'blog' },
  { label: '视频脚本', value: 'video_script' },
  { label: 'Twitter / X', value: 'twitter' }
]

export const styleOptions: SelectOption[] = [
  { label: '专业', value: 'professional' },
  { label: '轻松', value: 'casual' },
  { label: '营销', value: 'marketing' },
  { label: '故事', value: 'storytelling' }
]

export const modeOptions: SelectOption[] = [
  { label: '标准工作流', value: 'workflow' },
  { label: '研究型 Pipeline', value: 'dynamic' }
]

const AGENT_LABELS: Record<string, string> = {
  strategy: '策略',
  writer: '初稿',
  editor: '润色',
  reviewer: '审核',
  review: '审核',
  researcher: '调研',
  fact_checker: '事实校验'
}

const WORKFLOW_DESCRIPTIONS: Record<string, string> = {
  strategy: '分析受众、角度、结构与转化意图',
  writer: '把策略转成可编辑的第一版内容',
  editor: '优化表达、节奏与平台适配',
  review: '给出 1-100 分以及风险与改进建议'
}

export const RESEARCH_AGENTS = new Set(['researcher', 'fact_checker'])

const STEP_STATUS_LABELS: Record<PipelinePlanStep['status'], string> = {
  pending: '待运行',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  skipped: '已跳过'
}

export function agentLabel(id: string): string {
  return AGENT_LABELS[id] ?? id
}

export function workflowDescription(id: string): string {
  return WORKFLOW_DESCRIPTIONS[id] || ''
}

export function isResearchStep(agentId: string): boolean {
  return RESEARCH_AGENTS.has(agentId)
}

export function statusLabel(status: PipelinePlanStep['status']): string {
  return STEP_STATUS_LABELS[status]
}

export function statusToPill(status: PipelinePlanStep['status']): string {
  if (status === 'running') return 'running'
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'failed'
  return ''
}

/**
 * Render a tool call's arguments for the trace list.
 *
 * Strings are shown raw and everything else is JSON, because an argument that is
 * itself JSON (`{"plan": [...]}`) is unreadable if quoted and escaped.
 */
export function formatToolArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args || {})
  if (!entries.length) return ''
  return entries
    .map(([key, value]) => `${key}: ${typeof value === 'string' ? value : JSON.stringify(value)}`)
    .join(', ')
}

/**
 * Render a tool result preview.
 *
 * An empty container means "ran successfully, found nothing", which reads very
 * differently from a blank cell. `[]` and `{}` are therefore labelled rather
 * than shown as empty or as literal JSON punctuation.
 */
export function formatToolPreview(preview?: string | null): string {
  const trimmed = (preview || '').trim()
  if (!trimmed) return '完成'
  try {
    const parsed = JSON.parse(trimmed)
    if (Array.isArray(parsed) && parsed.length === 0) return '无结果'
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && Object.keys(parsed).length === 0) {
      return '无结果'
    }
  } catch {
    // Plain text previews are displayed as-is.
  }
  return trimmed
}

/** Live tool events for a step, falling back to the events recorded on the step. */
export function toolEventsFor(
  stepIndex: number,
  live: Record<number, SubAgentToolEvent[]>,
  plan: PipelinePlanStep[]
): SubAgentToolEvent[] {
  const pending = live[stepIndex]
  if (pending && pending.length) return pending
  const step = plan.find(candidate => candidate.index === stepIndex)
  return step?.tool_events ?? []
}
