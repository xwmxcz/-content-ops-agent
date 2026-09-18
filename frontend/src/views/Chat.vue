<template>
  <div class="page chat-page">
    <section class="chat-topline">
      <div>
        <h1 class="page-title">把想法，聊成内容。</h1>
        <p class="page-subtitle">从选题到成稿，和你的内容助手一起推进。</p>
      </div>
      <div class="hero-actions">
        <el-button :icon="Refresh" :loading="chat.threadsLoading" @click="refreshThreads">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="chat.startNewThread()">新建会话</el-button>
      </div>
    </section>

    <section class="chat-workbench">
      <aside class="thread-panel">
        <div class="panel-head">
          <span>我的会话</span>
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
              <small>{{ hit.role === 'user' ? '我' : '内容助手' }} · {{ formatTime(hit.created_at) }}</small>
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
                <small>{{ thread.message_count }} 条消息</small>
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

        <aside class="control-panel" aria-label="会话设置">
          <details class="model-settings">
            <summary>
              <span>模型设置</span>
              <small :title="modelConfig.model">{{ modelConfig.model || '自动模型' }}</small>
            </summary>
            <div class="settings-body">
              <ModelSelector
                :model-value="modelConfig"
                @update:model-value="Object.assign(modelConfig, $event)"
              />
            </div>
          </details>
          <details class="tool-panel">
            <summary>可用工具 <small>{{ tools.length }}</small></summary>
            <div class="tool-grid">
              <span v-for="tool in tools" :key="tool">{{ tool }}</span>
            </div>
          </details>
        </aside>

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
            <span class="empty-label">留一页，给下一个好想法</span>
            <strong>今天，想写点什么？</strong>
            <p>说说你的选题，或把一段需要打磨的草稿交给我。</p>
            <div class="empty-capabilities"><span>寻找内容</span><span>生成草稿</span><span>打磨表达</span><span>安排日历</span></div>
          </div>

          <article
            v-for="(message, messageIndex) in chat.messages"
            :key="message.local_id || message.id"
            class="message-row"
            :class="message.role"
          >
            <div class="message-bubble">
              <div class="message-meta">
                <span>{{ message.role === 'user' ? '我' : '内容助手' }}</span>
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
                  <span>前往创作工作台，进行资料研究与分步创作。</span>
                  <el-button
                    type="primary"
                    size="small"
                    @click="openInStudio(messageIndex, message.intent)"
                  >
                    在创作工作台打开
                  </el-button>
                </div>
              </section>

              <section v-if="message.plan?.length" class="plan-board">
                <div class="plan-head">执行计划</div>
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
                  <span>工具执行记录</span>
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
                      第 {{ event.attempt }} 次尝试
                    </span>
                    <span class="tool-event-badge" :class="event.status">
                      {{ eventStatusLabel(event.status) }}
                    </span>
                    <small class="tool-event-summary">{{ summarizeEvent(event) }}</small>
                  </summary>
                  <div class="tool-event-body">
                    <div v-if="hasArgs(event.args)" class="tool-event-section">
                      <div class="tool-event-label">输入参数</div>
                      <pre>{{ prettyArgs(event.args) }}</pre>
                    </div>
                    <div v-if="event.status !== 'failed'" class="tool-event-section">
                      <div class="tool-event-label">{{ event.status === 'proposed' ? '待确认操作' : '执行结果' }}</div>
                      <pre>{{ prettyOutput(event.output) || '暂无输出' }}</pre>
                    </div>
                    <div v-else class="tool-event-section error">
                      <div class="tool-event-label">错误详情</div>
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
            :rows="3"
            resize="none"
            placeholder="描述你的想法，或粘贴需要打磨的内容…"
            @keydown.ctrl.enter="send"
          />
          <div class="composer-actions">
            <span>Ctrl + Enter 发送 · 支持多轮对话</span>
            <el-button type="primary" :icon="Position" :loading="chat.sending" @click="send">发送</el-button>
          </div>
        </div>
      </main>

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
import {
  eventStatusLabel,
  hasArgs,
  intentConfidence,
  intentLabel,
  planMarker,
  prettyArgs,
  prettyOutput,
  summarizeEvent
} from '../composables/useChatPresentation'
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
  if (!chat.activeThreadId) return '新会话'
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
  display: flex;
  flex-direction: column;
  height: calc(100dvh - 68px);
  gap: 20px;
  padding: 24px 32px;
  color: var(--c-text);
}

.chat-topline, .hero-actions, .panel-head, .dialog-head, .dialog-head-actions,
.composer-actions, .message-meta, .intent-head, .studio-suggestion {
  display: flex;
  align-items: center;
  gap: 12px;
}

