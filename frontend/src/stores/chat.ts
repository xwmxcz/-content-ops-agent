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
    threadsLoading: false,
    messagesLoading: false,
    sending: false,
    hasMoreThreads: false,
    hasMoreMessages: false,
    includeArchived: false,
    searchQuery: '',
    searchResults: [] as AgentSearchHit[],
    searching: false
  }),
  getters: {
    activeThread(state): AgentThread | undefined {
      return state.threads.find(thread => thread.id === state.activeThreadId)
    }
  },
  actions: {
    async loadThreads(options: { reset?: boolean } = {}) {
      this.threadsLoading = true
      try {
        const offset = options.reset ? 0 : 0
        const rows = await getAgentThreads({
          limit: THREAD_PAGE_SIZE,
          offset,
          include_archived: this.includeArchived
        })
        this.threads = rows
        this.hasMoreThreads = rows.length === THREAD_PAGE_SIZE
      } finally {
        this.threadsLoading = false
      }
    },
    async loadMoreThreads() {
      if (!this.hasMoreThreads || this.threadsLoading) return
      this.threadsLoading = true
      try {
        const rows = await getAgentThreads({
          limit: THREAD_PAGE_SIZE,
          offset: this.threads.length,
          include_archived: this.includeArchived
        })
        // Filter out any duplicates that could appear if a thread was updated
        // between requests (its updated_at could move it to an earlier page).
        const existing = new Set(this.threads.map(t => t.id))
        const fresh = rows.filter(r => !existing.has(r.id))
        this.threads.push(...fresh)
        this.hasMoreThreads = rows.length === THREAD_PAGE_SIZE
      } finally {
        this.threadsLoading = false
      }
    },
    async setIncludeArchived(value: boolean) {
      if (this.includeArchived === value) return
      this.includeArchived = value
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
        // Refresh the thread list so message counts and last_model reflect the new turn.
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
      const updated = await updateAgentThread(threadId, patch)
      const index = this.threads.findIndex(t => t.id === threadId)
      if (index >= 0) this.threads[index] = updated
      // Archiving may remove the row from the default-view list; reload to fix ordering.
      if (patch.archived !== undefined || patch.pinned !== undefined) {
        await this.loadThreads({ reset: true })
      }
    },
    async removeThread(threadId: string) {
      await deleteAgentThread(threadId)
      if (this.activeThreadId === threadId) this.startNewThread()
      await this.loadThreads({ reset: true })
    },
    async runSearch(query: string) {
      const q = query.trim()
      this.searchQuery = q
      if (!q) {
        this.searchResults = []
        this.searching = false
        return
      }
      this.searching = true
      try {
        this.searchResults = await searchAgentMessages(q, { limit: 30 })
      } finally {
        this.searching = false
      }
    },
    clearSearch() {
      this.searchQuery = ''
      this.searchResults = []
      this.searching = false
    }
  }
})
