/**
 * Tests for the Chat presentation helpers.
 *
 * Extracted from Chat.vue, which had no unit coverage of these rules. Two of
 * them carry real meaning:
 *
 * - `eventStatusLabel` must distinguish `proposed` from `completed`. A proposed
 *   write has NOT happened and is waiting on the user; rendering it as "ok" would
 *   report an unexecuted action as done.
 * - `prettyOutput` only reformats something that parses as JSON, so plain-text
 *   tool output keeps its original formatting.
 */
import { describe, expect, it } from 'vitest'
import {
  eventStatusLabel,
  hasArgs,
  intentConfidence,
  intentLabel,
  planMarker,
  prettyArgs,
  prettyOutput,
  summarizeEvent
} from '../src/composables/useChatPresentation'
import type { ChatIntentName, ChatToolEvent } from '../src/api/agent'

function event(overrides: Partial<ChatToolEvent> = {}): ChatToolEvent {
  return { name: 'view_content', args: {}, status: 'completed', preview: '', duration_ms: 0, ...overrides }
}

describe('intentLabel', () => {
  it('translates every declared intent', () => {
    const names: ChatIntentName[] = [
      'content_create',
      'content_refine',
      'title_generate',
      'seo_optimize',
      'content_search',
      'topic_strategy',
      'performance_review',
      'calendar_view',
      'schedule_propose',
      'schedule_commit',
      'memory_update',
      'action_confirm',
      'smalltalk',
      'clarify',
      'unknown'
    ]
    for (const name of names) {
      expect(intentLabel(name)).not.toBe('')
      // A missing mapping would fall through to the raw key.
      expect(intentLabel(name)).not.toBe(name)
    }
  })

  it('renders confidence as a whole percentage', () => {
    expect(intentConfidence(0.913)).toBe('91%')
    expect(intentConfidence(1)).toBe('100%')
  })

  it('treats a missing confidence as zero rather than NaN', () => {
    expect(intentConfidence(undefined)).toBe('0%')
  })
})

describe('eventStatusLabel', () => {
  it('reports completed as ok', () => {
    expect(eventStatusLabel('completed')).toBe('ok')
  })

  it('reports a proposed write as confirm, not ok', () => {
    // The action has not run yet; "ok" would misreport it as done.
    expect(eventStatusLabel('proposed')).toBe('confirm')
  })

  it('reports anything else as failed', () => {
    expect(eventStatusLabel('failed')).toBe('failed')
  })
})

describe('summarizeEvent', () => {
  it('surfaces the error for a failed event', () => {
    expect(summarizeEvent(event({ status: 'failed', error: 'boom' }))).toBe('boom')
  })

  it('falls back to output then to a literal when a failure has no error', () => {
    expect(summarizeEvent(event({ status: 'failed', error: undefined, output: 'partial' }))).toBe('partial')
    expect(summarizeEvent(event({ status: 'failed', error: undefined, output: undefined }))).toBe('failed')
  })

  it('collapses whitespace so a multi-line result stays one line', () => {
    expect(summarizeEvent(event({ output: 'a\n\n  b   c' }))).toBe('a b c')
  })

  it('truncates a long result with an ellipsis', () => {
    const summary = summarizeEvent(event({ output: 'x'.repeat(200) }))
    expect(summary).toHaveLength(81)
    expect(summary.endsWith('…')).toBe(true)
  })

  it('does not truncate a result at exactly the limit', () => {
    const exact = 'y'.repeat(80)
    expect(summarizeEvent(event({ output: exact }))).toBe(exact)
  })
})

describe('prettyArgs', () => {
  it('indents JSON so arguments are readable', () => {
    expect(prettyArgs({ a: 1 })).toBe('{\n  "a": 1\n}')
  })

  it('returns an empty string for absent arguments', () => {
    expect(prettyArgs(undefined)).toBe('')
  })

  it('reports whether there are arguments to show', () => {
    expect(hasArgs({ a: 1 })).toBe(true)
    expect(hasArgs({})).toBe(false)
    expect(hasArgs(undefined)).toBe(false)
  })
})

describe('prettyOutput', () => {
  it('indents a JSON-looking result', () => {
    expect(prettyOutput('{"count":2}')).toBe('{\n  "count": 2\n}')
  })

  it('returns plain text unchanged, preserving its formatting', () => {
    // A JSON round-trip would strip the line breaks from plain-text output.
    expect(prettyOutput('line one\nline two')).toBe('line one\nline two')
  })

  it('returns malformed JSON braces unchanged instead of throwing', () => {
    expect(prettyOutput('{not json')).toBe('{not json')
  })

  it('returns an empty string for absent output', () => {
    expect(prettyOutput(undefined)).toBe('')
    expect(prettyOutput('   ')).toBe('')
  })
})

describe('planMarker', () => {
  it('gives each step status a distinct glyph', () => {
    const markers = (['pending', 'running', 'completed', 'failed', 'skipped'] as const).map(planMarker)
    expect(new Set(markers).size).toBe(markers.length)
    expect(planMarker('failed')).toBe('✗')
  })

  it('falls back to pending for an unexpected status', () => {
    expect(planMarker('mystery' as never)).toBe('○')
  })
})
