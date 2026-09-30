// Owns chat state; message responses only update the context that requested them.
import { defineStore } from 'pinia'
import { readActiveThreadFromStorage, writeActiveThreadToStorage } from '../workspaceSession'
import {
  chat,
  chatStream,
  ChatStreamInterruptedError,
  ChatStreamUnavailableError,
  deleteAgentThread,
  getAgentMessages,
  getAgentThreads,
  searchAgentMessages,
  updateAgentThread,
  type AgentMessage,
  type AgentSearchHit,
  type AgentThread,
  type ChatIntent,
  type ChatPayload,
  type ChatResponse,
  type ChatToolEvent,
  type PlanStep,
  type UpdateThreadPatch
} from '../api/agent'

export type UiMessage = Partial<AgentMessage> & {
  local_id?: string
  role: 'user' | 'assistant'
  content: string
  pending?: boolean
  /** The reply is still arriving; `content` and `tool_events` grow in place. */
  streaming?: boolean
  /** The tool the agent is waiting on, while `streaming`. */
  activeTool?: string
  intent?: ChatIntent | null
  tool_events?: ChatToolEvent[]
  plan?: PlanStep[]
}

const THREAD_PAGE_SIZE = 30
const MESSAGE_PAGE_SIZE = 200

export const useChatStore = defineStore('chat', {
  state: () => ({
    threads: [] as AgentThread[],
    activeThreadId: readActiveThreadFromStorage() as string | undefined,
    messages: [] as UiMessage[],
    messageContextVersion: 0,
    threadsRequestVersion: 0,
    searchRequestVersion: 0,
    threadsOffset: 0,
    threadsLoading: false,
    threadsError: '',
    messagesLoading: false,
    sending: false,
    hasMoreThreads: false,
    hasMoreMessages: false,
    includeArchived: false,
    searchQuery: '',
    searchResults: [] as AgentSearchHit[],
    searching: false,
    searchError: '',
    mutatingThreadIds: [] as string[]
  }),
  getters: {
    activeThread(state): AgentThread | undefined {
      return state.threads.find(thread => thread.id === state.activeThreadId)
    }
  },
  actions: {
    invalidateThreadReads() {
      this.threadsRequestVersion += 1
      this.threadsLoading = false
    },
    async loadThreads(_options: { reset?: boolean } = {}) {
      const request = ++this.threadsRequestVersion
      const includeArchived = this.includeArchived
      this.threadsLoading = true
      this.threadsError = ''
      try {
        const rows = await getAgentThreads({
          limit: THREAD_PAGE_SIZE,
          offset: 0,
          include_archived: includeArchived
        })
        if (request !== this.threadsRequestVersion || includeArchived !== this.includeArchived) return false
        this.threads = rows
        this.threadsOffset = rows.length
        this.hasMoreThreads = rows.length === THREAD_PAGE_SIZE
        return true
      } catch (error) {
        if (request === this.threadsRequestVersion) {
          this.threadsError = error instanceof Error ? error.message : '会话加载失败，请重试'
        }
        return false
      } finally {
        if (request === this.threadsRequestVersion) this.threadsLoading = false
      }
    },
    async loadMoreThreads() {
      if (!this.hasMoreThreads || this.threadsLoading || this.mutatingThreadIds.length) return
      const request = ++this.threadsRequestVersion
      const includeArchived = this.includeArchived
      this.threadsLoading = true
      this.threadsError = ''
      try {
        const rows = await getAgentThreads({
          limit: THREAD_PAGE_SIZE,
          offset: this.threadsOffset,
          include_archived: includeArchived
        })
        if (request !== this.threadsRequestVersion || includeArchived !== this.includeArchived) return
        this.threadsOffset += rows.length
        // Filter out any duplicates that could appear if a thread was updated
        // between requests (its updated_at could move it to an earlier page).
        const existing = new Set(this.threads.map(t => t.id))
        const fresh = rows.filter(r => !existing.has(r.id))
        this.threads.push(...fresh)
        this.hasMoreThreads = rows.length === THREAD_PAGE_SIZE
      } catch (error) {
        if (request === this.threadsRequestVersion) {
          this.threadsError = error instanceof Error ? error.message : '会话加载失败，请重试'
        }
      } finally {
        if (request === this.threadsRequestVersion) this.threadsLoading = false
      }
    },
    async setIncludeArchived(value: boolean) {
      if (this.includeArchived === value) return
      this.includeArchived = value
      this.threads = []
      this.hasMoreThreads = false
      this.threadsOffset = 0
      await this.loadThreads({ reset: true })
    },
    async selectThread(threadId: string | undefined) {
      const contextVersion = ++this.messageContextVersion
      this.activeThreadId = threadId
      writeActiveThreadToStorage(threadId)
      this.messages = []
      this.hasMoreMessages = false
      this.messagesLoading = Boolean(threadId)
      if (!threadId) {
        return
      }
      try {
        const rows = await getAgentMessages(threadId, { limit: MESSAGE_PAGE_SIZE })
        if (contextVersion !== this.messageContextVersion) return
        this.messages = rows as UiMessage[]
        // If we got a full page back, there *might* be older history to load.
        this.hasMoreMessages = rows.length === MESSAGE_PAGE_SIZE
      } finally {
        if (contextVersion === this.messageContextVersion) this.messagesLoading = false
      }
    },
    async loadOlderMessages() {
      if (!this.activeThreadId || !this.hasMoreMessages || this.messagesLoading) return
      const firstId = this.messages.find(m => typeof m.id === 'number')?.id as number | undefined
      if (!firstId) return
      const contextVersion = this.messageContextVersion
      this.messagesLoading = true
      try {
        const older = await getAgentMessages(this.activeThreadId, {
          limit: MESSAGE_PAGE_SIZE,
          before_id: firstId
        })
        if (contextVersion !== this.messageContextVersion) return
        if (!older.length) {
          this.hasMoreMessages = false
          return
        }
        this.messages = [...(older as UiMessage[]), ...this.messages]
        this.hasMoreMessages = older.length === MESSAGE_PAGE_SIZE
      } finally {
        if (contextVersion === this.messageContextVersion) this.messagesLoading = false
      }
    },
    startNewThread() {
      this.messageContextVersion += 1
      this.activeThreadId = undefined
      writeActiveThreadToStorage(undefined)
      this.messages = []
      this.hasMoreMessages = false
      this.messagesLoading = false
    },
    async sendMessage(payload: Omit<ChatPayload, 'thread_id'>) {
      if (this.sending) return
      this.invalidateThreadReads()
      const contextVersion = this.messageContextVersion
      const inContext = () => contextVersion === this.messageContextVersion
      const localMessage: UiMessage = {
        local_id: `local-${Date.now()}`,
        role: 'user',
        content: payload.message,
        provider: payload.provider,
        model: payload.model,
        pending: true,
        tool_events: []
      }
      this.messages.push(localMessage)
      this.sending = true
      const request = { ...payload, thread_id: this.activeThreadId }

      // The reply is rendered from a draft that grows as events arrive. It is read
      // back out of the array so writes go through the reactive proxy; mutating the
      // plain object would not repaint. If the user switched threads, the events
      // belong to a view that is gone and are dropped.
      let draft: UiMessage | undefined
      const currentDraft = () => {
        if (!inContext()) return undefined
        if (!draft) {
          this.messages.push({ local_id: `draft-${Date.now()}`, role: 'assistant', content: '', streaming: true, tool_events: [] })
          draft = this.messages[this.messages.length - 1]
        }
        return draft
      }
      const discardDraft = () => {
        if (draft && inContext()) this.messages = this.messages.filter(message => message.local_id !== draft?.local_id)
        draft = undefined
      }

      try {
        let result: ChatResponse
        try {
          result = await chatStream(request, {
            onTurnStart: info => {
              const target = currentDraft()
              if (target) Object.assign(target, { provider: info.provider, model: info.model })
            },
            onIntent: intent => {
              const target = currentDraft()
              if (target) target.intent = intent
            },
            onPlan: plan => {
              const target = currentDraft()
              if (target) target.plan = plan
            },
            onToken: delta => {
              const target = currentDraft()
              if (target) target.content += delta
            },
            onDraftReset: () => {
              const target = currentDraft()
              if (target) target.content = ''
            },
            onToolStart: call => {
              const target = currentDraft()
              if (target) target.activeTool = call.name
            },
            onToolEnd: event => {
              const target = currentDraft()
              if (!target) return
              target.activeTool = undefined
              target.tool_events = [...(target.tool_events ?? []), event]
            }
          })
        } catch (error) {
          // Only when no turn can have started; see ChatStreamUnavailableError.
          if (!(error instanceof ChatStreamUnavailableError)) throw error
          discardDraft()
          result = await chat(request)
        }
        localMessage.pending = false
        if (inContext()) {
          this.activeThreadId = result.thread_id
          writeActiveThreadToStorage(result.thread_id)
          // The server's response is authoritative: it replaces whatever was streamed.
          const final: UiMessage = {
            id: result.message_id,
            thread_id: result.thread_id,
            role: 'assistant',
            content: result.response,
            provider: result.provider,
            model: result.model,
            intent: result.intent,
            tool_events: result.tool_events,
            plan: result.plan,
            status: 'completed',
            streaming: false,
            activeTool: undefined
          }
          const target = currentDraft()
          // Updated in place so the bubble the user is reading is not re-created.
          if (target) Object.assign(target, final)
          else this.messages.push(final)
        }
        // List failures belong to the sidebar. They must never discard a reply
        // which has already completed and been persisted by the server.
        await this.loadThreads({ reset: true })
      } catch (error) {
        localMessage.pending = false
        discardDraft()
        if (error instanceof ChatStreamInterruptedError && inContext()) {
          // The turn is still running server-side and will be saved to this thread.
          this.activeThreadId = error.threadId
          writeActiveThreadToStorage(error.threadId)
        }
        throw error
      } finally {
        this.sending = false
      }
    },
    async renameThread(threadId: string, title: string) {
      const trimmed = title.trim()
      if (!trimmed) return
      await this.patchThread(threadId, { title: trimmed })
    },
    async togglePin(threadId: string) {
      const thread = this.threads.find(t => t.id === threadId)
      if (!thread) return
      await this.patchThread(threadId, { pinned: !thread.pinned })
    },
    async toggleArchive(threadId: string) {
      const thread = this.threads.find(t => t.id === threadId)
      if (!thread) return
      await this.patchThread(threadId, { archived: !thread.archived })
    },
    async patchThread(threadId: string, patch: UpdateThreadPatch) {
      if (this.mutatingThreadIds.includes(threadId)) return
      this.mutatingThreadIds.push(threadId)
      this.invalidateThreadReads()
      try {
        const updated = await updateAgentThread(threadId, patch)
        this.invalidateThreadReads()
        this.hasMoreThreads = false
        if (updated.archived && !this.includeArchived) {
          this.threads = this.threads.filter(thread => thread.id !== threadId)
        } else {
          const index = this.threads.findIndex(t => t.id === threadId)
          if (index >= 0) this.threads[index] = updated
        }
        // All edits can change ordering, including a title edit's updated_at.
        await this.loadThreads({ reset: true })
      } finally {
        this.mutatingThreadIds = this.mutatingThreadIds.filter(id => id !== threadId)
      }
    },
    async removeThread(threadId: string) {
      if (this.mutatingThreadIds.includes(threadId)) return
      this.mutatingThreadIds.push(threadId)
      this.invalidateThreadReads()
      try {
        await deleteAgentThread(threadId)
        this.invalidateThreadReads()
        this.hasMoreThreads = false
        this.threads = this.threads.filter(thread => thread.id !== threadId)
        this.searchRequestVersion += 1
        this.searching = false
        this.searchResults = this.searchResults.filter(hit => hit.thread_id !== threadId)
        if (this.activeThreadId === threadId) this.startNewThread()
        await Promise.all([
          this.loadThreads({ reset: true }),
          this.searchQuery ? this.runSearch(this.searchQuery) : Promise.resolve()
        ])
      } finally {
        this.mutatingThreadIds = this.mutatingThreadIds.filter(id => id !== threadId)
      }
    },
    prepareSearch(query: string) {
      this.searchRequestVersion += 1
      this.searchQuery = query.trim()
      this.searchResults = []
      this.searchError = ''
      this.searching = Boolean(this.searchQuery)
    },
    async runSearch(query: string) {
      this.prepareSearch(query)
      const request = this.searchRequestVersion
      const q = this.searchQuery
      if (!q) return
      try {
        const results = await searchAgentMessages(q, { limit: 30 })
        if (request === this.searchRequestVersion && q === this.searchQuery) this.searchResults = results
      } catch (error) {
        if (request === this.searchRequestVersion) {
          this.searchError = error instanceof Error ? error.message : '搜索失败，请重试'
        }
      } finally {
        if (request === this.searchRequestVersion) this.searching = false
      }
    },
    clearSearch() {
      this.prepareSearch('')
    }
  }
})
