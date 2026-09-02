<template>
  <div class="page chat-page">
    <section class="chat-topline">
      <div>
        <span class="hero-kicker">工具型 Agent</span>
        <h1 class="page-title">Agent 对话</h1>
        <p class="page-subtitle">多轮会话、模型切换和内容工具调用都会记录在当前 thread。</p>
      </div>
      <div class="hero-actions">
        <el-button :icon="Refresh" :loading="chat.threadsLoading" @click="refreshThreads">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="chat.startNewThread()">新建会话</el-button>
      </div>
    </section>

    <section class="chat-workbench">
      <aside class="thread-panel">
        <div class="panel-head">
          <span>Threads</span>
          <strong>{{ chat.threads.length }}</strong>
        </div>

        <div class="thread-search">
          <el-input
            v-model="searchInput"
            placeholder="搜索消息内容"
            size="small"
            clearable
            :prefix-icon="Search"
            @input="onSearchInput"
            @clear="onSearchClear"
          />
        </div>

        <label class="thread-toggle">
          <input type="checkbox" :checked="chat.includeArchived" @change="onIncludeArchivedChange" />
          <span>显示已归档</span>
        </label>

        <div class="thread-list">
          <!-- Search results override the thread list when a query is active. -->
          <div v-if="isSearchActive" class="search-results">
            <div v-if="chat.searching" class="thread-empty">搜索中…</div>
            <div v-else-if="!chat.searchResults.length" class="thread-empty">无匹配结果</div>
            <button
              v-for="hit in chat.searchResults"
              :key="`${hit.thread_id}-${hit.message_id}`"
              type="button"
              class="thread-item"
              :class="{ active: hit.thread_id === chat.activeThreadId }"
              @click="jumpToThread(hit.thread_id)"
            >
              <span class="thread-title">{{ threadLabel(hit.thread_id) }}</span>
              <small class="search-snippet">{{ snippet(hit.content) }}</small>
              <small>{{ hit.role === 'user' ? 'You' : 'Agent' }} · {{ formatTime(hit.created_at) }}</small>
            </button>
          </div>

          <template v-else>
            <div v-if="!chat.threads.length && !chat.threadsLoading" class="thread-empty">暂无会话</div>
            <div
              v-for="thread in chat.threads"
              :key="thread.id"
              class="thread-item"
              :class="{ active: thread.id === chat.activeThreadId, pinned: thread.pinned, archived: thread.archived }"
            >
              <button type="button" class="thread-item-body" @click="selectThread(thread.id)">
                <span class="thread-title">
                  <span v-if="thread.pinned" class="pin-mark" title="已置顶">📌</span>
                  <span v-if="thread.archived" class="archive-mark" title="已归档">🗄</span>
                  {{ thread.title || thread.id }}
                </span>
                <small>{{ thread.message_count }} 条消息 · {{ thread.last_model || '自动模型' }}</small>
              </button>
              <div class="thread-actions" @click.stop>
                <el-button text size="small" :icon="Edit" aria-label="重命名" @click="renameThread(thread)" />
                <el-button
                  text
                  size="small"
                  :icon="Top"
                  :class="{ 'is-active': thread.pinned }"
                  :aria-label="thread.pinned ? '取消置顶' : '置顶'"
                  @click="togglePin(thread)"
                />
                <el-button
                  text
                  size="small"
                  :icon="thread.archived ? FolderOpened : FolderRemove"
                  :class="{ 'is-active': thread.archived }"
                  :aria-label="thread.archived ? '取消归档' : '归档'"
                  @click="toggleArchive(thread)"
                />
                <el-button text size="small" type="danger" :icon="Delete" aria-label="删除" @click="removeThread(thread)" />
              </div>
            </div>
            <button
              v-if="chat.hasMoreThreads"
              type="button"
              class="thread-load-more"
              :disabled="chat.threadsLoading"
              @click="chat.loadMoreThreads()"
            >
              {{ chat.threadsLoading ? '加载中…' : '加载更多' }}
            </button>
          </template>
        </div>
      </aside>

      <main class="dialog-panel">
        <div class="dialog-head">
          <div>
            <span class="panel-kicker">当前会话</span>
            <strong>{{ currentThreadLabel }}</strong>
          </div>
          <div v-if="chat.activeThreadId" class="dialog-head-actions">
            <el-button text :icon="Edit" aria-label="重命名当前会话" @click="renameActive" />
            <el-button text type="danger" :icon="Delete" aria-label="删除当前会话" @click="removeActive" />
          </div>
        </div>

        <div ref="logRef" class="chat-log">
          <button
            v-if="chat.hasMoreMessages"
            type="button"
            class="load-older"
            :disabled="chat.messagesLoading"
            @click="loadOlder"
          >
            {{ chat.messagesLoading ? '加载中…' : '加载更早的消息' }}
          </button>

          <div v-if="!chat.messages.length" class="chat-empty">
            <strong>开始一次运营对话</strong>
            <p>可以让 Agent 查询内容库、生成草稿、打磨内容或安排发布日历。</p>
          </div>

          <article
            v-for="(message, messageIndex) in chat.messages"
            :key="message.local_id || message.id"
            class="message-row"
            :class="message.role"
          >
            <div class="message-bubble">
              <div class="message-meta">
                <span>{{ message.role === 'user' ? 'You' : 'Agent' }}</span>
                <small v-if="message.model">{{ message.provider }} / {{ message.model }}</small>
                <small v-else-if="message.pending">发送中</small>
              </div>

              <section v-if="message.role === 'assistant' && message.intent" class="intent-board">
                <div class="intent-head">
                  <span class="intent-chip" :class="`intent-${message.intent.name}`">
                    {{ intentLabel(message.intent.name) }}
                  </span>
                  <small>置信度 {{ intentConfidence(message.intent.confidence) }}</small>
                  <small v-if="message.intent.requires_confirmation">需确认</small>
                </div>
                <div
                  v-if="message.intent.route_surface === 'studio'"
                  class="studio-suggestion"
                >
                  <span>这类请求更适合在 Studio 的研究型 Pipeline 中运行。</span>
                  <el-button
                    type="primary"
                    size="small"
                    @click="openInStudio(messageIndex, message.intent)"
                  >
                    在 Studio 中打开
                  </el-button>
                </div>
              </section>

              <section v-if="message.plan?.length" class="plan-board">
                <div class="plan-head">Agent 计划</div>
                <ol>
                  <li v-for="step in message.plan" :key="step.index" :class="step.status">
                    <span class="plan-marker">{{ planMarker(step.status) }}</span>
                    <span class="plan-desc">{{ step.description }}</span>
                    <small v-if="step.tool_hint">→ {{ step.tool_hint }}</small>
                  </li>
                </ol>
              </section>

              <p>{{ message.content }}</p>

              <div v-if="message.tool_events?.length" class="tool-events">
                <div class="tool-events-head">
                  <span>Tool calls</span>
                  <strong>{{ message.tool_events.length }}</strong>
                </div>
                <details
                  v-for="(event, index) in message.tool_events"
                  :key="`${message.id || message.local_id}-${index}`"
                  class="tool-event"
                  :class="event.status"
                >
                  <summary>
                    <span class="tool-event-index">#{{ index + 1 }}</span>
                    <span class="tool-event-name">{{ event.name }}</span>
                    <span v-if="(event.attempt ?? 1) > 1" class="tool-event-attempt">
                      attempt {{ event.attempt }}
                    </span>
                    <span class="tool-event-badge" :class="event.status">
                      {{ eventStatusLabel(event.status) }}
                    </span>
                    <small class="tool-event-summary">{{ summarizeEvent(event) }}</small>
                  </summary>
                  <div class="tool-event-body">
                    <div v-if="hasArgs(event.args)" class="tool-event-section">
                      <div class="tool-event-label">args</div>
                      <pre>{{ prettyArgs(event.args) }}</pre>
                    </div>
                    <div v-if="event.status !== 'failed'" class="tool-event-section">
                      <div class="tool-event-label">{{ event.status === 'proposed' ? 'approval proposal' : 'output' }}</div>
                      <pre>{{ prettyOutput(event.output) || '(empty)' }}</pre>
                    </div>
                    <div v-else class="tool-event-section error">
                      <div class="tool-event-label">error</div>
                      <pre>{{ event.error || event.output || 'Unknown error' }}</pre>
                    </div>
                  </div>
                </details>
              </div>
            </div>
          </article>
        </div>

        <div class="composer">
          <el-input
            v-model="input"
            type="textarea"
            :rows="4"
            resize="none"
            placeholder="让 Agent 帮你处理内容运营任务"
            @keydown.ctrl.enter="send"
          />
          <div class="composer-actions">
            <span>{{ modelConfig.provider || '自动提供商' }} / {{ modelConfig.model || '自动模型' }}</span>
            <el-button type="primary" :icon="Position" :loading="chat.sending" @click="send">发送</el-button>
          </div>
        </div>
      </main>

      <aside class="control-panel">
        <ModelSelector
          :model-value="modelConfig"
          @update:model-value="Object.assign(modelConfig, $event)"
        />

        <section class="tool-panel">
          <div class="panel-head">
            <span>Tools</span>
            <strong>11</strong>
          </div>
          <div class="tool-grid">
            <span v-for="tool in tools" :key="tool">{{ tool }}</span>
          </div>
        </section>
      </aside>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus/es/components/message/index'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import 'element-plus/es/components/message-box/style/css'
