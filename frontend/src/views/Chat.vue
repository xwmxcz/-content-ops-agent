<template>
  <div class="page chat-page">
    <section class="chat-topline">
      <div>
        <span class="hero-kicker">Tool Agent</span>
        <h1 class="page-title">Agent 对话</h1>
        <p class="page-subtitle">多轮会话、模型切换和内容工具调用都会记录在当前 thread。</p>
      </div>
      <div class="hero-actions">
        <el-button :icon="Refresh" :loading="threadsLoading" @click="loadThreads">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="startNewThread">新建会话</el-button>
      </div>
    </section>

    <section class="chat-workbench">
      <aside class="thread-panel">
        <div class="panel-head">
          <span>Threads</span>
          <strong>{{ threads.length }}</strong>
        </div>

        <div v-if="!threads.length" class="thread-empty">暂无会话</div>
        <button
          v-for="thread in threads"
          :key="thread.id"
          type="button"
          class="thread-item"
          :class="{ active: thread.id === activeThreadId }"
          @click="selectThread(thread.id)"
        >
          <span>{{ thread.title || thread.id }}</span>
          <small>{{ thread.message_count }} 条消息 · {{ thread.last_model || '自动模型' }}</small>
        </button>
      </aside>

      <main class="dialog-panel">
        <div class="dialog-head">
          <div>
            <span class="panel-kicker">Current Thread</span>
            <strong>{{ activeThreadId || 'New thread' }}</strong>
          </div>
          <el-button
            v-if="activeThreadId"
            :icon="Delete"
            text
            type="danger"
            aria-label="删除当前会话"
            @click="removeThread(activeThreadId)"
          />
        </div>

        <div ref="logRef" class="chat-log">
          <div v-if="!messages.length" class="chat-empty">
            <strong>开始一次运营对话</strong>
            <p>可以让 Agent 查询内容库、生成草稿、打磨内容或安排发布日历。</p>
          </div>

          <article
            v-for="message in messages"
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

              <section v-if="message.plan?.length" class="plan-board">
                <div class="plan-head">📋 Agent 计划</div>
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
                      {{ event.status === 'completed' ? 'ok' : 'failed' }}
                    </span>
                    <small class="tool-event-summary">{{ summarizeEvent(event) }}</small>
                  </summary>
                  <div class="tool-event-body">
                    <div v-if="hasArgs(event.args)" class="tool-event-section">
                      <div class="tool-event-label">args</div>
                      <pre>{{ prettyArgs(event.args) }}</pre>
                    </div>
                    <div v-if="event.status === 'completed'" class="tool-event-section">
                      <div class="tool-event-label">output</div>
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
            <el-button type="primary" :icon="Position" :loading="loading" @click="send">发送</el-button>
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
import { nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index'
import { Delete, Plus, Position, Refresh } from '@element-plus/icons-vue'
import ModelSelector from '../components/ModelSelector.vue'
import {
  chat,
  deleteAgentThread,
  getAgentMessages,
  getAgentThreads,
  type AgentMessage,
  type AgentThread,
  type ChatToolEvent,
  type PlanStep
} from '../api/agent'

type UiMessage = Partial<AgentMessage> & {
  local_id?: string
  role: 'user' | 'assistant'
  content: string
  pending?: boolean
  tool_events?: ChatToolEvent[]
  plan?: PlanStep[]
}

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

const input = ref('')
const loading = ref(false)
const threadsLoading = ref(false)
const activeThreadId = ref<string>()
const threads = ref<AgentThread[]>([])
const messages = ref<UiMessage[]>([])
const logRef = ref<HTMLElement>()
const modelConfig = reactive({ provider: '', model: '', temperature: 0.7, max_tokens: 2048 })

async function loadThreads() {
  threadsLoading.value = true
  try {
    threads.value = await getAgentThreads()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    threadsLoading.value = false
  }
}

async function selectThread(threadId: string) {
  activeThreadId.value = threadId
  try {
    messages.value = await getAgentMessages(threadId)
    await scrollToBottom()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function startNewThread() {
  activeThreadId.value = undefined
  messages.value = []
  input.value = ''
}

async function removeThread(threadId: string) {
  try {
    await deleteAgentThread(threadId)
    if (activeThreadId.value === threadId) {
      startNewThread()
    }
    await loadThreads()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || loading.value) return

  const localMessage: UiMessage = {
    local_id: `local-${Date.now()}`,
    role: 'user',
    content: text,
    provider: modelConfig.provider,
    model: modelConfig.model,
    pending: true,
    tool_events: []
  }
  messages.value.push(localMessage)
  input.value = ''
  loading.value = true
  await scrollToBottom()

  try {
    const result = await chat({
      message: text,
      thread_id: activeThreadId.value,
      provider: modelConfig.provider || undefined,
      model: modelConfig.model || undefined,
      temperature: modelConfig.temperature,
      max_tokens: modelConfig.max_tokens
    })
    localMessage.pending = false
    activeThreadId.value = result.thread_id
    messages.value.push({
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
    await loadThreads()
    await scrollToBottom()
  } catch (error) {
    localMessage.pending = false
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
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

function summarizeEvent(event: ChatToolEvent) {
  if (event.status === 'failed') {
    return event.error || event.output || 'failed'
  }
  const text = (event.output || '').replace(/\s+/g, ' ').trim()
  return text.length > 80 ? `${text.slice(0, 80)}…` : text
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

onMounted(loadThreads)
</script>

<style scoped>
.chat-page {
  display: grid;
  gap: 18px;
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
  color: #6b7468;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.chat-workbench {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr) 340px;
  gap: 14px;
  min-height: 680px;
}

@media (max-width: 1180px) {
  .chat-workbench {
    grid-template-columns: 220px minmax(0, 1fr);
    min-height: 0;
  }

  .control-panel {
    grid-column: 1 / -1;
  }
}

@media (max-width: 820px) {
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

  .composer-actions {
    align-items: stretch;
    flex-direction: column;
  }
}

.thread-panel,
.dialog-panel,
.control-panel,
.tool-panel {
  border: 1px solid rgba(24, 33, 38, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 18px 50px rgba(21, 31, 39, 0.08);
  backdrop-filter: blur(14px);
}

.thread-panel,
.control-panel {
  align-self: start;
  display: grid;
  gap: 12px;
  padding: 14px;
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

.panel-head span {
  color: #6c777d;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.panel-head strong {
  color: #182126;
}

.thread-empty {
  display: grid;
  min-height: 120px;
  place-items: center;
  color: #778187;
  font-size: 13px;
}

.thread-item {
  display: grid;
  gap: 5px;
  width: 100%;
  padding: 12px;
  border: 1px solid transparent;
  border-radius: 8px;
  color: #29363b;
  background: rgba(248, 244, 237, 0.72);
  text-align: left;
  cursor: pointer;
}

.thread-item.active {
  border-color: rgba(15, 133, 116, 0.24);
  background: rgba(122, 210, 192, 0.16);
}

.thread-item span {
  overflow: hidden;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thread-item small {
  overflow: hidden;
  color: #738086;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dialog-head {
  padding: 14px 16px;
  border-bottom: 1px solid rgba(24, 33, 38, 0.08);
}

.dialog-head strong {
  display: block;
  margin-top: 4px;
  color: #182126;
  word-break: break-word;
}

.chat-log {
  min-height: 0;
  padding: 18px;
  overflow: auto;
}

.chat-empty {
  display: grid;
  gap: 8px;
  min-height: 360px;
  place-items: center;
  color: #5d6a71;
  text-align: center;
}

.chat-empty strong {
  color: #182126;
  font-size: 18px;
}

.message-row {
  display: flex;
  margin-bottom: 14px;
}

.message-row.user {
  justify-content: flex-end;
}

.message-bubble {
  width: min(76%, 720px);
  padding: 13px 14px;
  border: 1px solid rgba(24, 33, 38, 0.08);
  border-radius: 8px;
  color: #1c2a30;
  background: rgba(248, 244, 237, 0.9);
}

.message-row.user .message-bubble {
  color: #f7fbf9;
  border-color: rgba(16, 45, 49, 0.18);
  background: linear-gradient(135deg, #173238, #14554e);
}

.message-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.message-meta span {
  font-weight: 800;
}

.message-meta small {
  overflow: hidden;
  color: rgba(28, 42, 48, 0.58);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.message-row.user .message-meta small {
  color: rgba(247, 251, 249, 0.72);
}

.message-bubble p {
  margin: 0;
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
}

.tool-events {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}

.plan-board {
  margin-bottom: 12px;
  padding: 10px 12px;
  border: 1px solid rgba(15, 97, 86, 0.16);
  border-radius: 8px;
  background: rgba(122, 210, 192, 0.08);
}

.plan-head {
  margin-bottom: 6px;
  color: #0f6156;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.plan-board ol {
  display: grid;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.plan-board li {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 13px;
  color: #29363b;
}

.plan-board li.completed {
  color: #0f6156;
}

.plan-board li.failed {
  color: #9a3f33;
}

.plan-board li.skipped {
  color: #738086;
}

.plan-marker {
  display: inline-block;
  width: 14px;
  flex-shrink: 0;
  text-align: center;
}

.plan-desc {
  flex: 1;
}

.plan-board small {
  color: #5f6b71;
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.tool-events-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: #5f6b71;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.tool-events-head strong {
  color: #0f6156;
  font-size: 13px;
}

.tool-event {
  border: 1px solid rgba(15, 97, 86, 0.16);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.66);
  overflow: hidden;
}

.tool-event.failed {
  border-color: rgba(154, 63, 51, 0.28);
  background: rgba(255, 240, 236, 0.72);
}

.tool-event > summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 8px;
  padding: 9px 10px;
  cursor: pointer;
  list-style: none;
  user-select: none;
}

.tool-event > summary::-webkit-details-marker {
  display: none;
}

.tool-event > summary::before {
  content: '▸';
  flex-shrink: 0;
  color: #738086;
  font-size: 10px;
  transition: transform 0.15s ease;
}

.tool-event[open] > summary::before {
  transform: rotate(90deg);
}

.tool-event-index {
  flex-shrink: 0;
  color: #738086;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.04em;
}

.tool-event-name {
  color: #0f6156;
  font-size: 13px;
  font-weight: 800;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  word-break: break-all;
}

.tool-event.failed .tool-event-name {
  color: #9a3f33;
}

.tool-event-badge {
  flex-shrink: 0;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.tool-event-attempt {
  flex-shrink: 0;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(196, 122, 22, 0.16);
  color: #c47a16;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.04em;
}

.tool-event-badge.completed {
  color: #0f6156;
  background: rgba(122, 210, 192, 0.28);
}

.tool-event-badge.failed {
  color: #fff;
  background: #9a3f33;
}

.tool-event-summary {
  flex: 1 1 200px;
  min-width: 0;
  overflow: hidden;
  color: #5f6b71;
  font-size: 12px;
  line-height: 1.5;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-event-body {
  display: grid;
  gap: 10px;
  padding: 0 10px 10px;
}

.tool-event-section {
  display: grid;
  gap: 4px;
}

.tool-event-label {
  color: #6c777d;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.tool-event-section pre {
  margin: 0;
  padding: 8px 10px;
  border-radius: 6px;
  background: rgba(24, 33, 38, 0.06);
  color: #1c2a30;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
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
  background: rgba(154, 63, 51, 0.08);
  color: #6c241a;
}

.composer {
  display: grid;
  gap: 12px;
  padding: 14px 16px 16px;
  border-top: 1px solid rgba(24, 33, 38, 0.08);
  background: rgba(255, 255, 255, 0.72);
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
  color: #6a767b;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-panel {
  display: grid;
  gap: 12px;
  padding: 14px;
}

.tool-grid {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.tool-grid span {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 9px;
  border-radius: 999px;
  color: #425158;
  background: rgba(248, 244, 237, 0.86);
  font-size: 12px;
}

@media (max-width: 1180px) {
  .chat-workbench {
    grid-template-columns: 220px minmax(0, 1fr);
    min-height: 0;
  }

  .control-panel {
    grid-column: 1 / -1;
  }
}

@media (max-width: 820px) {
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

  .composer-actions {
    align-items: stretch;
    flex-direction: column;
  }
}

/* original duplicate breakpoints removed below */
</style>
