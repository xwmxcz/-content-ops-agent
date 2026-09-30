import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Chat from '../src/views/Chat.vue'
import ChatThreadPanel from '../src/components/ChatThreadPanel.vue'
import { useChatStore } from '../src/stores/chat'
import type { AgentThread } from '../src/api/agent'

const api = vi.hoisted(() => ({ getAgentThreads: vi.fn(), getAgentMessages: vi.fn(), searchAgentMessages: vi.fn() }))
vi.mock('../src/api/agent', async original => ({ ...(await original<typeof import('../src/api/agent')>()), ...api }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }), useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }))
vi.mock('element-plus/es/components/message/index', () => ({ ElMessage: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

let wrapper: VueWrapper | undefined
const thread = (id: string): AgentThread => ({ id, title: id, message_count: 1, pinned: false, archived: false, title_pinned: false })
function open() {
  wrapper = shallowMount(Chat, {
    global: {
      plugins: [createPinia()],
      stubs: {
        'el-button': { template: '<button><slot /></button>' },
        'el-input': true, 'el-icon': true
      }
    }
  })
  return { view: wrapper, store: useChatStore() }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

beforeEach(() => {
  vi.useFakeTimers()
  sessionStorage.clear()
  setActivePinia(createPinia())
  api.getAgentThreads.mockReset().mockResolvedValue([])
  api.getAgentMessages.mockReset().mockResolvedValue([])
  api.searchAgentMessages.mockReset().mockResolvedValue([])
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.useRealTimers() })

describe('chat page search lifecycle', () => {
  it('invalidates the previous query immediately and only requests the debounced final input', async () => {
    const { view, store } = open()
    await flushPromises()
    const panel = view.findComponent(ChatThreadPanel)
    panel.vm.$emit('search-input', 'first')
    expect(store.searchQuery).toBe('first')
    await vi.advanceTimersByTimeAsync(150)
    panel.vm.$emit('search-input', 'latest')
    await vi.advanceTimersByTimeAsync(249)
    expect(api.searchAgentMessages).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(api.searchAgentMessages).toHaveBeenCalledExactlyOnceWith('latest', { limit: 30 })
  })

  it.each(['clear', 'new', 'jump', 'unmount'])('cancels the pending search on %s', async action => {
    const { view, store } = open()
    await flushPromises()
    const panel = view.findComponent(ChatThreadPanel)
    panel.vm.$emit('search-input', 'pending')
    if (action === 'clear') panel.vm.$emit('search-clear')
    if (action === 'new') await view.findAll('button').find(button => button.text() === '新建会话')!.trigger('click')
    if (action === 'jump') panel.vm.$emit('jump', 'selected')
    if (action === 'unmount') { view.unmount(); wrapper = undefined }
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    expect(api.searchAgentMessages).not.toHaveBeenCalled()
    expect(store.searchQuery).toBe('')
    expect(store.searching).toBe(false)
  })

  it('does not reopen the stored conversation when the user starts a new one during initial load', async () => {
    sessionStorage.setItem('chat:activeThreadId', 'old')
    const list = deferred<AgentThread[]>()
    api.getAgentThreads.mockReturnValueOnce(list.promise)
    const { view, store } = open()
    await view.findAll('button').find(button => button.text() === '新建会话')!.trigger('click')
    list.resolve([thread('old')])
    await flushPromises()

    expect(api.getAgentMessages).not.toHaveBeenCalled()
    expect(store.activeThreadId).toBeUndefined()
  })

  it('restores an existing conversation beyond the first sidebar page', async () => {
    sessionStorage.setItem('chat:activeThreadId', 'older')
    api.getAgentThreads.mockResolvedValueOnce(Array.from({ length: 30 }, (_, index) => thread(String(index))))
    api.getAgentMessages.mockResolvedValueOnce([{ id: 1, thread_id: 'older', role: 'user', content: 'saved message' }])
    const { store } = open()
    await flushPromises()

    expect(api.getAgentMessages).toHaveBeenCalledWith('older', { limit: 200 })
    expect(store.activeThreadId).toBe('older')
    expect(store.messages[0].content).toBe('saved message')
  })
})