.chat-topline, .panel-head, .dialog-head, .composer-actions, .message-meta,
.studio-suggestion {
  justify-content: space-between;
}

.chat-topline {
  align-items: flex-end;
  flex-shrink: 0;
}

.hero-actions {
  flex-wrap: wrap;
  gap: 8px;
}

.panel-kicker {
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .08em;
}
.chat-topline .page-title {
  margin: 0 0 8px;
  font-family: var(--font-display);
  font-size: var(--fs-h1);
  line-height: 1.3;
  letter-spacing: -.04em;
}
.chat-topline .page-subtitle {
  margin: 0;
  color: var(--c-text-secondary);
  font-size: 13px;
}


.chat-workbench {
  display: grid;
  flex: 1;
  grid-template-columns: 236px minmax(0, 1fr);
  gap: 20px;
  min-height: 0;
}
.thread-panel, .dialog-panel {
  min-width: 0;
  border: 1px solid var(--c-border);
  border-radius: var(--r-card);
  background: var(--c-surface);
}
.thread-panel {
  display: grid;
  grid-template-rows: auto auto auto minmax(0, 1fr);
  align-self: stretch;
  gap: 16px;
  padding: 20px 12px 12px;
  min-height: 0;
  overflow: hidden;
  background: var(--c-bg-soft);
}
.panel-head, .thread-search, .thread-toggle {
  margin: 0 6px;
}

.panel-head span {
  color: var(--c-text-secondary);
  font-weight: 600;
  font-size: 13px;
}

.panel-head strong {
  padding: 1px 8px;
  border-radius: var(--r-pill);
  background: var(--c-surface);
  color: var(--c-text-tertiary);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.thread-toggle {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--c-text-tertiary);
  font-size: 12px;
  cursor: pointer;
}

.thread-toggle input {
  margin: 0;
  accent-color: var(--c-accent);
}

.thread-list, .search-results {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.thread-list {
  min-height: 0;
  overflow-y: auto;
}

.thread-empty {
  padding: 42px 12px;
  color: var(--c-text-tertiary);
  text-align: center;
  font-size: 13px;
}

.thread-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 4px;
  flex-shrink: 0;
  width: 100%;
  padding: 12px 12px 6px;
  border: 1px solid transparent;
  border-radius: var(--r-control);
  background: transparent;
  color: var(--c-text);
  text-align: left;
  transition: background-color 120ms ease, border-color 120ms ease;
}
.thread-item:hover {
  background: var(--c-surface);
}

.thread-item.active {
  background: var(--c-surface);
  border-color: var(--c-border);
  box-shadow: inset 3px 0 var(--c-accent);
}

.thread-item.archived {
  opacity: .65;
}

