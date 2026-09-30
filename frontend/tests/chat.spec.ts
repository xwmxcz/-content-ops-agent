import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { AgentMessage, AgentSearchHit, AgentThread, ChatResponse, ChatStreamHandlers, ChatToolEvent } from '../src/api/agent'
import {
  chat,
  chatStream,
  ChatStreamInterruptedError,
  ChatStreamUnavailableError,
  getAgentMessages,
  getAgentThreads,
  deleteAgentThread,
  searchAgentMessages,
  updateAgentThread
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
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
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

  it('keeps the completed reply when the subsequent sidebar refresh fails', async () => {
    streamThat(handlers => {
      handlers.onToken?.('reply')
      return response('saved')
    })
    vi.mocked(getAgentThreads).mockRejectedValue(new Error('列表服务不可用'))
    const store = useChatStore()

    await expect(store.sendMessage(payload)).resolves.toBeUndefined()

    expect(store.messages.map(row => row.content)).toEqual(['hello', 'reply'])
    expect(store.messages[1]).toMatchObject({ status: 'completed', streaming: false })
    expect(store.activeThreadId).toBe('saved')
    expect(store.threadsError).toBe('列表服务不可用')
    expect(chatStream).toHaveBeenCalledOnce()
  })
})

const thread = (id: string, overrides: Partial<AgentThread> = {}): AgentThread => ({
  id, title: id, message_count: 1, pinned: false, archived: false, title_pinned: false, ...overrides
})
const searchHit = (id: string): AgentSearchHit => ({ message_id: 1, thread_id: id, role: 'user', content: id })

