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
  font-size: 32px;
  font-weight: 600;
  letter-spacing: -0.025em;
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
  grid-template-columns: 260px minmax(0, 1fr) 340px;
  gap: 16px;
  min-height: 680px;
  height: calc(100vh - 200px);
  max-height: 920px;
}

/* Panel shells ---------------------------------------------------------- */

.thread-panel,
.dialog-panel,
.control-panel,
.tool-panel {
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg);
  box-shadow: none;
  backdrop-filter: none;
}

.thread-panel,
.control-panel {
  align-self: start;
  display: grid;
  gap: 12px;
  padding: 16px;
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

.thread-empty {
  display: grid;
  min-height: 120px;
  place-items: center;
  color: var(--c-text-tertiary);
  font-size: 13px;
}

/* Thread list items ----------------------------------------------------- */

.thread-item {
  display: grid;
  gap: 4px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid transparent;
  border-radius: 4px;
  color: var(--c-text);
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background-color 80ms ease, border-color 80ms ease;
}

.thread-item:hover {
  background: var(--c-bg-soft);
}

.thread-item.active {
  border-color: var(--c-accent);
  background: var(--c-accent-soft);
}

.thread-item span {
  overflow: hidden;
  font-weight: 600;
  font-size: 13px;
  letter-spacing: -0.01em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thread-item small {
  overflow: hidden;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-family: var(--font-mono);
  text-overflow: ellipsis;
  white-space: nowrap;
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
  background: var(--c-bg);
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
  letter-spacing: -0.015em;
}

.chat-empty p {
  margin: 0;
  color: var(--c-text-secondary);
  font-size: 13px;
}

/* Messages -------------------------------------------------------------- */

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
  background: var(--c-bg);
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
  letter-spacing: -0.01em;
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

.tool-events {
  display: grid;
  gap: 6px;
  margin-top: 14px;
}

/* Plan board (CLI checklist style) -------------------------------------- */

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

/* Tool events (structured log entries) ---------------------------------- */

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
  background: var(--c-bg);
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
  letter-spacing: -0.01em;
  word-break: break-all;
  flex-shrink: 0;
}

.tool-event.failed .tool-event-name {
  color: var(--c-fail);
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

/* Composer -------------------------------------------------------------- */

.composer {
  display: grid;
  gap: 10px;
  padding: 14px 20px 16px;
  border-top: 1px solid var(--c-border);
  background: var(--c-bg);
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

/* Tool grid (right rail) ------------------------------------------------ */

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
  background: var(--c-bg);
  font-size: 11px;
  font-family: var(--font-mono);
  letter-spacing: -0.01em;
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

  .composer-actions {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
