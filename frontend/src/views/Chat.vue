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
              <p>{{ message.content }}</p>

              <div v-if="message.tool_events?.length" class="tool-events">
                <div v-for="event in message.tool_events" :key="`${message.id}-${event.name}`" class="tool-event">
                  <span :class="event.status">{{ event.name }}</span>
                  <small>{{ event.status === 'completed' ? event.output : event.error }}</small>
                </div>
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
            <strong>10</strong>
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
  type ChatToolEvent
} from '../api/agent'

type UiMessage = Partial<AgentMessage> & {
  local_id?: string
  role: 'user' | 'assistant'
  content: string
  pending?: boolean
  tool_events?: ChatToolEvent[]
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
  'check_xiaohongshu_login'
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

.tool-event {
  display: grid;
  gap: 5px;
  padding: 9px 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.58);
}

.tool-event span {
  color: #0f6156;
  font-size: 12px;
  font-weight: 800;
}

.tool-event span.failed {
  color: #9a3f33;
}

.tool-event small {
  overflow: hidden;
  color: #5f6b71;
  font-size: 12px;
  line-height: 1.5;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.composer {
  display: grid;
  gap: 12px;
  padding: 14px 16px 16px;
  border-top: 1px solid rgba(24, 33, 38, 0.08);
  background: rgba(255, 255, 255, 0.72);
}

.composer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.composer-actions span {
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
    grid-template-columns: 1fr;
  }

  .message-bubble {
    width: 100%;
  }

  .composer-actions {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