import {
  Delete,
  Edit,
  FolderOpened,
  FolderRemove,
  Plus,
  Position,
  Refresh,
  Search,
  Top
} from '@element-plus/icons-vue'
import ModelSelector from '../components/ModelSelector.vue'
import { useChatStore } from '../stores/chat'
import type { AgentThread, ChatIntent, ChatIntentName, ChatToolEvent, PlanStep } from '../api/agent'

const tools = [
  'create_content',
  'refine_content',
  'generate_title_options',
  'optimize_seo',
  'view_content',
  'list_recent_contents',
  'add_to_calendar',
  'view_calendar',
  'get_content_stats',
  'check_xiaohongshu_login',
  'search_history'
]

const chat = useChatStore()
const input = ref('')
const route = useRoute()
const router = useRouter()
const logRef = ref<HTMLElement>()
const modelConfig = reactive({ provider: '', model: '', temperature: 0.7, max_tokens: 2048 })
const searchInput = ref('')

const isSearchActive = computed(() => Boolean(chat.searchQuery))
const currentThreadLabel = computed(() => {
  if (!chat.activeThreadId) return 'New thread'
  return chat.activeThread?.title || chat.activeThreadId
})

let searchDebounce: ReturnType<typeof setTimeout> | undefined

function onSearchInput(value: string) {
  if (searchDebounce) clearTimeout(searchDebounce)
  searchDebounce = setTimeout(() => {
    void chat.runSearch(value)
  }, 250)
}

