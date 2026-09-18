/**
 * Behaviour tests for the extracted thread panel.
 *
 * The page had no component test for this markup before the extraction, so these
 * are new coverage rather than a port. They target the wiring that the extraction
 * introduced: props in, events out. A mistake there is silent — the panel renders
 * fine but a click does nothing, or hits the wrong thread.
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatThreadPanel from '../src/components/ChatThreadPanel.vue'
import type { AgentThread } from '../src/api/agent'

function thread(overrides: Partial<AgentThread> = {}): AgentThread {
  return {
    id: 'thread-1',
    title: 'First thread',
    message_count: 3,
    pinned: false,
    archived: false,
    ...overrides
  } as AgentThread
}

const baseProps = {
  threads: [] as AgentThread[],
  threadsLoading: false,
  includeArchived: false,
  hasMoreThreads: false,
  activeThreadId: undefined as string | undefined,
  searchInput: '',
  searchActive: false,
  searching: false,
  searchResults: [],
  threadLabel: (id: string) => `label:${id}`
}

/**
 * Element Plus is not registered globally in this suite, so `el-button` would
 * otherwise render as an unresolved stub and its props would not reach the DOM.
 * The stub renders a real <button> carrying through the attributes this panel is
 * responsible for setting: `aria-label` (the accessible name) and `disabled`.
 */
const ElementStub = {
  inheritAttrs: false,
  props: ['disabled'],
  template: '<button v-bind="$attrs" :disabled="disabled"><slot /></button>'
}

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(ChatThreadPanel, {
    props: { ...baseProps, ...props },
    global: { stubs: { 'el-button': ElementStub, 'el-input': ElementStub } }
  })
}

describe('ChatThreadPanel thread list', () => {
  it('shows an empty state when there are no threads', () => {
    expect(mountPanel().text()).toContain('暂无会话')
  })

  it('does not show the empty state while loading', () => {
    // A first load would otherwise flash "暂无会话" before results arrive.
    expect(mountPanel({ threadsLoading: true }).text()).not.toContain('暂无会话')
  })

  it('renders a title and message count per thread', () => {
    const wrapper = mountPanel({ threads: [thread({ message_count: 7 })] })
    expect(wrapper.text()).toContain('First thread')
    expect(wrapper.text()).toContain('7 条消息')
  })

  it('falls back to the id when a thread has no title', () => {
    const wrapper = mountPanel({ threads: [thread({ title: '' })] })
    expect(wrapper.text()).toContain('thread-1')
  })

  it('emits select with the thread id when a row is clicked', async () => {
    const wrapper = mountPanel({ threads: [thread()] })
    await wrapper.find('.thread-item-body').trigger('click')
    expect(wrapper.emitted('select')).toEqual([['thread-1']])
  })

  it('marks the active thread', () => {
    const wrapper = mountPanel({ threads: [thread()], activeThreadId: 'thread-1' })
    expect(wrapper.find('.thread-item').classes()).toContain('active')
  })

  it('marks pinned and archived threads', () => {
    const wrapper = mountPanel({ threads: [thread({ pinned: true, archived: true })] })
    const classes = wrapper.find('.thread-item').classes()
    expect(classes).toContain('pinned')
    expect(classes).toContain('archived')
  })

  it('emits load-more only when more threads exist', async () => {
    expect(mountPanel({ threads: [thread()] }).find('.thread-load-more').exists()).toBe(false)

    const wrapper = mountPanel({ threads: [thread()], hasMoreThreads: true })
    await wrapper.find('.thread-load-more').trigger('click')
    expect(wrapper.emitted('load-more')).toEqual([[]])
  })

  it('disables load-more while a page is in flight', () => {
    const wrapper = mountPanel({ threads: [thread()], hasMoreThreads: true, threadsLoading: true })
    expect(wrapper.find('.thread-load-more').attributes('disabled')).toBeDefined()
  })
})

describe('ChatThreadPanel thread actions', () => {
  it.each([
    ['rename', '重命名', 'rename'],
    ['toggle-pin', '置顶', 'toggle-pin'],
    ['toggle-archive', '归档', 'toggle-archive'],
    ['remove', '删除', 'remove']
  ])('emits %s from its labelled control', async (_name, label, event) => {
    const wrapper = mountPanel({ threads: [thread()] })
    const button = wrapper.findAll('.thread-actions button').find(b => b.attributes('aria-label') === label)
    expect(button, `missing a control labelled ${label}`).toBeDefined()
    await button!.trigger('click')
    expect(wrapper.emitted(event)).toHaveLength(1)
    expect(wrapper.emitted(event)![0][0]).toMatchObject({ id: 'thread-1' })
  })

  it('uses the inverse label when a thread is already pinned or archived', () => {
    const wrapper = mountPanel({ threads: [thread({ pinned: true, archived: true })] })
    const labels = wrapper.findAll('.thread-actions button').map(b => b.attributes('aria-label'))
    expect(labels).toContain('取消置顶')
    expect(labels).toContain('取消归档')
  })

  it('stops the click on the action row from selecting the thread', async () => {
    // Without @click.stop, acting on a thread would also open it.
    const wrapper = mountPanel({ threads: [thread()] })
    await wrapper.find('.thread-actions').trigger('click')
    expect(wrapper.emitted('select')).toBeUndefined()
  })
})

describe('ChatThreadPanel search mode', () => {
  it('replaces the thread list with results when a search is active', () => {
    const wrapper = mountPanel({
      threads: [thread()],
      searchActive: true,
      searchResults: [{ thread_id: 'thread-9', message_id: 5, role: 'user', content: 'hello', created_at: '2026-01-01T00:00:00Z' }]
    })
    expect(wrapper.find('.search-results').exists()).toBe(true)
    expect(wrapper.find('.thread-list > .thread-item').exists()).toBe(false)
    expect(wrapper.text()).toContain('label:thread-9')
  })

  it('shows a searching state before results arrive', () => {
    expect(mountPanel({ searchActive: true, searching: true }).text()).toContain('搜索中')
  })

  it('shows an empty state when a search matched nothing', () => {
    expect(mountPanel({ searchActive: true, searchResults: [] }).text()).toContain('无匹配结果')
  })

  it('emits jump with the hit thread id', async () => {
    const wrapper = mountPanel({
      searchActive: true,
      searchResults: [{ thread_id: 'thread-9', message_id: 5, role: 'user', content: 'hi', created_at: '' }]
    })
    await wrapper.find('.search-results .thread-item').trigger('click')
    expect(wrapper.emitted('jump')).toEqual([['thread-9']])
  })
})

describe('ChatThreadPanel inputs', () => {
  it('emits toggle-archived with the change event', async () => {
    const wrapper = mountPanel()
    await wrapper.find('.thread-toggle input').trigger('change')
    expect(wrapper.emitted('toggle-archived')).toHaveLength(1)
  })

  it('reflects the includeArchived prop on the checkbox', () => {
    const wrapper = mountPanel({ includeArchived: true })
    expect((wrapper.find('.thread-toggle input').element as HTMLInputElement).checked).toBe(true)
  })
})
