import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import Memory from '../src/views/Memory.vue'
import { activateWorkspaceSession, clearWorkspaceSession } from '../src/workspaceSession'
import type { MemoryFile, SessionSearchResult } from '../src/api/memory'

const mocks = vi.hoisted(() => ({
  getAgentMemory: vi.fn(), saveAgentMemory: vi.fn(), getUserMemory: vi.fn(), saveUserMemory: vi.fn(),
  searchSessions: vi.fn(), refreshSnapshot: vi.fn(), success: vi.fn(), error: vi.fn(), confirm: vi.fn(), leave: vi.fn()
}))
vi.mock('../src/api/memory', () => mocks)
vi.mock('element-plus/es/components/message/index', () => ({ ElMessage: mocks }))
vi.mock('element-plus/es/components/message-box/index', () => ({ ElMessageBox: mocks }))
vi.mock('vue-router', () => ({ onBeforeRouteLeave: mocks.leave }))
const input = defineComponent({
  props: ['modelValue', 'disabled'], emits: ['update:modelValue'],
  setup(props, { emit }) {
    return () => h('textarea', { value: props.modelValue, disabled: props.disabled,
      onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLTextAreaElement).value) })
  }
})
const memory = (content: string, limit = 2200): MemoryFile => ({ content, char_count: [...content].length, char_limit: limit })
const wrappers: ReturnType<typeof shallowMount>[] = []
function mountMemory() {
  const wrapper = shallowMount(Memory, { global: { renderStubDefaultSlot: true, stubs: {
    'el-input': input, 'el-button': { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' }
  } } })
  wrappers.push(wrapper)
  return wrapper
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}
const save = (wrapper: ReturnType<typeof mountMemory>) => wrapper.findAll('button').filter(button => button.text() === '保存')[0]
const search = (wrapper: ReturnType<typeof mountMemory>) => wrapper.findAll('button').find(button => button.text() === '搜索')!
const value = (wrapper: ReturnType<typeof mountMemory>) => (wrapper.get('[aria-label="工作笔记"]').element as HTMLTextAreaElement).value
beforeEach(() => {
  clearWorkspaceSession(); activateWorkspaceSession()
  mocks.getAgentMemory.mockResolvedValue(memory('原记忆'))
  mocks.getUserMemory.mockResolvedValue(memory('用户偏好', 1375))
  mocks.saveAgentMemory.mockImplementation(async (content: string) => memory(content))
  mocks.confirm.mockResolvedValue('confirm')
  mocks.searchSessions.mockResolvedValue({ messages: [], count: 0 })
})
afterEach(() => wrappers.splice(0).forEach(wrapper => wrapper.unmount()))

describe('memory draft and search reliability', () => {
  it('keeps newer typing during save and prevents double submission', async () => {
    const pending = deferred<MemoryFile>()
    mocks.saveAgentMemory.mockReturnValueOnce(pending.promise)
    const wrapper = mountMemory()
    await flushPromises()
    await wrapper.get('[aria-label="工作笔记"]').setValue('提交的内容')
    await save(wrapper).trigger('click')
    await wrapper.get('[aria-label="工作笔记"]').setValue('保存期间继续输入')
    await save(wrapper).trigger('click')
    expect(mocks.saveAgentMemory).toHaveBeenCalledExactlyOnceWith('提交的内容')
    pending.resolve(memory('提交的内容'))
    await flushPromises()
    expect(value(wrapper)).toBe('保存期间继续输入')
    expect(wrapper.text()).toContain('有未保存的修改')
    await save(wrapper).trigger('click')
    await flushPromises()
    expect(mocks.saveAgentMemory).toHaveBeenLastCalledWith('保存期间继续输入')
  })

  it('does not allow saving an empty fallback after a failed initial load', async () => {
    mocks.getAgentMemory.mockRejectedValueOnce(new Error('记忆服务未启用'))
    const wrapper = mountMemory()
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('记忆服务未启用')
    expect(save(wrapper).attributes('disabled')).toBeDefined()
    expect(wrapper.get('[aria-label="工作笔记"]').attributes('disabled')).toBeDefined()
    const reload = wrapper.findAll('button').filter(button => button.text() === '重新加载')[0]
    await reload.trigger('click')
    await flushPromises()
    expect(value(wrapper)).toBe('原记忆')
  })

  it('shows actual save errors and preserves unsaved input', async () => {
    mocks.saveAgentMemory.mockRejectedValueOnce(new Error('超过记忆存储上限'))
    const wrapper = mountMemory()
    await flushPromises()
    await wrapper.get('[aria-label="工作笔记"]').setValue('待保存')
    await save(wrapper).trigger('click')
    await flushPromises()
    expect(value(wrapper)).toBe('待保存')
    expect(wrapper.get('[role="alert"]').text()).toBe('超过记忆存储上限')
    mocks.confirm.mockRejectedValueOnce('cancel')
    expect(await mocks.leave.mock.calls[0][0]()).toBe(false)
  })

  it('counts emoji the same way as the Python character limit', async () => {
    mocks.getAgentMemory.mockResolvedValueOnce(memory('', 2))
    const wrapper = mountMemory()
    await flushPromises()
    await wrapper.get('[aria-label="工作笔记"]').setValue('😀😀')
    expect(wrapper.findAll('.count')[0].text()).toBe('2 / 2')
    expect(save(wrapper).attributes('disabled')).toBeUndefined()
  })

  it('discards previous-account reads even when the transport ignores cancellation', async () => {
    const pending = deferred<MemoryFile>()
    mocks.getAgentMemory.mockReturnValueOnce(pending.promise)
    const wrapper = mountMemory()
    clearWorkspaceSession()
    mocks.getAgentMemory.mockResolvedValue(memory('新工作区'))
    activateWorkspaceSession()
    await flushPromises()
    pending.resolve(memory('旧工作区私有内容'))
    await flushPromises()
    expect(value(wrapper)).toBe('新工作区')
    expect(wrapper.text()).not.toContain('旧工作区私有内容')
  })

  it('ignores older search results and clearing the query retires pending searches', async () => {
    const first = deferred<SessionSearchResult>()
    const second = deferred<SessionSearchResult>()
    mocks.searchSessions.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const wrapper = mountMemory()
    const query = wrapper.get('.search-keyword')
    await query.setValue('第一次')
    await search(wrapper).trigger('click')
    await query.setValue('第二次')
    await search(wrapper).trigger('click')
    second.resolve({ messages: [{ id: 2, thread_id: 'two', role: 'user', content: '新搜索结果' }], count: 1 })
    await flushPromises()
    first.resolve({ messages: [{ id: 1, thread_id: 'one', role: 'user', content: '旧搜索结果' }], count: 1 })
    await flushPromises()
    expect(wrapper.findAll('.hit-content').map(hit => hit.text())).toEqual(['新搜索结果'])
    const third = deferred<SessionSearchResult>()
    mocks.searchSessions.mockReturnValueOnce(third.promise)
    await search(wrapper).trigger('click')
    await query.setValue('')
    third.resolve({ messages: [{ id: 3, thread_id: 'one', role: 'user', content: '清空后迟到' }], count: 1 })
    await flushPromises()
    expect(wrapper.findAll('.hit-card')).toHaveLength(0)
    expect(wrapper.text()).toContain('输入关键词')
  })

  it('separates a search failure from an empty result', async () => {
    mocks.searchSessions.mockRejectedValueOnce(new Error('搜索服务暂时不可用'))
    const wrapper = mountMemory()
    await wrapper.get('.search-keyword').setValue('内容')
    await search(wrapper).trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('搜索服务暂时不可用')
    expect(wrapper.text()).not.toContain('还没有找到相关消息')
  })
})
