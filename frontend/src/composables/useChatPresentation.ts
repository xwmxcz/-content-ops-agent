/**
 * Labels and formatters for the Chat page.
 *
 * Pure functions and constant maps only: no component state, no API calls. They
 * are separated so the user-visible wording (intent names, status words) and the
 * truncation rules can be unit-tested directly rather than only through a
 * rendered component.
 */

import type { ChatIntentName, ChatToolEvent, PlanStep } from '../api/agent'

const INTENT_LABELS: Record<ChatIntentName, string> = {
  content_create: '新建内容',
  content_refine: '内容改写',
  title_generate: '标题生成',
  seo_optimize: 'SEO 优化',
  content_search: '内容检索',
  topic_strategy: '选题策略',
  performance_review: '效果复盘',
  calendar_view: '查看日历',
  schedule_propose: '排期提案',
  schedule_commit: '确认排期',
  memory_update: '记忆更新',
  action_confirm: '确认操作',
  smalltalk: '闲聊',
  clarify: '需要澄清',
  unknown: '未分类'
}

/** Chat quote-box summary length, in characters. */
const SUMMARY_LIMIT = 80

export function intentLabel(name: ChatIntentName): string {
  return INTENT_LABELS[name] || name
}

export function intentConfidence(value: number | undefined): string {
  const ratio = typeof value === 'number' ? value : 0
  return `${Math.round(ratio * 100)}%`
}

export function hasArgs(args: Record<string, unknown> | undefined): boolean {
  return !!args && Object.keys(args).length > 0
}

/**
 * Pretty-print tool arguments.
 *
 * Two-space JSON rather than the compact form: these are read by a person
 * checking what the agent actually sent, not parsed.
 */
export function prettyArgs(args: Record<string, unknown> | undefined): string {
  if (!args) return ''
  try {
    return JSON.stringify(args, null, 2)
  } catch {
    return String(args)
  }
}

/**
 * Pretty-print a tool result.
 *
 * Only reformats something that looks like JSON; anything else is returned
 * verbatim, because a JSON round-trip would strip meaningful formatting from
 * plain-text output.
 */
export function prettyOutput(output: string | undefined): string {
  if (!output) return ''
  const trimmed = output.trim()
  if (!trimmed) return ''
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      return JSON.stringify(JSON.parse(trimmed), null, 2)
    } catch {
      return output
    }
  }
  return output
}

/**
 * Short status word for a tool event.
 *
 * `proposed` is deliberately distinct from `completed`: a proposed write has not
 * happened yet and is waiting on the user, so labelling it "ok" would misreport
 * an unexecuted action as a finished one.
 */
export function eventStatusLabel(status: ChatToolEvent['status']): string {
  if (status === 'completed') return 'ok'
  if (status === 'proposed') return 'confirm'
  return 'failed'
}

/** One-line summary of a tool event for the collapsed trace view. */
export function summarizeEvent(event: ChatToolEvent): string {
  if (event.status === 'failed') {
    return event.error || event.output || 'failed'
  }
  const text = (event.output || '').replace(/\s+/g, ' ').trim()
  return text.length > SUMMARY_LIMIT ? `${text.slice(0, SUMMARY_LIMIT)}…` : text
}

export function planMarker(status: PlanStep['status']): string {
  const markers: Record<PlanStep['status'], string> = {
    pending: '○',
    running: '◐',
    completed: '●',
    failed: '✗',
    skipped: '–'
  }
  return markers[status] ?? '○'
}

/** Search-hit snippet length, in characters. */
const SNIPPET_LIMIT = 90

/** One-line snippet of a message body for the search results list. */
export function snippet(content: string): string {
  const text = content.replace(/\s+/g, ' ').trim()
  return text.length > SNIPPET_LIMIT ? `${text.slice(0, SNIPPET_LIMIT)}…` : text
}

/**
 * Format a timestamp for display.
 *
 * Falls back to the raw value when the string is unparseable, so a malformed
 * timestamp shows as-is rather than as "Invalid Date".
 */
export function formatTime(iso?: string): string {
  if (!iso) return ''
  try {
    const parsed = new Date(iso)
    if (Number.isNaN(parsed.getTime())) return iso
    return parsed.toLocaleString()
  } catch {
    return iso
  }
}
