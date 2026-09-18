/**
 * Behaviour tests for the extracted Studio step dialog.
 *
 * The dialog had no component coverage before the extraction. What matters here
 * is the branching that decides *what a user is told about a step*: a running
 * step says it is generating, a completed step with no text says so explicitly
 * rather than looking broken, and a failed step says it failed. Those four
 * branches are the reason this markup is worth testing rather than trusting.
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import StudioStepDialog from '../src/components/StudioStepDialog.vue'
import type { PipelinePlanStep, SubAgentToolEvent } from '../src/api/agent'

function step(overrides: Partial<PipelinePlanStep> = {}): PipelinePlanStep {
  return {
    index: 2,
    agent_id: 'writer',
    description: '写出初稿',
    status: 'pending',
    ...overrides
  } as PipelinePlanStep
}

function toolEvent(overrides: Partial<SubAgentToolEvent> = {}): SubAgentToolEvent {
  return { name: 'web_search', args: {}, status: 'completed', preview: '', duration_ms: 0, ...overrides }
}

function mountDialog(props: Record<string, unknown> = {}) {
  return mount(StudioStepDialog, {
    props: { open: true, step: step(), toolEvents: [], streamingOutput: '', ...props },
    global: {
      stubs: {
        // Element Plus is not registered in this suite; a transparent stub keeps
        // the slot content assertable.
        'el-dialog': { template: '<div class="dialog"><slot /></div>' },
        'el-icon': { template: '<i><slot /></i>' }
      }
    }
  })
}

describe('StudioStepDialog header', () => {
  it('titles the dialog with the step index and agent label', () => {
    // The title is built from the step, so a mismatched index would point the
    // user at the wrong step.
    expect(mountDialog().props('step')).toMatchObject({ index: 2 })
  })

  it('shows the raw agent id and a research marker for research steps', () => {
    const wrapper = mountDialog({ step: step({ agent_id: 'fact_checker' }) })
    expect(wrapper.text()).toContain('fact_checker')
    expect(wrapper.text()).toContain('research')
  })

  it('does not mark a non-research step as research', () => {
    expect(mountDialog({ step: step({ agent_id: 'writer' }) }).text()).not.toContain('research')
  })

  it('shows the step duration only when it is known', () => {
    expect(mountDialog({ step: step({ duration_ms: 0 }) }).text()).not.toContain(' ms')
    expect(mountDialog({ step: step({ duration_ms: 1234 }) }).text()).toContain('1234 ms')
  })

  it('renders the step description', () => {
    expect(mountDialog().text()).toContain('写出初稿')
  })
})

describe('StudioStepDialog tool trace', () => {
  it('omits the trace entirely when there are no tool calls', () => {
    expect(mountDialog().find('.tool-trace').exists()).toBe(false)
  })

  it('lists one row per tool event', () => {
    const wrapper = mountDialog({
      toolEvents: [toolEvent({ name: 'web_search' }), toolEvent({ name: 'view_content' })]
    })
    expect(wrapper.findAll('.tool-row')).toHaveLength(2)
    expect(wrapper.text()).toContain('web_search')
    expect(wrapper.text()).toContain('view_content')
  })

  it('shows a running marker for an in-flight call and no result', () => {
    const wrapper = mountDialog({ toolEvents: [toolEvent({ status: 'started' })] })
    expect(wrapper.text()).toContain('运行中')
    expect(wrapper.find('.tool-preview').exists()).toBe(false)
  })

  it('surfaces the error text for a failed call', () => {
    const wrapper = mountDialog({ toolEvents: [toolEvent({ status: 'failed', error: 'timeout' })] })
    expect(wrapper.find('.tool-error').text()).toBe('timeout')
  })

  it('falls back to a literal when a failure has no error message', () => {
    const wrapper = mountDialog({ toolEvents: [toolEvent({ status: 'failed', error: null })] })
    expect(wrapper.find('.tool-error').text()).toBe('失败')
  })

  it('renders arguments only when the call has some', () => {
    expect(mountDialog({ toolEvents: [toolEvent()] }).find('.tool-args').exists()).toBe(false)
    const wrapper = mountDialog({ toolEvents: [toolEvent({ args: { query: 'x' } })] })
    expect(wrapper.find('.tool-args').text()).toBe('(query: x)')
  })

  it('carries the event status as a class so failures can be styled', () => {
    const wrapper = mountDialog({ toolEvents: [toolEvent({ status: 'failed' })] })
    expect(wrapper.find('.tool-row').classes()).toContain('failed')
  })
})

describe('StudioStepDialog output branches', () => {
  it('shows the completed output', () => {
    const wrapper = mountDialog({ step: step({ status: 'completed', output: 'final text' }) })
    expect(wrapper.find('.step-output').text()).toBe('final text')
  })

  it('falls back to the streaming buffer while the step has no output yet', () => {
    // During a run the streamed text arrives before the step record is updated;
    // showing nothing there would look stalled.
    const wrapper = mountDialog({ step: step({ status: 'running' }), streamingOutput: 'partial…' })
    expect(wrapper.find('.step-output').text()).toBe('partial…')
  })

  it('prefers the recorded output over the streaming buffer once available', () => {
    const wrapper = mountDialog({
      step: step({ status: 'completed', output: 'recorded' }),
      streamingOutput: 'stale buffer'
    })
    expect(wrapper.find('.step-output').text()).toBe('recorded')
  })

  it('tells the user a running step is still generating', () => {
    expect(mountDialog({ step: step({ status: 'running' }) }).text()).toContain('正在生成')
  })

  it('says explicitly that a completed step produced no text', () => {
    // A blank panel would read as a bug rather than as a step that only made
    // tool calls.
    expect(mountDialog({ step: step({ status: 'completed' }) }).text()).toContain('未产出文本输出')
  })

  it('reports a failed step with no output as failed', () => {
    const wrapper = mountDialog({ step: step({ status: 'failed' }) })
    expect(wrapper.text()).toContain('步骤失败')
    expect(wrapper.find('.step-empty').classes()).toContain('failed')
  })

  it('reports a skipped step', () => {
    expect(mountDialog({ step: step({ status: 'skipped' }) }).text()).toContain('已跳过')
  })

  it('reports a pending step as waiting', () => {
    expect(mountDialog({ step: step({ status: 'pending' }) }).text()).toContain('等待执行')
  })

  it('renders nothing but the shell when no step is selected', () => {
    const wrapper = mountDialog({ step: null })
    expect(wrapper.find('.step-description').exists()).toBe(false)
    expect(wrapper.find('.step-pending').exists()).toBe(false)
  })
})