.thread-item-body {
  display: grid;
  gap: 7px;
  min-width: 0;
  width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.thread-title {
  overflow: hidden;
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pin-mark, .archive-mark {
  font-size: 11px;
}

.thread-item small {
  overflow: hidden;
  color: var(--c-text-tertiary);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thread-actions {
  /* Keep this row reserved so revealing actions never moves the title target. */
  display: flex;
  visibility: hidden;
  justify-content: flex-end;
  align-items: center;
  gap: 2px;
}
.thread-item:hover .thread-actions,
.thread-item:focus-within .thread-actions,
.thread-item.active .thread-actions {
  visibility: visible;
}

.thread-actions :deep(.el-button) {
  padding: 4px 5px;
  height: 24px;
  margin: 0;
}

.thread-actions :deep(.is-active) {
  color: var(--c-accent);
}

.thread-load-more, .load-older {
  padding: 7px 14px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-control);
  background: var(--c-surface);
  color: var(--c-text-secondary);
  font-size: 12px;
  cursor: pointer;
}
.thread-load-more:hover:not(:disabled), .load-older:hover:not(:disabled) {
  color: var(--c-accent);
  border-color: var(--c-accent);
}

.thread-load-more:disabled, .load-older:disabled {
  opacity: .6;
  cursor: not-allowed;
}

.search-snippet {
  color: var(--c-text-secondary);
}


.dialog-panel {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  overflow: hidden;
  box-shadow: var(--shadow-panel);
}
.dialog-head {
  padding: 19px 26px;
}

.dialog-head > div:first-child {
  min-width: 0;
}

.dialog-head strong {
  display: block;
  margin-top: 4px;
  font-size: 15px;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.dialog-head-actions {
  gap: 0;
  flex-shrink: 0;
}

.control-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0 24px;
  padding: 0 26px;
  border-block: 1px solid var(--c-border-soft);
  background: var(--c-bg-soft);
  max-height: min(32dvh, 260px);
  overflow-y: auto;
}
.model-settings, .tool-panel {
  min-width: 0;
}

.control-panel summary {
  display: flex;
  align-items: center;
  gap: 9px;
  min-height: 42px;
  color: var(--c-text-secondary);
  font-size: 12px;
  cursor: pointer;
  list-style: none;
}
.control-panel summary::-webkit-details-marker {
  display: none;
}

.control-panel summary::after {
  content: '⌄';
  color: var(--c-text-tertiary);
}

.control-panel details[open] > summary::after {
  transform: rotate(180deg);
}

.control-panel summary > span {
  flex-shrink: 0;
}

.control-panel summary small {
  color: var(--c-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.settings-body {
  padding: 5px 0 20px;
}

.tool-grid {
  display: grid;
  gap: 8px;
  padding: 8px 0 20px;
}

.tool-grid span {
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-family: var(--font-mono);
  overflow-wrap: anywhere;
}


.chat-log {
  min-height: 0;
  max-height: none;
  padding: 28px;
  overflow-y: auto;
  border: 0;
  border-radius: 0;
  box-shadow: none;
  scroll-behavior: smooth;
}

.load-older {
  display: block;
  margin: 0 auto 24px;
  border-radius: var(--r-pill);
}

.chat-empty {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 100%;
  gap: 12px;
  padding: 24px 16px;
  text-align: center;
}
.empty-label {
  padding: 7px 13px;
  background: var(--c-accent-soft);
  color: var(--c-accent);
  border-radius: var(--r-pill);
  font-size: 11px;
}

.chat-empty strong {
  font-family: var(--font-editorial);
  font-size: clamp(25px, 2.5vw, 34px);
  font-weight: 500;
  letter-spacing: -.03em;
}

.chat-empty p {
  max-width: 330px;
  margin: 0;
  color: var(--c-text-secondary);
  font-size: 13px;
  line-height: 1.8;
}

.empty-capabilities {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px 18px;
  margin-top: 12px;
  color: var(--c-text-tertiary);
  font-size: 11px;
}

.empty-capabilities span::before {
  content: '·';
  margin-right: 8px;
  color: var(--c-accent);
}

.message-row {
  display: flex;
  margin-bottom: 26px;
}

.message-row.user {
  justify-content: flex-end;
}

.message-bubble {
  width: 100%;
  min-width: 0;
  padding: 6px 0;
}

.message-row.user .message-bubble {
  width: auto;
  max-width: 88%;
  padding: 16px 20px;
  border-radius: 16px 16px 4px 16px;
  background: var(--c-accent-soft);
}

.message-meta {
  margin-bottom: 10px;
}

.message-meta span {
  font-size: 12px;
  font-weight: 600;
  color: var(--c-accent);
}

.message-meta small {
  overflow: hidden;
  color: var(--c-text-tertiary);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.message-bubble p {
  margin: 0;
  color: var(--c-text);
  font-size: 14px;
  line-height: 1.85;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.intent-board {
  display: grid;
  gap: 10px;
  margin-bottom: 14px;
}

.intent-head {
  flex-wrap: wrap;
  gap: 9px;
  color: var(--c-text-tertiary);
  font-size: 11px;
}

.intent-chip {
  padding: 3px 9px;
  border-radius: var(--r-pill);
  background: var(--c-bg-soft);
  color: var(--c-text-secondary);
  font-size: 11px;
}

.studio-suggestion {
  padding: 12px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-control);
  background: var(--c-accent-soft);
  color: var(--c-text-secondary);
  font-size: 12px;
}

.plan-board {
  margin-bottom: 16px;
  padding: 14px 16px;
  border-left: 2px solid var(--c-border);
  background: var(--c-bg-soft);
  border-radius: 0 var(--r-control) var(--r-control) 0;
}

.plan-head, .tool-events-head {
  margin-bottom: 8px;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 600;
}

.plan-board ol {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.plan-board li {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  align-items: baseline;
  gap: 3px 8px;
  font-size: 12px;
  color: var(--c-text-secondary);
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
  text-align: center;
}

.plan-board small {
  grid-column: 2;
  color: var(--c-text-tertiary);
  font-family: var(--font-mono);
  font-size: 10px;
  overflow-wrap: anywhere;
}

.tool-events {
  display: grid;
  gap: 6px;
  margin-top: 18px;
}

.tool-events-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 2px;
}

.tool-events-head strong {
  font-weight: 500;
}

.tool-event {
  border: 1px solid var(--c-border);
  border-radius: var(--r-control);
  overflow: hidden;
  background: var(--c-bg-soft);
}

.tool-event.failed {
  border-color: var(--c-fail);
}

.tool-event.proposed {
  border-color: var(--c-warn);
}

.tool-event > summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px 8px;
  padding: 10px 12px;
  cursor: pointer;
  list-style: none;
  font-size: 11px;
}

.tool-event > summary::-webkit-details-marker {
  display: none;
}

.tool-event > summary::before {
  content: '›';
  color: var(--c-text-tertiary);
  font-size: 14px;
}

.tool-event[open] > summary::before {
  transform: rotate(90deg);
}

.tool-event-index, .tool-event-summary {
  color: var(--c-text-tertiary);
  font-size: 10px;
}

.tool-event-name {
  color: var(--c-text-secondary);
  font-family: var(--font-mono);
  overflow-wrap: anywhere;
}

.tool-event-badge, .tool-event-attempt {
  padding: 2px 6px;
  border-radius: var(--r-pill);
  font-size: 10px;
}

.tool-event-badge.completed {
  color: var(--c-ok);
  background: var(--c-ok-soft);
}

.tool-event-badge.failed {
  color: var(--c-fail);
  background: var(--c-fail-soft);
}

.tool-event-badge.proposed, .tool-event-attempt {
  color: var(--c-warn);
  background: var(--c-warn-soft);
}

.tool-event-summary {
  flex: 1 1 180px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-event-body {
  display: grid;
  gap: 12px;
  padding: 12px;
  border-top: 1px solid var(--c-border);
}

.tool-event-section {
  min-width: 0;
  display: grid;
  gap: 5px;
}

.tool-event-label {
  color: var(--c-text-tertiary);
  font-size: 10px;
}

.tool-event-section pre {
  max-width: 100%;
  max-height: 240px;
  overflow: auto;
  margin: 0;
  padding: 12px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-control);
  background: var(--c-surface);
  color: var(--c-text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.65;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.tool-event-section.error pre {
  color: var(--c-fail);
  background: var(--c-fail-soft);
}

.composer {
  display: grid;
  gap: 12px;
  min-width: 0;
  padding: 18px 24px 20px;
  border-top: 1px solid var(--c-border-soft);
}

.composer :deep(.el-textarea__inner) {
  padding: 14px 16px;
  line-height: 1.7;
  background: var(--c-bg-soft);
}

.composer-actions span {
  min-width: 0;
  color: var(--c-text-tertiary);
  font-size: 11px;
}

.composer-actions :deep(.el-button) {
  min-width: 94px;
}

.thread-item-body:focus-visible, summary:focus-visible, .load-older:focus-visible, .thread-load-more:focus-visible {
  outline: 2px solid var(--c-accent);
  outline-offset: 3px;
  border-radius: var(--r-control);
}


@media (max-width: 1100px) {
  .chat-workbench {
    grid-template-columns: 210px minmax(0, 1fr);
    gap: 14px;
  }

  .chat-log {
    padding: 22px;
  }

  .control-panel {
    padding: 0 20px;
    gap: 12px;
  }

  .model-settings[open] {
    grid-column: 1 / -1;
  }

  .tool-panel[open] {
    grid-column: 1 / -1;
  }

  .tool-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

}

@media (min-width: 821px) and (max-width: 980px) {
  .chat-page {
    height: calc(100dvh - 118px);
  }
}

@media (min-width: 821px) and (max-height: 600px) {
  .chat-page {
    height: auto;
  }

  .chat-workbench {
    flex: none;
    height: 520px;
  }
}

@media (max-width: 820px) {
  .chat-page {
    height: auto;
    padding: 20px 16px;
    gap: 20px;
  }

  .chat-topline {
    align-items: flex-start;
    flex-direction: column;
    gap: 18px;
  }

  .chat-workbench {
    flex: none;
    grid-template-columns: minmax(0, 1fr);
    height: auto;
    max-height: none;
  }

  .dialog-panel {
    order: 1;
    min-height: 670px;
    grid-template-rows: auto auto minmax(280px, 1fr) auto;
  }

  .thread-panel {
    order: 2;
    max-height: 350px;
  }

  .thread-actions {
    visibility: visible;
  }

  .dialog-head {
    padding: 16px 18px;
  }

  .chat-log {
    padding: 20px 18px;
    max-height: 60vh;
  }

  .message-row.user .message-bubble {
    max-width: 95%;
  }

  .control-panel {
    padding: 0 18px;
  }

  .composer {
    padding: 16px 18px;
  }

  .studio-suggestion {
    align-items: flex-start;
    flex-direction: column;
  }

}

@media (max-width: 480px) {
  .control-panel {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }

  .tool-panel > summary {
    min-height: 32px;
  }

  .composer-actions span {
    max-width: 150px;
    line-height: 1.6;
  }

  .chat-empty {
    padding-inline: 0;
  }

  .tool-grid {
    grid-template-columns: minmax(0, 1fr);
  }

}

@media (prefers-reduced-motion: reduce) {
  .chat-log {
    scroll-behavior: auto;
  }

  .thread-item {
    transition: none;
  }

}
</style>
