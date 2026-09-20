import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { AgentMessage, ChatResponse, ChatStreamHandlers, ChatToolEvent } from '../src/api/agent'
import {
  chat,
  chatStream,
  ChatStreamInterruptedError,
  ChatStreamUnavailableError,
  getAgentMessages,
  getAgentThreads
} from '../src/api/agent'
import { ApiError } from '../src/api'
import { useChatStore } from '../src/stores/chat'

// The real module is kept for its error classes: the store branches on instanceof.
vi.mock('../src/api/agent', async importOriginal => ({
  ...(await importOriginal<typeof import('../src/api/agent')>()),
  chat: vi.fn(),
  chatStream: vi.fn(),
  getAgentMessages: vi.fn(),
  getAgentThreads: vi.fn(),
  deleteAgentThread: vi.fn(),
  searchAgentMessages: vi.fn(),
  updateAgentThread: vi.fn()
}))

/** Drives the store the way the stream does: handlers first, then the verdict. */
function streamThat(script: (handlers: ChatStreamHandlers) => Promise<ChatResponse> | ChatResponse) {
  vi.mocked(chatStream).mockImplementation(async (_payload, handlers = {}) => script(handlers))
}

function toolEvent(name: string): ChatToolEvent {
  return { name, args: {}, output: 'ok', status: 'completed' }
}

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
    // Events keep arriving for the thread the user has already left.
    streamThat(async handlers => {
      handlers.onTurnStart?.({ thread_id: 'old', provider: 'test', model: 'test' })
      const result = await reply.promise
      handlers.onToken?.('late text')
      return result
    })
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
    streamThat(() => response('created'))
    const store = useChatStore()
    await store.sendMessage(payload)

    expect(store.activeThreadId).toBe('created')
    expect(store.messages.map(row => row.content)).toEqual(['hello', 'reply'])
    expect(sessionStorage.getItem('chat:activeThreadId')).toBe('created')
    expect(store.sending).toBe(false)
  })
})

describe('streamed replies', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    sessionStorage.clear()
    setActivePinia(createPinia())
    vi.mocked(getAgentThreads).mockResolvedValue([])
  })

  it('grows one draft as tokens arrive, then settles on the server response in place', async () => {
    const store = useChatStore()
    const snapshots: Array<{ content: string; streaming?: boolean }> = []
    let draftKey: string | undefined
    streamThat(handlers => {
      handlers.onTurnStart?.({ thread_id: 't1', provider: 'test', model: 'test' })
      handlers.onToken?.('Hel')
      handlers.onToken?.('lo')
      const draft = store.messages[store.messages.length - 1]
      draftKey = draft.local_id
      snapshots.push({ content: draft.content, streaming: draft.streaming })
      return { ...response('t1'), response: 'Hello.' }
    })

    await store.sendMessage(payload)

    expect(snapshots).toEqual([{ content: 'Hel' + 'lo', streaming: true }])
    expect(store.messages).toHaveLength(2)
    const reply = store.messages[1]
    // What the server persisted wins over what was streamed.
    expect(reply.content).toBe('Hello.')
    expect(reply.streaming).toBe(false)
    expect(reply.id).toBe(2)
    // Same v-for key as the draft, so the bubble being read is not re-created.
    expect(reply.local_id).toBe(draftKey)
  })

  it('withdraws text that preceded a tool call and shows the tool while it runs', async () => {
    const store = useChatStore()
    const seen: Array<{ content: string; activeTool?: string; tools: number }> = []
    const capture = () => {
      const draft = store.messages[store.messages.length - 1]
      seen.push({ content: draft.content, activeTool: draft.activeTool, tools: draft.tool_events?.length ?? 0 })
    }
    streamThat(handlers => {
      handlers.onToken?.('Let me check. ')
      handlers.onDraftReset?.()
      handlers.onToolStart?.({ name: 'search_history', args: {}, attempt: 1 })
      capture()
      handlers.onToolEnd?.(toolEvent('search_history'))
      handlers.onToken?.('Found it.')
      capture()
      return { ...response('t1'), response: 'Found it.', tool_events: [toolEvent('search_history')] }
    })

    await store.sendMessage(payload)

    expect(seen).toEqual([
      { content: '', activeTool: 'search_history', tools: 0 },
      { content: 'Found it.', activeTool: undefined, tools: 1 }
    ])
    expect(store.messages[1].tool_events).toHaveLength(1)
  })

  it('falls back to the plain endpoint only when no turn can have started', async () => {
    vi.mocked(chatStream).mockRejectedValue(new ChatStreamUnavailableError('no chat stream'))
    vi.mocked(chat).mockResolvedValue(response('plain'))
    const store = useChatStore()

    await store.sendMessage(payload)

    expect(chat).toHaveBeenCalledOnce()
    expect(store.messages.map(row => row.content)).toEqual(['hello', 'reply'])
  })

  it('does not resend the message after an ordinary failure', async () => {
    vi.mocked(chatStream).mockRejectedValue(new ApiError('上游模型或服务调用失败', 502))
    const store = useChatStore()

    await expect(store.sendMessage(payload)).rejects.toThrow('上游模型或服务调用失败')

    expect(chat).not.toHaveBeenCalled()
    expect(store.sending).toBe(false)
  })

  it('drops the half-written draft and keeps the thread when the connection is lost mid-reply', async () => {
    const store = useChatStore()
    streamThat(handlers => {
      handlers.onTurnStart?.({ thread_id: 'still-running', provider: 'test', model: 'test' })
      handlers.onToken?.('Half of an ans')
      throw new ChatStreamInterruptedError('still-running')
    })

    await expect(store.sendMessage(payload)).rejects.toBeInstanceOf(ChatStreamInterruptedError)

    // The turn is still running server-side: resending would duplicate it.
    expect(chat).not.toHaveBeenCalled()
    expect(store.messages.map(row => row.content)).toEqual(['hello'])
    expect(store.activeThreadId).toBe('still-running')
    expect(store.sending).toBe(false)
  })
})
