/**
 * Tests for the Studio presentation helpers.
 *
 * These were extracted from Studio.vue, which had no unit coverage at all: the
 * component is 2000 lines with a template that cannot be mounted without the API
 * layer, so the label maps and formatting rules were only reachable through a
 * full render. They matter beyond cosmetics — `formatToolPreview` decides whether
 * a tool that found nothing reads as "无结果" or as an empty cell, and
 * `statusToPill` drives the colour a user reads as success or failure.
 */
import { describe, expect, it } from 'vitest'
import {
  agentLabel,
  contentTypeOptions,
  formatToolArgs,
  formatToolPreview,
  isResearchStep,
  modeOptions,
  statusLabel,
  statusToPill,
  styleOptions,
  toolEventsFor,
  workflowDescription
} from '../src/composables/useStudioPresentation'
import type { PipelinePlanStep, SubAgentToolEvent } from '../src/api/agent'

function step(overrides: Partial<PipelinePlanStep> = {}): PipelinePlanStep {
  return {
    index: 1,
    agent_id: 'writer',
    description: 'write it',
    status: 'pending',
    ...overrides
  } as PipelinePlanStep
}

describe('studio option lists', () => {
  it('offers every content type the backend accepts', () => {
    expect(contentTypeOptions.map(o => o.value)).toEqual([
      'xiaohongshu',
      'weibo',
      'blog',
      'video_script',
      'twitter'
    ])
  })

  it('offers both run modes', () => {
    expect(modeOptions.map(o => o.value)).toEqual(['workflow', 'dynamic'])
  })

  it('offers the four writing styles', () => {
    expect(styleOptions.map(o => o.value)).toEqual([
      'professional',
      'casual',
      'marketing',
      'storytelling'
    ])
  })
})

describe('agentLabel', () => {
  it('translates known agent ids', () => {
    expect(agentLabel('writer')).toBe('初稿')
    expect(agentLabel('fact_checker')).toBe('事实校验')
  })

  it('falls back to the raw id rather than hiding an unknown agent', () => {
    // An unmapped agent must still be identifiable in the trace, so the id is
    // shown instead of a placeholder.
    expect(agentLabel('some_new_agent')).toBe('some_new_agent')
  })
})

describe('isResearchStep', () => {
  it.each(['researcher', 'fact_checker'])('classifies %s as research', id => {
    expect(isResearchStep(id)).toBe(true)
  })

  it.each(['writer', 'editor', 'reviewer', 'strategy'])('does not classify %s as research', id => {
    expect(isResearchStep(id)).toBe(false)
  })
})

describe('workflowDescription', () => {
  it('describes the four workflow stages', () => {
    for (const id of ['strategy', 'writer', 'editor', 'review']) {
      expect(workflowDescription(id)).not.toBe('')
    }
  })

  it('returns an empty string for an unknown stage', () => {
    expect(workflowDescription('nope')).toBe('')
  })
})

describe('status labels and pills', () => {
  it.each([
    ['pending', '待运行'],
    ['running', '运行中'],
    ['completed', '已完成'],
    ['failed', '失败'],
    ['skipped', '已跳过']
  ] as const)('labels %s as %s', (status, label) => {
    expect(statusLabel(status)).toBe(label)
  })

  it('maps only running/completed/failed to a pill class', () => {
    expect(statusToPill('running')).toBe('running')
    expect(statusToPill('completed')).toBe('success')
    expect(statusToPill('failed')).toBe('failed')
  })

  it('leaves pending and skipped unstyled rather than mislabelling them', () => {
    // A neutral step must not borrow the success/failure colour.
    expect(statusToPill('pending')).toBe('')
    expect(statusToPill('skipped')).toBe('')
  })
})

describe('formatToolArgs', () => {
  it('renders strings raw and everything else as JSON', () => {
    expect(formatToolArgs({ query: 'hello', limit: 3 })).toBe('query: hello, limit: 3')
  })

  it('does not quote or escape a nested object argument', () => {
    // A plan-shaped argument is unreadable if JSON-escaped into a string.
    expect(formatToolArgs({ plan: [{ a: 1 }] })).toBe('plan: [{"a":1}]')
  })

  it('returns an empty string when there are no arguments', () => {
    expect(formatToolArgs({})).toBe('')
  })
})

describe('formatToolPreview', () => {
  it('labels an empty result list as no-result rather than blank', () => {
    expect(formatToolPreview('[]')).toBe('无结果')
    expect(formatToolPreview('{}')).toBe('无结果')
  })

  it('treats a missing preview as completed', () => {
    // A tool with no textual output still completed; blank would read as a bug.
    expect(formatToolPreview('')).toBe('完成')
    expect(formatToolPreview(null)).toBe('完成')
    expect(formatToolPreview('   ')).toBe('完成')
  })

  it('passes plain text through unchanged', () => {
    expect(formatToolPreview('搜索完成：3 条结果')).toBe('搜索完成：3 条结果')
  })

  it('does not mangle output that looks like JSON but is not', () => {
    expect(formatToolPreview('{not json')).toBe('{not json')
  })

  it('passes a non-empty JSON payload through as its original text', () => {
    expect(formatToolPreview('{"count":2}')).toBe('{"count":2}')
  })
})

describe('toolEventsFor', () => {
  const live: SubAgentToolEvent[] = [
    { name: 'web_search', args: {}, status: 'started', preview: '', duration_ms: 0 }
  ]
  const recorded: SubAgentToolEvent[] = [
    { name: 'web_search', args: {}, status: 'completed', preview: 'ok', duration_ms: 12 }
  ]

  it('prefers live events while a step is streaming', () => {
    expect(toolEventsFor(1, { 1: live }, [step({ tool_events: recorded })] as never)).toBe(live)
  })

  it('falls back to the events recorded on the step', () => {
    expect(toolEventsFor(1, {}, [step({ tool_events: recorded })] as never)).toBe(recorded)
  })

  it('returns an empty list for a step with no events at all', () => {
    expect(toolEventsFor(9, {}, [step()] as never)).toEqual([])
  })

  it('falls back when the live list exists but is empty', () => {
    // An empty live array must not mask the server's recorded events.
    expect(toolEventsFor(1, { 1: [] }, [step({ tool_events: recorded })] as never)).toBe(recorded)
  })
})