function onSearchClear() {
  if (searchDebounce) clearTimeout(searchDebounce)
  chat.clearSearch()
}

async function onIncludeArchivedChange(event: Event) {
  const target = event.target as HTMLInputElement
  try {
    await chat.setIncludeArchived(target.checked)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function refreshThreads() {
  try {
    await chat.loadThreads({ reset: true })
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function selectThread(threadId: string) {
  try {
    await chat.selectThread(threadId)
    await scrollToBottom()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function jumpToThread(threadId: string) {
  // Clearing the search exits the search-results view; the regular thread
  // list re-renders with the target selected.
  searchInput.value = ''
  chat.clearSearch()
  await selectThread(threadId)
}

async function send() {
  const text = input.value.trim()
  if (!text || chat.sending) return
  const payload = {
    message: text,
    provider: modelConfig.provider || undefined,
    model: modelConfig.model || undefined,
    temperature: modelConfig.temperature,
    max_tokens: modelConfig.max_tokens
  }
  input.value = ''
  await scrollToBottom()
  try {
    await chat.sendMessage(payload)
    await scrollToBottom()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function loadOlder() {
  const log = logRef.value
  const prevHeight = log?.scrollHeight ?? 0
  await chat.loadOlderMessages()
  await nextTick()
  if (log) {
    // Preserve the user's scroll position relative to the existing content
    // when older messages are prepended.
    log.scrollTop = log.scrollHeight - prevHeight
  }
}

async function renameThread(thread: AgentThread) {
  try {
    const { value } = await ElMessageBox.prompt('修改会话标题', '重命名会话', {
      inputValue: thread.title || '',
      inputPlaceholder: '输入新标题',
      inputValidator: (val: string) => (val.trim().length > 0 ? true : '标题不能为空'),
      confirmButtonText: '保存',
      cancelButtonText: '取消'
    })
    await chat.renameThread(thread.id, value)
    ElMessage.success('已重命名')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error((error as Error).message || '重命名失败')
  }
}

async function renameActive() {
  const target = chat.activeThread
  if (target) await renameThread(target)
}

async function togglePin(thread: AgentThread) {
  try {
    await chat.togglePin(thread.id)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function toggleArchive(thread: AgentThread) {
  try {
    await chat.toggleArchive(thread.id)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function removeThread(thread: AgentThread) {
  try {
    await ElMessageBox.confirm(
      `确定删除会话「${thread.title || thread.id}」吗？该操作不可撤销。`,
      '删除会话',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
    await chat.removeThread(thread.id)
    ElMessage.success('已删除')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error((error as Error).message || '删除失败')
  }
}

async function removeActive() {
  const target = chat.activeThread
  if (target) await removeThread(target)
}

async function scrollToBottom() {
  await nextTick()
  if (logRef.value) {
    logRef.value.scrollTop = logRef.value.scrollHeight
  }
}

function hasArgs(args: Record<string, unknown> | undefined) {
  return !!args && Object.keys(args).length > 0
}

function prettyArgs(args: Record<string, unknown> | undefined) {
  if (!args) return ''
  try {
    return JSON.stringify(args, null, 2)
  } catch {
    return String(args)
  }
}

function prettyOutput(output: string | undefined) {
  if (!output) return ''
  const trimmed = output.trim()
  if (!trimmed) return ''
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      return JSON.stringify(JSON.parse(trimmed), null, 2)
    } catch {
      return output
    }
  }
  return output
}

function eventStatusLabel(status: ChatToolEvent['status']) {
  if (status === 'completed') return 'ok'
  if (status === 'proposed') return 'confirm'
  return 'failed'
}

function summarizeEvent(event: ChatToolEvent) {
  if (event.status === 'failed') {
    return event.error || event.output || 'failed'
  }
  const text = (event.output || '').replace(/\s+/g, ' ').trim()
  return text.length > 80 ? `${text.slice(0, 80)}…` : text
}

function intentLabel(name: ChatIntentName) {
  const labels: Record<ChatIntentName, string> = {
    content_create: '新建内容',
    content_refine: '内容改写',
    title_generate: '标题生成',
    seo_optimize: 'SEO 优化',
    content_search: '内容检索',
    topic_strategy: '选题策略',
    performance_review: '效果复盘',
    calendar_view: '查看日历',
    schedule_propose: '排期提案',
    schedule_commit: '确认排期',
    memory_update: '记忆更新',
    action_confirm: '确认操作',
    smalltalk: '闲聊',
    clarify: '需要澄清',
    unknown: '未分类'
  }
  return labels[name] || name
}

function intentConfidence(value: number | undefined) {
  const ratio = typeof value === 'number' ? value : 0
  return `${Math.round(ratio * 100)}%`
}

function studioTopicFor(index: number) {
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    const message = chat.messages[cursor]
    if (message?.role === 'user' && message.content?.trim()) return message.content.trim()
  }
  return input.value.trim()
}

function openInStudio(index: number, intent: ChatIntent) {
  const topic = studioTopicFor(index)
  const researchFocus = typeof intent.slots?.research_focus === 'string' ? intent.slots.research_focus : ''
  void router.push({
    path: '/',
    query: {
      mode: 'dynamic',
      topic,
      research_focus: researchFocus || undefined
    }
  })
}

function planMarker(status: PlanStep['status']) {
  const map: Record<PlanStep['status'], string> = {
    pending: '○',
    running: '◐',
    completed: '●',
    failed: '✗',
    skipped: '–'
  }
  return map[status] ?? '○'
}

function threadLabel(threadId: string) {
  const hit = chat.threads.find(t => t.id === threadId)
  return hit?.title || threadId
}

function snippet(content: string) {
  const text = content.replace(/\s+/g, ' ').trim()
  return text.length > 90 ? `${text.slice(0, 90)}…` : text
}

function formatTime(iso?: string) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

onMounted(async () => {
  try {
    await chat.loadThreads({ reset: true })
    // Restore the previously-active thread (sessionStorage) if it still exists.
    if (chat.activeThreadId && chat.threads.some(t => t.id === chat.activeThreadId)) {
      await chat.selectThread(chat.activeThreadId)
      await scrollToBottom()
    } else if (chat.activeThreadId) {
      // Stale session id (deleted in another tab); clear it.
      chat.startNewThread()
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
  const seed = route.query.seed
  if (typeof seed === 'string' && seed.trim()) {
    input.value = seed.trim()
    router.replace({ query: {} })
    await nextTick()
    ElMessage.info('已带入待优化提示，确认后点击发送')
  }
})
</script>

<style scoped>
.chat-page {
  display: grid;
  gap: 20px;
  padding: 24px 32px;
  background: var(--c-bg);
  color: var(--c-text);
}

.chat-topline {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.hero-kicker,
.panel-kicker {
  display: inline-block;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.chat-topline .page-title {
  margin-top: 6px;
  font-size: var(--fs-h1);
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1.15;
}

.chat-topline .page-subtitle {
  margin-top: 6px;
  color: var(--c-text-secondary);
  font-size: 14px;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.chat-workbench {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 340px;
  gap: 16px;
  min-height: 680px;
  height: calc(100vh - 200px);
  max-height: 920px;
}

.thread-panel,
.dialog-panel,
.control-panel,
.tool-panel {
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-surface);
  box-shadow: none;
  backdrop-filter: none;
}

.thread-panel,
.control-panel {
  display: grid;
  gap: 12px;
  padding: 16px;
}

.control-panel {
  align-self: start;
}

.thread-panel {
  /* Header / search / toggle stay put; only .thread-list (the last row) scrolls. */
  align-self: stretch;
  overflow: hidden;
  min-height: 0;
  grid-template-rows: auto auto auto minmax(0, 1fr);
}

.thread-list {
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-right: 2px;
}

.dialog-panel {
  min-width: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  overflow: hidden;
}

.panel-head,
.dialog-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.dialog-head-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.panel-head span {
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.panel-head strong {
  color: var(--c-text);
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 500;
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
}

.thread-search {
  /* Sits between the header and the thread list. */
}

.thread-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--c-text-secondary);
  cursor: pointer;
  user-select: none;
}

.thread-toggle input {
  margin: 0;
  cursor: pointer;
}

.thread-empty {
  display: grid;
  min-height: 120px;
  place-items: center;
  color: var(--c-text-tertiary);
  font-size: 13px;
}

.search-results {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* Thread list items ----------------------------------------------------- */

.thread-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 4px;
  width: 100%;
  flex-shrink: 0;
  padding: 6px 8px 6px 12px;
  border: 1px solid transparent;
  border-radius: 4px;
  color: var(--c-text);
  background: transparent;
  text-align: left;
  transition: background-color 80ms ease, border-color 80ms ease;
}

.thread-item:hover {
  background: var(--c-bg-soft);
}

.thread-item.active {
  border-color: var(--c-accent);
  background: var(--c-accent-soft);
}

.thread-item.archived {
  opacity: 0.65;
}

.thread-item-body {
  display: grid;
  gap: 4px;
  padding: 4px 0;
  width: 100%;
  min-width: 0;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.thread-title {
  display: flex;
  align-items: center;
  gap: 4px;
  overflow: hidden;
  font-weight: 600;
  font-size: 13px;
  letter-spacing: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pin-mark,
.archive-mark {
  font-size: 12px;
  flex-shrink: 0;
}

.thread-item small {
  overflow: hidden;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-family: var(--font-mono);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thread-actions {
  display: none;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.thread-item:hover .thread-actions,
.thread-item.active .thread-actions {
  display: flex;
}

.thread-actions :deep(.el-button) {
  padding: 4px 5px;
  height: 24px;
}

.thread-actions :deep(.is-active) {
  color: var(--c-accent);
}

.thread-load-more {
  width: 100%;
  flex-shrink: 0;
  padding: 8px;
  margin-top: 4px;
  border: 1px dashed var(--c-border);
  border-radius: 4px;
  background: transparent;
  color: var(--c-text-secondary);
  cursor: pointer;
  font-size: 12px;
  transition: border-color 100ms ease;
}

.thread-load-more:hover:not(:disabled) {
  border-color: var(--c-accent);
  color: var(--c-accent);
}

.thread-load-more:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.search-snippet {
  color: var(--c-text-secondary) !important;
  font-family: var(--font-ui) !important;
}

.dialog-head {
  padding: 14px 20px;
  border-bottom: 1px solid var(--c-border);
}

.dialog-head strong {
  display: block;
  margin-top: 4px;
  color: var(--c-text);
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 500;
  word-break: break-word;
}

.chat-log {
  min-height: 0;
  padding: 20px;
  overflow-y: auto;
  background: var(--c-bg-soft);
  border: 0;
  border-radius: 0;
  scroll-behavior: smooth;
}

.chat-log::-webkit-scrollbar {
  width: 8px;
}

.chat-log::-webkit-scrollbar-thumb {
  background: var(--c-border);
  border-radius: 4px;
}

.chat-log::-webkit-scrollbar-thumb:hover {
  background: var(--c-text-tertiary);
}

.load-older {
  display: block;
  margin: 0 auto 12px;
  padding: 4px 14px;
  border: 1px solid var(--c-border);
  border-radius: 999px;
  background: transparent;
  color: var(--c-text-secondary);
  cursor: pointer;
  font-size: 12px;
  font-family: var(--font-mono);
  transition: border-color 100ms ease;
}

.load-older:hover:not(:disabled) {
  border-color: var(--c-accent);
  color: var(--c-accent);
}

.load-older:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.chat-empty {
  display: grid;
  gap: 6px;
  min-height: 360px;
  place-items: center;
  color: var(--c-text-tertiary);
  text-align: center;
}

.chat-empty strong {
  color: var(--c-text);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0;
}

.chat-empty p {
  margin: 0;
  color: var(--c-text-secondary);
  font-size: 13px;
}

.message-row {
  display: flex;
  margin-bottom: 16px;
}

.message-row.user {
  justify-content: flex-end;
}

.message-bubble {
  width: min(78%, 720px);
  padding: 14px 16px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  color: var(--c-text);
  background: var(--c-surface);
}

.message-row.user .message-bubble {
  background: var(--c-bg-soft);
}

.message-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.message-meta span {
  color: var(--c-text);
  font-weight: 600;
  font-size: 12px;
  letter-spacing: 0;
}

.message-meta small {
  overflow: hidden;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-family: var(--font-mono);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.message-bubble p {
  margin: 0;
  color: var(--c-text);
  font-size: 14px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}

.intent-board {
  display: grid;
  gap: 8px;
  margin-bottom: 14px;
}

.intent-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  color: var(--c-text-secondary);
  font-size: 12px;
}

.intent-chip {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--c-accent) 10%, white);
  color: var(--c-accent);
  font-size: 12px;
  font-weight: 600;
}

.studio-suggestion {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--c-accent) 24%, transparent);
  border-radius: 6px;
  background: color-mix(in srgb, var(--c-accent) 6%, white);
  color: var(--c-text-secondary);
  font-size: 13px;
}

.tool-events {
  display: grid;
  gap: 6px;
  margin-top: 14px;
}

.plan-board {
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  background: var(--c-bg-soft);
}

.plan-head {
  margin-bottom: 8px;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-family: var(--font-mono);
}

.plan-board ol {
  display: grid;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
  counter-reset: plan-step;
}

.plan-board li {
  display: grid;
  grid-template-columns: 16px 16px minmax(0, 1fr) auto;
  align-items: baseline;
  gap: 8px;
  padding: 3px 0;
  font-size: 13px;
  font-family: var(--font-mono);
  color: var(--c-text-secondary);
  counter-increment: plan-step;
}

.plan-board li::before {
  content: counter(plan-step, decimal-leading-zero);
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 500;
  text-align: right;
}

.plan-board li.completed {
  color: var(--c-ok);
}

.plan-board li.running {
  color: var(--c-accent);
  font-weight: 500;
}

.plan-board li.failed {
  color: var(--c-fail);
}

.plan-board li.skipped {
  color: var(--c-text-tertiary);
}

.plan-marker {
  display: inline-block;
  width: 16px;
  flex-shrink: 0;
  text-align: center;
  font-size: 13px;
  font-family: var(--font-mono);
}

.plan-board li.running .plan-marker {
  animation: marker-pulse 1.2s ease-in-out infinite;
}

@keyframes marker-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.plan-desc {
  flex: 1;
  font-family: var(--font-ui);
  font-size: 13px;
  color: inherit;
}

.plan-board small {
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-family: var(--font-mono);
  white-space: nowrap;
}

.tool-events-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 4px;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-family: var(--font-mono);
}

.tool-events-head strong {
  color: var(--c-text);
  font-size: 12px;
  font-family: var(--font-mono);
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
}

.tool-event {
  border: 1px solid var(--c-border);
  border-radius: 4px;
  background: var(--c-surface);
  overflow: hidden;
  font-family: var(--font-mono);
  transition: border-color 100ms ease;
}

.tool-event:hover {
  border-color: var(--c-border-strong);
}

.tool-event.failed {
  border-color: var(--c-fail);
  background: var(--c-fail-soft);
}

.tool-event.proposed {
  border-color: var(--c-warn);
  background: var(--c-warn-soft);
}

.tool-event > summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
  padding: 8px 12px;
  cursor: pointer;
  list-style: none;
  user-select: none;
  font-size: 12px;
  line-height: 1.4;
}

.tool-event > summary::-webkit-details-marker {
  display: none;
}

.tool-event > summary::before {
  content: '›';
  flex-shrink: 0;
  color: var(--c-text-tertiary);
  font-size: 14px;
  font-weight: 600;
  width: 12px;
  display: inline-block;
  transition: transform 0.12s ease;
}

.tool-event[open] > summary::before {
  transform: rotate(90deg);
}

.tool-event-index {
  flex-shrink: 0;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 500;
  font-family: var(--font-mono);
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
  min-width: 28px;
}

.tool-event-name {
  color: var(--c-text);
  font-size: 12.5px;
  font-weight: 500;
  font-family: var(--font-mono);
  letter-spacing: 0;
  word-break: break-all;
  flex-shrink: 0;
}

.tool-event.failed .tool-event-name {
  color: var(--c-fail);
}

.tool-event.proposed .tool-event-name {
  color: var(--c-warn);
}

.tool-event-badge {
  flex-shrink: 0;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-family: var(--font-mono);
}

.tool-event-attempt {
  flex-shrink: 0;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--c-warn-soft);
  color: var(--c-warn);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.04em;
  font-family: var(--font-mono);
}

.tool-event-badge.completed {
  color: var(--c-ok);
  background: var(--c-ok-soft);
}

.tool-event-badge.failed {
  color: #ffffff;
  background: var(--c-fail);
}

.tool-event-badge.proposed {
  color: var(--c-warn);
  background: var(--c-warn-soft);
}

.tool-event-summary {
  flex: 1 1 200px;
  min-width: 0;
  overflow: hidden;
  color: var(--c-text-tertiary);
  font-size: 11.5px;
  font-family: var(--font-mono);
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-event-body {
  display: grid;
  gap: 10px;
  padding: 0 12px 12px;
  border-top: 1px solid var(--c-border);
  padding-top: 10px;
}

.tool-event-section {
  display: grid;
  gap: 4px;
}

.tool-event-label {
  color: var(--c-text-tertiary);
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-family: var(--font-mono);
}

.tool-event-section pre {
  margin: 0;
  padding: 10px 12px;
  border-radius: 4px;
  background: var(--c-bg-code);
  border: 1px solid var(--c-border);
  color: var(--c-text);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.55;
  max-height: 240px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  max-width: 100%;
}

.tool-event-section.error pre {
  background: var(--c-fail-soft);
  color: var(--c-fail);
  border-color: var(--c-fail);
}

.composer {
  display: grid;
  gap: 10px;
  padding: 14px 20px 16px;
  border-top: 1px solid var(--c-border);
  background: var(--c-surface);
  min-width: 0;
}

.composer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

.composer-actions span {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  color: var(--c-text-tertiary);
  font-size: 11.5px;
  font-family: var(--font-mono);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-panel {
  display: grid;
  gap: 12px;
  padding: 16px;
}

.tool-grid {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.tool-grid span {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border: 1px solid var(--c-border);
  border-radius: 999px;
  color: var(--c-text-secondary);
  background: var(--c-surface);
  font-size: 11px;
  font-family: var(--font-mono);
  letter-spacing: 0;
}

@media (max-width: 1180px) {
  .chat-workbench {
    grid-template-columns: 240px minmax(0, 1fr);
    min-height: 0;
  }

  .control-panel {
    grid-column: 1 / -1;
  }
}

@media (max-width: 820px) {
  .chat-page {
    padding: 16px;
  }

  .chat-topline {
    align-items: flex-start;
    flex-direction: column;
  }

  .chat-workbench {
    grid-template-columns: minmax(0, 1fr);
  }

  .thread-panel {
    order: 2;
  }

  .dialog-panel {
    order: 1;
  }

  .control-panel {
    order: 3;
  }

  .message-bubble {
    width: 100%;
  }

  .studio-suggestion {
    align-items: flex-start;
    flex-direction: column;
  }

  .composer-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .thread-actions {
    display: flex; /* Touch devices have no hover. */
  }
}
</style>
