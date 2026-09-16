import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { AgentMessage, ChatResponse } from '../src/api/agent'
import { chat, getAgentMessages, getAgentThreads } from '../src/api/agent'
import { useChatStore } from '../src/stores/chat'

vi.mock('../src/api/agent', () => ({
  chat: vi.fn(),
  getAgentMessages: vi.fn(),
  getAgentThreads: vi.fn(),
  deleteAgentThread: vi.fn(),
  searchAgentMessages: vi.fn(),
  updateAgentThread: vi.fn()
}))

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

function message(threadId: string, id = 1): AgentMessage {
  return {
    id, thread_id: threadId, role: 'assistant', content: `${threadId}-${id}`,
    tool_events: [], plan: [], status: 'completed'
  }
}

function response(threadId: string): ChatResponse {
  return {
    message_id: 2, thread_id: threadId, response: 'reply',
    provider: 'test', model: 'test', tool_events: [], plan: []
  }
}

const payload = { message: 'hello', temperature: 0.7, max_tokens: 100 }

describe('chat message context', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    sessionStorage.clear()
    setActivePinia(createPinia())
    vi.mocked(getAgentThreads).mockResolvedValue([])
  })

  it.each(['old-first', 'new-first'])('keeps the latest selection when requests finish %s', async order => {
    const oldRequest = deferred<AgentMessage[]>()
    const newRequest = deferred<AgentMessage[]>()
    vi.mocked(getAgentMessages)
      .mockReturnValueOnce(oldRequest.promise)
      .mockReturnValueOnce(newRequest.promise)
    const store = useChatStore()
    const oldSelection = store.selectThread('old')
    const newSelection = store.selectThread('new')

    if (order === 'old-first') {
      oldRequest.resolve([message('old')])
      await oldSelection
      expect(store.messages).toEqual([])
      expect(store.messagesLoading).toBe(true)
    }
    newRequest.resolve([message('new')])
    await newSelection
    oldRequest.resolve([message('old')])
    await oldSelection

    expect(store.activeThreadId).toBe('new')
    expect(store.messages).toEqual([message('new')])
    expect(store.messagesLoading).toBe(false)
  })

  it('ignores an old request even after returning to the same thread', async () => {
    const oldRequest = deferred<AgentMessage[]>()
    vi.mocked(getAgentMessages)
      .mockReturnValueOnce(oldRequest.promise)
      .mockResolvedValueOnce([message('other')])
      .mockResolvedValueOnce([message('same', 2)])
    const store = useChatStore()
    const oldSelection = store.selectThread('same')
    await store.selectThread('other')
    await store.selectThread('same')
    oldRequest.resolve([message('same', 1)])
    await oldSelection

    expect(store.messages).toEqual([message('same', 2)])
  })

  it.each(['new-thread', 'clear-selection'])('invalidates message loading on %s', async action => {
    const request = deferred<AgentMessage[]>()
    vi.mocked(getAgentMessages).mockReturnValue(request.promise)
    const store = useChatStore()
    const selection = store.selectThread('old')
    if (action === 'new-thread') store.startNewThread()
    else await store.selectThread(undefined)

    expect(store.messagesLoading).toBe(false)
    request.resolve([message('old')])
    await selection
    expect(store.activeThreadId).toBeUndefined()
    expect(store.messages).toEqual([])
    expect(store.hasMoreMessages).toBe(false)
  })

  it('does not prepend old history or clear loading for the newly selected thread', async () => {
    const older = deferred<AgentMessage[]>()
    const selection = deferred<AgentMessage[]>()
    vi.mocked(getAgentMessages)
      .mockResolvedValueOnce([message('old', 10)])
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(selection.promise)
    const store = useChatStore()
    await store.selectThread('old')
    store.hasMoreMessages = true
    const loadingOlder = store.loadOlderMessages()
    const selecting = store.selectThread('new')
    older.resolve([message('old', 9)])
    await loadingOlder

    expect(store.messages).toEqual([])
    expect(store.hasMoreMessages).toBe(false)
    expect(store.messagesLoading).toBe(true)
    selection.resolve([message('new')])
    await selecting
    expect(store.messages).toEqual([message('new')])
  })

  it.each(['switch-thread', 'new-thread'])('keeps the current context when a reply arrives after %s', async action => {
    const reply = deferred<ChatResponse>()
    vi.mocked(chat).mockReturnValue(reply.promise)
    vi.mocked(getAgentMessages).mockResolvedValue([message('new')])
    const store = useChatStore()
    const sending = store.sendMessage(payload)
    if (action === 'switch-thread') await store.selectThread('new')
    else store.startNewThread()

    reply.resolve(response('old'))
    await sending

    expect(store.activeThreadId).toBe(action === 'switch-thread' ? 'new' : undefined)
    expect(store.messages).toEqual(action === 'switch-thread' ? [message('new')] : [])
    expect(sessionStorage.getItem('chat:activeThreadId')).toBe(action === 'switch-thread' ? 'new' : null)
    expect(store.sending).toBe(false)
    expect(getAgentThreads).toHaveBeenCalledOnce()
  })

  it('still adopts a new thread and appends its reply when the context is unchanged', async () => {
    vi.mocked(chat).mockResolvedValue(response('created'))
    const store = useChatStore()
    await store.sendMessage(payload)

    expect(store.activeThreadId).toBe('created')
    expect(store.messages.map(row => row.content)).toEqual(['hello', 'reply'])
    expect(sessionStorage.getItem('chat:activeThreadId')).toBe('created')
    expect(store.sending).toBe(false)
  })
})
