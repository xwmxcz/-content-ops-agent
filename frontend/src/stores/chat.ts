import { defineStore } from 'pinia'
import {
  chat,
  deleteAgentThread,
  getAgentMessages,
  getAgentThreads,
  searchAgentMessages,
  updateAgentThread,
  type AgentMessage,
  type AgentSearchHit,
  type AgentThread,
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
  tool_events?: ChatToolEvent[]
  plan?: PlanStep[]
}

const ACTIVE_THREAD_STORAGE_KEY = 'chat:activeThreadId'
const THREAD_PAGE_SIZE = 30
const MESSAGE_PAGE_SIZE = 200

function readActiveThreadFromStorage(): string | undefined {
  try {
    return sessionStorage.getItem(ACTIVE_THREAD_STORAGE_KEY) || undefined
  } catch {
    return undefined
  }
}

function writeActiveThreadToStorage(threadId: string | undefined) {
  try {
    if (threadId) sessionStorage.setItem(ACTIVE_THREAD_STORAGE_KEY, threadId)
    else sessionStorage.removeItem(ACTIVE_THREAD_STORAGE_KEY)
  } catch {
    // sessionStorage may be unavailable in private mode; ignore.
  }
}

export const useChatStore = defineStore('chat', {
  state: () => ({
    threads: [] as AgentThread[],
    activeThreadId: readActiveThreadFromStorage() as string | undefined,
    messages: [] as UiMessage[],
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
      this.activeThreadId = threadId
      writeActiveThreadToStorage(threadId)
      if (!threadId) {
        this.messages = []
        this.hasMoreMessages = false
        return
      }
      this.messagesLoading = true
      try {
        const rows = await getAgentMessages(threadId, { limit: MESSAGE_PAGE_SIZE })
        this.messages = rows as UiMessage[]
        // If we got a full page back, there *might* be older history to load.
        this.hasMoreMessages = rows.length === MESSAGE_PAGE_SIZE
      } finally {
        this.messagesLoading = false
      }
    },
    async loadOlderMessages() {
      if (!this.activeThreadId || !this.hasMoreMessages || this.messagesLoading) return
      const firstId = this.messages.find(m => typeof m.id === 'number')?.id as number | undefined
      if (!firstId) return
      this.messagesLoading = true
      try {
        const older = await getAgentMessages(this.activeThreadId, {
          limit: MESSAGE_PAGE_SIZE,
          before_id: firstId
        })
        if (!older.length) {
          this.hasMoreMessages = false
          return
        }
        this.messages = [...(older as UiMessage[]), ...this.messages]
        this.hasMoreMessages = older.length === MESSAGE_PAGE_SIZE
      } finally {
        this.messagesLoading = false
      }
    },
    startNewThread() {
      this.activeThreadId = undefined
      writeActiveThreadToStorage(undefined)
      this.messages = []
      this.hasMoreMessages = false
    },
    async sendMessage(payload: Omit<ChatPayload, 'thread_id'>) {
      if (this.sending) return
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
      try {
        const result: ChatResponse = await chat({ ...payload, thread_id: this.activeThreadId })
        localMessage.pending = false
        this.activeThreadId = result.thread_id
        writeActiveThreadToStorage(result.thread_id)
        this.messages.push({
          id: result.message_id,
          thread_id: result.thread_id,
          role: 'assistant',
          content: result.response,
          provider: result.provider,
          model: result.model,
          tool_events: result.tool_events,
          plan: result.plan,
          status: 'completed'
        })
        // Refresh the thread list so message counts and last_model reflect the new turn.
        await this.loadThreads({ reset: true })
      } catch (error) {
        localMessage.pending = false
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