describe('chat sidebar request isolation', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    sessionStorage.clear()
    setActivePinia(createPinia())
    vi.mocked(getAgentThreads).mockResolvedValue([])
    vi.mocked(searchAgentMessages).mockResolvedValue([])
  })

  it('only applies the latest refresh and keeps its loading state until it completes', async () => {
    const first = deferred<AgentThread[]>()
    const latest = deferred<AgentThread[]>()
    vi.mocked(getAgentThreads).mockReturnValueOnce(first.promise).mockReturnValueOnce(latest.promise)
    const store = useChatStore()
    const oldLoad = store.loadThreads()
    const newLoad = store.loadThreads()
    first.resolve([thread('old')])
    await oldLoad
    expect(store.threadsLoading).toBe(true)
    expect(store.threads).toEqual([])
    latest.resolve([thread('latest')])
    await newLoad
    expect(store.threads.map(item => item.id)).toEqual(['latest'])
    expect(store.threadsLoading).toBe(false)
  })

  it('ignores late archive-filter results even after the filter returns to its original value', async () => {
    const first = deferred<AgentThread[]>()
    const archived = deferred<AgentThread[]>()
    vi.mocked(getAgentThreads)
      .mockReturnValueOnce(first.promise).mockReturnValueOnce(archived.promise)
      .mockResolvedValueOnce([thread('current')])
    const store = useChatStore()
    const initial = store.loadThreads()
    const includingArchived = store.setIncludeArchived(true)
    await store.setIncludeArchived(false)
    archived.resolve([thread('archived', { archived: true })])
    first.resolve([thread('old')])
    await Promise.all([initial, includingArchived])

    expect(store.includeArchived).toBe(false)
    expect(store.threads.map(item => item.id)).toEqual(['current'])
    expect(vi.mocked(getAgentThreads).mock.calls.map(call => call[0]?.include_archived)).toEqual([false, true, false])
  })

  it('does not append a stale next page after refreshing the list', async () => {
    const page = deferred<AgentThread[]>()
    vi.mocked(getAgentThreads)
      .mockResolvedValueOnce(Array.from({ length: 30 }, (_, index) => thread(String(index))))
      .mockReturnValueOnce(page.promise).mockResolvedValueOnce([thread('new')])
    const store = useChatStore()
    await store.loadThreads()
    const more = store.loadMoreThreads()
    await store.loadThreads()
    page.resolve([thread('stale-page')])
    await more
    expect(store.threads.map(item => item.id)).toEqual(['new'])
    expect(store.hasMoreThreads).toBe(false)
  })

  it('advances the server offset by fetched rows even when overlapping pages are deduplicated', async () => {
    const page = Array.from({ length: 30 }, (_, index) => thread(String(index)))
    vi.mocked(getAgentThreads).mockResolvedValueOnce(page).mockResolvedValueOnce(page).mockResolvedValueOnce([])
    const store = useChatStore()
    await store.loadThreads()
    await store.loadMoreThreads()
    await store.loadMoreThreads()
    expect(store.threads).toHaveLength(30)
    expect(vi.mocked(getAgentThreads).mock.calls.map(call => call[0]?.offset)).toEqual([0, 30, 60])
  })

  it('retains loaded rows on failure, reports the error, and clears it after a successful retry', async () => {
    vi.mocked(getAgentThreads).mockResolvedValueOnce([thread('kept')]).mockRejectedValueOnce(new Error('离线')).mockResolvedValueOnce([])
    const store = useChatStore()
    await store.loadThreads()
    expect(await store.loadThreads()).toBe(false)
    expect(store.threadsError).toBe('离线')
    expect(store.threads.map(item => item.id)).toEqual(['kept'])
    await store.loadThreads()
    expect(store.threadsError).toBe('')
  })

  it('does not report a stale request failure over a successful refresh', async () => {
    const old = deferred<AgentThread[]>()
    vi.mocked(getAgentThreads).mockReturnValueOnce(old.promise).mockResolvedValueOnce([thread('latest')])
    const store = useChatStore()
    const pending = store.loadThreads()
    await store.loadThreads()
    old.reject(new Error('stale error'))
    await pending
    expect(store.threadsError).toBe('')
    expect(store.threads.map(item => item.id)).toEqual(['latest'])
  })

  it('a completed rename invalidates reads started before and during the mutation', async () => {
    const old = deferred<AgentThread[]>()
    const during = deferred<AgentThread[]>()
    const rename = deferred<AgentThread>()
    const renamed = thread('t1', { title: '新标题' })
    vi.mocked(getAgentThreads).mockReturnValueOnce(old.promise).mockReturnValueOnce(during.promise).mockResolvedValueOnce([renamed])
    vi.mocked(updateAgentThread).mockReturnValueOnce(rename.promise)
    const store = useChatStore()
    store.threads = [thread('t1')]
    const beforeLoad = store.loadThreads()
    const mutation = store.renameThread('t1', '新标题')
    const duringLoad = store.loadThreads()
    rename.resolve(renamed)
    await mutation
    old.resolve([thread('t1')])
    during.resolve([thread('t1')])
    await Promise.all([beforeLoad, duringLoad])
    expect(store.threads[0].title).toBe('新标题')
  })

  it('does not resurrect a deleted thread or search hit if the follow-up refresh fails', async () => {
    const old = deferred<AgentThread[]>()
    const oldSearch = deferred<AgentSearchHit[]>()
    vi.mocked(getAgentThreads).mockReturnValueOnce(old.promise).mockRejectedValueOnce(new Error('离线'))
    vi.mocked(searchAgentMessages).mockReturnValueOnce(oldSearch.promise).mockRejectedValueOnce(new Error('离线'))
    vi.mocked(deleteAgentThread).mockResolvedValueOnce({ deleted: true })
    const store = useChatStore()
    store.threads = [thread('removed')]
    store.activeThreadId = 'removed'
    const oldLoad = store.loadThreads()
    const searching = store.runSearch('removed')
    await store.removeThread('removed')
    old.resolve([thread('removed')])
    oldSearch.resolve([searchHit('removed')])
    await Promise.all([oldLoad, searching])
    expect(store.threads).toEqual([])
    expect(store.searchResults).toEqual([])
    expect(store.activeThreadId).toBeUndefined()
    expect(store.threadsError).toBe('离线')
  })

  it('does not replace a newly created conversation with a list response from before sending', async () => {
    const old = deferred<AgentThread[]>()
    vi.mocked(getAgentThreads).mockReturnValueOnce(old.promise).mockResolvedValueOnce([thread('created')])
    streamThat(() => response('created'))
    const store = useChatStore()
    const loading = store.loadThreads()
    await store.sendMessage(payload)
    old.resolve([])
    await loading
    expect(store.threads.map(item => item.id)).toEqual(['created'])
    expect(store.messages.map(item => item.content)).toEqual(['hello', 'reply'])
  })

  it('only accepts the latest query and keeps searching until that request finishes', async () => {
    const first = deferred<AgentSearchHit[]>()
    const second = deferred<AgentSearchHit[]>()
    vi.mocked(searchAgentMessages).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const store = useChatStore()
    const oldSearch = store.runSearch('old')
    const newSearch = store.runSearch('new')
    first.resolve([searchHit('old')])
    await oldSearch
    expect(store.searching).toBe(true)
    expect(store.searchResults).toEqual([])
    second.resolve([searchHit('new')])
    await newSearch
    expect(store.searchResults).toEqual([searchHit('new')])
    expect(store.searching).toBe(false)
  })

  it.each(['clear', 'debouncing'])('invalidates a running search immediately on %s', async action => {
    const first = deferred<AgentSearchHit[]>()
    vi.mocked(searchAgentMessages).mockReturnValueOnce(first.promise)
    const store = useChatStore()
    const oldSearch = store.runSearch('old')
    if (action === 'clear') store.clearSearch()
    else store.prepareSearch('new')
    first.resolve([searchHit('old')])
    await oldSearch
    expect(store.searchResults).toEqual([])
    expect(store.searchQuery).toBe(action === 'clear' ? '' : 'new')
    expect(store.searching).toBe(action !== 'clear')
  })

  it('reports a failed search without rejecting its debounced invocation', async () => {
    vi.mocked(searchAgentMessages).mockRejectedValueOnce(new Error('搜索失败')).mockResolvedValueOnce([searchHit('found')])
    const store = useChatStore()
    await expect(store.runSearch('needle')).resolves.toBeUndefined()
    expect(store.searchError).toBe('搜索失败')
    expect(store.searching).toBe(false)
    await store.runSearch('needle')
    expect(store.searchError).toBe('')
    expect(store.searchResults).toEqual([searchHit('found')])
  })
})
