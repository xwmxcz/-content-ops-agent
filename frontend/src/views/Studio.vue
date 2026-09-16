<template>
  <div class="studio-page">
    <section class="studio-banner">
      <div class="banner-copy">
        <h1>{{ modeTitle }}</h1>
        <p>{{ modeDescription }}</p>
      </div>
      <el-segmented v-model="mode" :options="modeOptions" :disabled="running" class="mode-toggle" />
    </section>

    <section class="run-strip">
      <div class="signal-row">
        <div class="signal-card" v-for="card in signalCards" :key="card.label" :title="card.note">
          <span>{{ card.label }}</span>
          <strong>{{ card.value }}</strong>
        </div>
      </div>
      <div class="run-actions">
        <template v-if="!running">
          <button class="ghost-action" type="button" :disabled="!hasOutput" @click="resetWorkspace">
            <el-icon><Refresh /></el-icon>
            <span>重置</span>
          </button>
          <el-button type="primary" size="large" :icon="VideoPlay" :disabled="!dynamicSourcesValid" @click="run">
            运行
          </el-button>
        </template>
        <template v-else>
          <div class="run-progress">
            <div class="progress-bar">
              <div class="progress-bar-fill" :style="{ width: `${progressPercent}%` }"></div>
            </div>
            <div class="progress-meta">
              <span class="progress-state">{{ statusText }}</span>
              <span class="progress-count">{{ progressLabel }}</span>
            </div>
          </div>
          <button class="stop-action" type="button" @click="stop">
            <el-icon><CircleClose /></el-icon>
            <span>停止</span>
          </button>
        </template>
      </div>
    </section>

    <div class="studio-grid">
      <aside class="studio-rail">
        <section class="studio-surface">
          <div class="surface-head">
            <div>
              <h2>创作配置</h2>
            </div>
            <span class="surface-pill">{{ platformLabel }}</span>
          </div>
          <div class="field-stack">
            <div class="field-block">
              <span>内容主题</span>
              <el-input v-model="form.topic" type="textarea" :rows="5" placeholder="例如：周末徒步路线推荐" />
            </div>
            <div class="field-grid">
              <div class="field-block">
                <span>目标平台</span>
                <el-select v-model="form.content_type">
                  <el-option v-for="item in contentTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
              </div>
              <div class="field-block">
                <span>长度</span>
                <el-radio-group v-model="form.length" class="length-group">
                  <el-radio-button value="short">短</el-radio-button>
                  <el-radio-button value="medium">中</el-radio-button>
                  <el-radio-button value="long">长</el-radio-button>
                </el-radio-group>
              </div>
            </div>
            <div class="field-block">
              <span>内容风格</span>
              <el-segmented v-model="form.style" :options="styleOptions" class="style-segmented" />
            </div>
            <div class="field-block">
              <span>关键词</span>
              <el-input v-model="keywordsText" placeholder="徒步, 周末, 避坑" />
            </div>
          </div>
        </section>

        <section v-if="mode === 'dynamic'" class="studio-surface research-surface">
          <div class="surface-head compact">
            <div>
              <h2>研究来源</h2>
            </div>
            <span class="surface-pill mono">{{ activeSourceCount }}/2</span>
          </div>
          <div class="research-toggles">
            <div
              class="research-toggle"
              :class="{ active: research.use_web_search }"
              role="switch"
              :aria-checked="research.use_web_search"
              tabindex="0"
              @click="research.use_web_search = !research.use_web_search"
              @keydown.enter.prevent="research.use_web_search = !research.use_web_search"
              @keydown.space.prevent="research.use_web_search = !research.use_web_search"
            >
              <el-switch v-model="research.use_web_search" @click.stop />
              <div class="toggle-copy">
                <strong>网页检索</strong>
                <span>查找新近资料与对比信息</span>
              </div>
            </div>
            <div
              class="research-toggle"
              :class="{ active: research.use_history_search }"
              role="switch"
              :aria-checked="research.use_history_search"
              tabindex="0"
              @click="research.use_history_search = !research.use_history_search"
              @keydown.enter.prevent="research.use_history_search = !research.use_history_search"
              @keydown.space.prevent="research.use_history_search = !research.use_history_search"
            >
              <el-switch v-model="research.use_history_search" @click.stop />
              <div class="toggle-copy">
                <strong>历史内容库</strong>
                <span>参考已保存的内容</span>
              </div>
            </div>
          </div>
          <p class="research-note">本次研究仅使用已开启的来源。</p>
          <el-alert
            v-if="activeSourceCount === 0"
            type="warning"
            title="至少保留一个研究来源，Pipeline 才能开始运行。"
            show-icon
            :closable="false"
            class="surface-alert"
          />
          <div class="field-block">
            <span>研究侧重 (可选)</span>
            <el-input
              v-model="research.research_focus"
              placeholder="例：重点对比续航与降噪 / 核实价格与发布时间"
            />
          </div>
        </section>

        <section class="studio-surface">
          <div class="surface-head compact">
            <div>
              <h2>模型与执行参数</h2>
            </div>
          </div>
          <ModelSelector :model-value="modelConfig" @update:model-value="Object.assign(modelConfig, $event)" />
        </section>
      </aside>

      <main class="studio-center">
        <section class="studio-surface">
          <div class="surface-head">
            <div>
              <h2>{{ pipelineTitle }}</h2>
            </div>
            <div class="surface-actions">
              <span v-if="runId" class="surface-pill mono">{{ runId }}</span>
              <span class="surface-pill" :class="statusPillClass">{{ statusText }}</span>
            </div>
          </div>

          <el-alert v-if="errorMessage" type="error" :title="errorMessage" show-icon :closable="false" class="surface-alert" />

          <el-alert
            v-if="connectionNotice"
            :type="connectionNotice.type"
            :title="connectionNotice.title"
            show-icon
            :closable="false"
            class="surface-alert"
          >
            <el-button
              v-if="connectionNotice.canRetry"
              size="small"
              :loading="reconciling"
              @click="retryStream"
            >
              重新连接
            </el-button>
          </el-alert>

          <div v-if="!plan.length && !running" class="timeline-empty">
            <div v-if="mode === 'workflow'" class="flow-preview" aria-label="创作流程：策略、初稿、润色、审核">
              <span><small>01</small> 策略</span>
              <span><small>02</small> 初稿</span>
              <span><small>03</small> 润色</span>
              <span><small>04</small> 审核</span>
            </div>
            <p>{{ mode === 'dynamic' ? '填写主题并点击“运行”，自动规划研究步骤，边查证边创作。' : '填写左侧创作配置，点击“运行”开始。你可以随时查看每一步的内容。' }}</p>
          </div>

          <ol v-else class="timeline">
            <li
              v-for="step in plan"
              :key="`${step.index}-${step.agent_id}`"
              class="timeline-step"
              :class="[step.status, { 'is-revised': step.revised_at, 'is-research': isResearchStep(step.agent_id) }]"
              tabindex="0"
              role="button"
              :aria-label="`跳转到第 ${step.index} 步 ${agentLabel(step.agent_id)}`"
              @click="scrollToStep(step.index)"
              @keydown.enter.prevent="scrollToStep(step.index)"
              @keydown.space.prevent="scrollToStep(step.index)"
            >
              <div class="timeline-head">
                <span class="timeline-index">{{ step.index }}</span>
                <strong class="timeline-name">
                  <span v-if="isResearchStep(step.agent_id)" class="research-glyph" aria-hidden="true">
                    {{ step.agent_id === 'researcher' ? 'R' : 'F' }}
                  </span>
                  {{ agentLabel(step.agent_id) }}
                </strong>
                <div class="timeline-meta">
                  <small v-if="toolEventsFor(step.index).length" class="tool-pill" :title="`${toolEventsFor(step.index).length} 个工具调用`">
                    工具 {{ toolEventsFor(step.index).length }}
                  </small>
                  <small v-if="step.duration_ms" class="timeline-duration">{{ step.duration_ms }} ms</small>
                  <span class="timeline-chevron" aria-hidden="true">›</span>
                </div>
              </div>
              <div v-if="step.revised_at" class="timeline-revised-badge">Planner 修改</div>
            </li>
          </ol>
        </section>

        <el-dialog
          v-model="stepDialogOpen"
          :title="stepDialogStep ? `Step ${stepDialogStep.index} · ${agentLabel(stepDialogStep.agent_id)}` : ''"
          width="720px"
          append-to-body
          destroy-on-close
        >
          <template v-if="stepDialogStep">
            <div class="step-dialog-meta">
              <span class="surface-kicker">
                {{ stepDialogStep.agent_id }}
                <span v-if="isResearchStep(stepDialogStep.agent_id)" class="research-tag">research</span>
              </span>
              <span class="surface-pill" :class="statusToPill(stepDialogStep.status)">{{ statusLabel(stepDialogStep.status) }}</span>
              <small v-if="stepDialogStep.duration_ms" class="step-dialog-duration">{{ stepDialogStep.duration_ms }} ms</small>
            </div>
            <p class="step-description">{{ stepDialogStep.description }}</p>
            <ul v-if="toolEventsFor(stepDialogStep.index).length" class="tool-trace">
              <li
                v-for="(event, idx) in toolEventsFor(stepDialogStep.index)"
                :key="`${stepDialogStep.index}-${idx}-${event.name}`"
                class="tool-row"
                :class="event.status"
              >
                <span class="tool-arrow">▸</span>
                <span class="tool-name">{{ event.name }}</span>
                <span v-if="formatToolArgs(event.args)" class="tool-args">({{ formatToolArgs(event.args) }})</span>
                <span v-if="event.status === 'started'" class="tool-status">运行中…</span>
                <template v-else>
                  <span class="tool-arrow">→</span>
                  <span v-if="event.status === 'failed'" class="tool-error">{{ event.error || '失败' }}</span>
                  <span v-else class="tool-preview">{{ formatToolPreview(event.preview) }}</span>
                  <span v-if="event.duration_ms" class="tool-duration">{{ event.duration_ms }} ms</span>
                </template>
              </li>
            </ul>
            <pre v-if="stepDialogStep.output || streamingOutputs[stepDialogStep.index]" class="step-output">{{ stepDialogStep.output || streamingOutputs[stepDialogStep.index] }}</pre>
            <div v-else-if="stepDialogStep.status === 'running'" class="step-running">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>正在生成…</span>
            </div>
            <div v-else-if="stepDialogStep.status === 'completed'" class="step-empty">
              该步骤未产出文本输出，仅记录上方工具调用。
            </div>
            <div v-else-if="stepDialogStep.status === 'failed'" class="step-empty failed">
              步骤失败，未产出输出
            </div>
            <div v-else-if="stepDialogStep.status === 'skipped'" class="step-empty">已跳过</div>
            <div v-else class="step-pending">等待执行</div>
          </template>
        </el-dialog>

        <section v-if="finalContent" class="studio-surface final-surface">
          <div class="surface-head">
            <div>
              <span class="surface-kicker">最终内容</span>
              <h2>{{ finalContent.title || form.topic || '未命名' }}</h2>
            </div>
            <div class="surface-actions">
              <span v-if="savedContentId" class="surface-pill success">已保存 #{{ savedContentId }}</span>
              <button
                v-if="savedContentId"
                class="ghost-action accent"
                type="button"
                @click="optimizeInChat"
              >
                <el-icon><ChatDotRound /></el-icon>
                <span>在 Chat 中优化</span>
              </button>
              <button class="ghost-action" type="button" @click="copyFinal">
                <el-icon><DocumentCopy /></el-icon>
                <span>复制</span>
              </button>
            </div>
          </div>
          <pre class="final-body">{{ finalContent.content }}</pre>
        </section>
        <section v-else class="studio-surface draft-placeholder">
          <div class="draft-icon"><el-icon><DocumentCopy /></el-icon></div>
          <h2>{{ running ? '好内容，正在成稿' : '从一个想法，写出下一篇' }}</h2>
          <p>{{ running ? '创作完成后，最终稿件会显示在这里。' : '告诉我们你想写什么，剩下的交给创作工作流。' }}</p>
          <span>最终稿件 · 可复制与继续打磨</span>
        </section>
      </main>
    </div>
  </div>
</template>

<!-- SCRIPT_PLACEHOLDER -->

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElAlert } from 'element-plus/es/components/alert/index'
import { ElDialog } from 'element-plus/es/components/dialog/index'
import { ElMessage } from 'element-plus/es/components/message/index'
import { ElRadioButton, ElRadioGroup } from 'element-plus/es/components/radio/index'
import { ElSegmented } from 'element-plus/es/components/segmented/index'
import { ElSwitch } from 'element-plus/es/components/switch/index'
import 'element-plus/es/components/alert/style/css'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/es/components/radio/style/css'
import 'element-plus/es/components/segmented/style/css'
import 'element-plus/es/components/switch/style/css'
import {
  CircleClose,
  ChatDotRound,
  DocumentCopy,
  Loading,
  Refresh,
  VideoPlay
} from '@element-plus/icons-vue'
import ModelSelector from '../components/ModelSelector.vue'
import {
  cancelPipelineRun,
  createPipelineRun,
  getPipelineRun,
  type PipelinePlanStep,
  type PipelineRunPayload,
  type SubAgentId,
  type SubAgentToolEvent
} from '../api/agent'
import {
  cancelJob,
  createAgentRunJob,
  extractAgentRun,
  type JobResponse
} from '../api/jobs'
import { useJobPolling } from '../composables/useJobPolling'
import { usePipelineStream, type StreamConnectionState } from '../composables/usePipelineStream'
import type { AgentRunPayload, AgentRunResponse, AgentStep } from '../api/agent'

interface FinalContent {
  title?: string
  content: string
  content_type: string
  style: string
  tags: string[]
}

type Mode = 'dynamic' | 'workflow'
type RunStatus = 'idle' | 'planning' | 'running' | 'completed' | 'failed' | 'cancelled'

const route = useRoute()
const router = useRouter()

const contentTypeOptions = [
  { label: '小红书', value: 'xiaohongshu' },
  { label: '微博', value: 'weibo' },
  { label: '博客文章', value: 'blog' },
  { label: '视频脚本', value: 'video_script' },
  { label: 'Twitter / X', value: 'twitter' }
]

const styleOptions = [
  { label: '专业', value: 'professional' },
  { label: '轻松', value: 'casual' },
  { label: '营销', value: 'marketing' },
  { label: '故事', value: 'storytelling' }
]

const QUICK_PROMPTS_BY_MODE: Record<Mode, string[]> = {
  workflow: [],
  dynamic: []
}

const quickPrompts = computed(() => QUICK_PROMPTS_BY_MODE[mode.value])
void quickPrompts // kept for future re-introduction; not currently rendered

const modeOptions = [
  { label: '标准工作流', value: 'workflow' },
  { label: '研究型 Pipeline', value: 'dynamic' }
]

const AGENT_LABELS: Record<string, string> = {
  strategy: '策略',
  writer: '初稿',
  editor: '润色',
  reviewer: '审核',
  review: '审核',
  researcher: '调研',
  fact_checker: '事实校验'
}

const WORKFLOW_DESCRIPTIONS: Record<string, string> = {
  strategy: '分析受众、角度、结构与转化意图',
  writer: '把策略转成可编辑的第一版内容',
  editor: '优化表达、节奏与平台适配',
  review: '给出 1-100 分以及风险与改进建议'
}

const initialMode: Mode = route.query.mode === 'dynamic' ? 'dynamic' : 'workflow'
const mode = ref<Mode>(initialMode)

const form = reactive({
  topic: '',
  content_type: 'xiaohongshu',
  style: 'professional',
  length: 'medium'
})

const research = reactive({
  use_web_search: true,
  use_history_search: true,
  research_focus: ''
})

const modelConfig = reactive({
  provider: '',
  model: '',
  temperature: 0.7,
  max_tokens: 2048
})

const keywordsText = ref('')
const running = ref(false)
const errorMessage = ref('')
const runId = ref('')
const plan = ref<PipelinePlanStep[]>([])
const streamingOutputs = reactive<Record<number, string>>({})
const stepToolEvents = reactive<Record<number, SubAgentToolEvent[]>>({})
const stepDialogOpen = ref(false)
const stepDialogIndex = ref<number | null>(null)
const stepDialogStep = computed<PipelinePlanStep | null>(() =>
  stepDialogIndex.value == null ? null : plan.value.find(s => s.index === stepDialogIndex.value) ?? null
)
const finalContent = ref<FinalContent | null>(null)
const savedContentId = ref<number | null>(null)
const totalPromptTokens = ref(0)
const totalCompletionTokens = ref(0)
const totalCost = ref(0)
const revisionCount = ref(0)
const status = ref<RunStatus>('idle')
// Transport health is tracked separately from run status: a broken stream does
// not mean a broken run, and conflating them made every network blip look like a
// pipeline failure.
const connectionState = ref<StreamConnectionState>('idle')
const streamExhausted = ref(false)
const reconciling = ref(false)
const isRunActive = computed(() => status.value === 'planning' || status.value === 'running')

let workflowJobId: string | null = null
const workflowPolling = useJobPolling()
const pipelineStream = usePipelineStream({
  onPlanReady(nextPlan) {
    plan.value = nextPlan.map(step => ({ ...step }))
    status.value = 'running'
  },
  onStepStart(index) {
    streamingOutputs[index] = ''
    stepToolEvents[index] = []
    const step = plan.value.find(s => s.index === index)
    if (step) step.status = 'running'
  },
  onStepToken(index, delta) {
    streamingOutputs[index] = (streamingOutputs[index] || '') + delta
  },
  onToolCallStart(event) {
    if (!stepToolEvents[event.index]) stepToolEvents[event.index] = []
    stepToolEvents[event.index].push({
      name: event.name,
      args: event.args || {},
      status: 'started',
      preview: '',
      duration_ms: 0
    })
  },
  onToolCallResult(event) {
    const list = stepToolEvents[event.index] || (stepToolEvents[event.index] = [])
    const pending = [...list].reverse().find(t => t.name === event.name && t.status === 'started')
    const nextEvent: SubAgentToolEvent = {
      name: event.name,
      args: event.args || {},
      status: event.status,
      preview: event.preview || '',
      error: event.error || null,
      duration_ms: event.duration_ms || 0
    }
    if (pending) Object.assign(pending, nextEvent)
    else list.push(nextEvent)
  },
  onStepComplete(event) {
    const step = plan.value.find(s => s.index === event.index)
    if (step) {
      step.status = 'completed'
      step.output = event.output
      step.duration_ms = event.duration_ms
      step.prompt_tokens = event.prompt_tokens
      step.completion_tokens = event.completion_tokens
      step.cost_estimate = event.cost_estimate
      step.tool_events = event.tool_events || []
    }
    streamingOutputs[event.index] = event.output
    if (event.tool_events) stepToolEvents[event.index] = event.tool_events
    totalPromptTokens.value += event.prompt_tokens
    totalCompletionTokens.value += event.completion_tokens
    totalCost.value += event.cost_estimate
  },
  onStepFailed(index, error) {
    const step = plan.value.find(s => s.index === index)
    if (step) step.status = 'failed'
    errorMessage.value = `Step ${index} 失败：${error}`
  },
  onPlanRevised(nextPlan, revision) {
    const knownIndices = new Set(plan.value.map(s => s.index))
    plan.value = nextPlan.map(step => {
      const isNew = !knownIndices.has(step.index)
      return { ...step, revised_at: isNew ? revision : step.revised_at }
    })
    revisionCount.value = revision
  },
  onRunComplete(event) {
    finalContent.value = event.final_content
    savedContentId.value = event.saved_content_id ?? null
    totalPromptTokens.value = event.total_prompt_tokens
    totalCompletionTokens.value = event.total_completion_tokens
    totalCost.value = event.total_cost
    revisionCount.value = event.revision_count
    status.value = 'completed'
    running.value = false
    closeStream()
    ElMessage.success(savedContentId.value ? `已完成，已保存 #${savedContentId.value}` : '已完成')
  },
  onRunFailed(error) {
    status.value = 'failed'
    running.value = false
    errorMessage.value = error || '运行失败'
    closeStream()
  },
  onRunCancelled() {
    status.value = 'cancelled'
    running.value = false
    errorMessage.value = '已停止运行'
    closeStream()
  },
  onConnectionLost() {
    // Retries are spent. The run may still be progressing server-side, so ask the
    // API for authoritative state instead of declaring failure.
    streamExhausted.value = true
    void reconcileRun()
  },
  onStateChange(next) {
    connectionState.value = next.state
    if (next.state === 'open') streamExhausted.value = false
  }
})

const connectionNotice = computed(() => {
  if (!isRunActive.value && !streamExhausted.value) return null
  if (streamExhausted.value) {
    return {
      type: 'warning' as const,
      title: '实时连接已断开，运行可能仍在后台继续。已同步一次最新状态。',
      canRetry: true
    }
  }
  if (connectionState.value === 'reconnecting') {
    return { type: 'info' as const, title: '连接中断，正在自动重连…', canRetry: false }
  }
  if (connectionState.value === 'stale') {
    return { type: 'info' as const, title: '连接空闲，等待服务端事件…', canRetry: true }
  }
  return null
})

/**
 * Pulls authoritative run state after the stream gives up. Terminal statuses are
 * applied to the view; a still-running run leaves the UI running so the user can
 * reconnect rather than losing the run.
 */
async function reconcileRun() {
  const id = runId.value
  if (!id) return
  reconciling.value = true
  try {
    const snapshot = await getPipelineRun(id)
    if (snapshot.plan?.length) plan.value = snapshot.plan.map(step => ({ ...step }))
    totalPromptTokens.value = snapshot.total_prompt_tokens ?? totalPromptTokens.value
    totalCompletionTokens.value = snapshot.total_completion_tokens ?? totalCompletionTokens.value
    totalCost.value = snapshot.total_cost ?? totalCost.value
    revisionCount.value = snapshot.revision_count ?? revisionCount.value

    if (snapshot.status === 'completed') {
      savedContentId.value = snapshot.saved_content_id ?? null
      status.value = 'completed'
      running.value = false
      streamExhausted.value = false
    } else if (snapshot.status === 'failed') {
      status.value = 'failed'
      running.value = false
      errorMessage.value = snapshot.error || '运行失败'
      streamExhausted.value = false
    } else if (snapshot.status === 'cancelled') {
      status.value = 'cancelled'
      running.value = false
      errorMessage.value = snapshot.error || '已停止运行'
      streamExhausted.value = false
    }
    // Still running: keep the banner and the retry affordance in place.
  } catch {
    // Reconciliation is best-effort. Leaving the banner up is more honest than
    // inventing a terminal state from a failed status probe.
  } finally {
    reconciling.value = false
  }
}

async function retryStream() {
  if (!runId.value) return
  streamExhausted.value = false
  await reconcileRun()
  if (isRunActive.value) pipelineStream.resume()
}

const totalTokens = computed(() => totalPromptTokens.value + totalCompletionTokens.value)
void totalTokens // kept for future re-introduction; not currently displayed
const completedSteps = computed(() => plan.value.filter(s => s.status === 'completed').length)
const totalPlanSteps = computed(() => plan.value.length || (mode.value === 'workflow' ? 4 : 0))

const progressPercent = computed(() => {
  if (status.value === 'planning') return 6
  if (!totalPlanSteps.value) return 4
  return Math.min(100, Math.round((completedSteps.value / totalPlanSteps.value) * 100))
})

const progressLabel = computed(() => {
  if (status.value === 'planning') return 'Planner 规划中'
  if (!totalPlanSteps.value) return '提交中'
  return `${completedSteps.value} / ${totalPlanSteps.value} 步`
})

const platformLabel = computed(
  () => contentTypeOptions.find(item => item.value === form.content_type)?.label ?? form.content_type
)

const modeTitle = computed(() =>
  mode.value === 'dynamic'
    ? '研究型创作'
    : '创作工作台'
)

const modeDescription = computed(() =>
  mode.value === 'dynamic'
    ? '先研究，再动笔。为横评、对比与深度内容找到可靠依据。'
    : '从选题到成稿，让每一步创作都有条不紊。'
)

const activeSourceCount = computed(() =>
  Number(research.use_web_search) + Number(research.use_history_search)
)

const dynamicSourcesValid = computed(() =>
  mode.value !== 'dynamic' || activeSourceCount.value > 0
)

const RESEARCH_AGENTS = new Set(['researcher', 'fact_checker'])

function isResearchStep(agentId: string): boolean {
  return RESEARCH_AGENTS.has(agentId)
}

const pipelineTitle = computed(() => {
  if (status.value === 'planning') return '正在规划研究步骤…'
  if (status.value === 'running') return '执行中…'
  if (status.value === 'completed') return '执行完成'
  if (status.value === 'failed') return '执行失败'
  if (status.value === 'cancelled') return '已停止'
  return mode.value === 'dynamic' ? '研究与创作进度' : '创作进度'
})

const statusText = computed(() => {
  switch (status.value) {
    case 'planning':
      return '规划中'
    case 'running':
      return '运行中'
    case 'completed':
      return '已完成'
    case 'failed':
      return '失败'
    case 'cancelled':
      return '已停止'
    default:
      return '待开始'
  }
})

const statusPillClass = computed(() => {
  if (status.value === 'running' || status.value === 'planning') return 'running'
  if (status.value === 'completed') return 'success'
  if (status.value === 'failed') return 'failed'
  if (status.value === 'cancelled') return 'warn'
  return ''
})

const keywordList = computed(() =>
  keywordsText.value
    .split(/[,\n，]/)
    .map(item => item.trim())
    .filter(Boolean)
)

const hasOutput = computed(() => !!finalContent.value || plan.value.length > 0 || !!errorMessage.value)

const totalToolCalls = computed(() =>
  plan.value.reduce((sum, step) => sum + toolEventsFor(step.index).length, 0)
)

const signalCards = computed(() => {
  if (mode.value === 'dynamic') {
    return [
      { label: '模式', value: '研究型', note: '先研究，再创作' },
      { label: '步骤', value: totalPlanSteps.value || '—', note: totalPlanSteps.value ? `${completedSteps.value} 已完成` : '等待计划' },
      { label: '工具调用', value: totalToolCalls.value, note: totalToolCalls.value ? '研究 / 校验工具已被调用' : '尚未调用工具' },
      { label: '计划调整', value: revisionCount.value, note: revisionCount.value ? '已调整研究计划' : '尚未调整计划' }
    ]
  }
  return [
    { label: '模式', value: '标准工作流', note: '策略、初稿、润色、审核四个阶段' },
    { label: '步骤', value: totalPlanSteps.value || '—', note: totalPlanSteps.value ? `${completedSteps.value} 已完成` : '等待计划' },
    { label: '状态', value: statusText.value, note: progressLabel.value },
    { label: '已保存', value: savedContentId.value ? `#${savedContentId.value}` : '—', note: savedContentId.value ? '可在 Chat 中优化' : '尚未保存' }
  ]
})

watch(mode, value => {
  if (route.query.mode !== value) {
    router.replace({ query: { ...route.query, mode: value } })
  }
})

function agentLabel(id: string): string {
  return AGENT_LABELS[id] ?? id
}

function statusLabel(s: PipelinePlanStep['status']) {
  const map: Record<PipelinePlanStep['status'], string> = {
    pending: '待运行',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    skipped: '已跳过'
  }
  return map[s]
}

function statusToPill(s: PipelinePlanStep['status']) {
  if (s === 'running') return 'running'
  if (s === 'completed') return 'success'
  if (s === 'failed') return 'failed'
  return ''
}

function toolEventsFor(stepIndex: number): SubAgentToolEvent[] {
  const live = stepToolEvents[stepIndex]
  if (live && live.length) return live
  const step = plan.value.find(s => s.index === stepIndex)
  return step?.tool_events ?? []
}

function registerStepCard(_index: number, _el: HTMLElement | null): void {
  // No-op now that step detail lives in a dialog. Kept so the template's
  // legacy :ref="..." (if any other path still passes through) doesn't error.
}

function scrollToStep(index: number): void {
  stepDialogIndex.value = index
  stepDialogOpen.value = true
}

function formatToolArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args || {})
  if (!entries.length) return ''
  return entries
    .map(([k, v]) => `${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`)
    .join(', ')
}

function formatToolPreview(preview?: string | null): string {
  const trimmed = (preview || '').trim()
  if (!trimmed) return '完成'
  try {
    const parsed = JSON.parse(trimmed)
    if (Array.isArray(parsed) && parsed.length === 0) return '无结果'
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && Object.keys(parsed).length === 0) {
      return '无结果'
    }
  } catch {
    // Plain text previews are displayed as-is.
  }
  return trimmed
}

function resetWorkspace() {
  if (running.value) return
  closeStream()
  workflowJobId = null
  workflowPolling.reset()
  runId.value = ''
  plan.value = []
  Object.keys(streamingOutputs).forEach(k => delete streamingOutputs[Number(k)])
  Object.keys(stepToolEvents).forEach(k => delete stepToolEvents[Number(k)])
  finalContent.value = null
  savedContentId.value = null
  totalPromptTokens.value = 0
  totalCompletionTokens.value = 0
  totalCost.value = 0
  revisionCount.value = 0
  errorMessage.value = ''
  status.value = 'idle'
  connectionState.value = 'idle'
  streamExhausted.value = false
}

function closeStream() {
  pipelineStream.close()
}

function stop() {
  if (mode.value === 'dynamic') {
    const id = runId.value
    if (id) {
      // Fire-and-forget: backend DELETE flips run.status to "cancelled" and
      // emits run_cancelled, which lets the in-flight pipeline exit at the next
      // step boundary. We don't await — the UI shouldn't block on the network.
      cancelPipelineRun(id).catch(() => {
        /* already terminal or network blip — frontend state is already 'cancelled' */
      })
    }
    closeStream()
  } else {
    workflowPolling.abort()
    if (workflowJobId) {
      cancelJob(workflowJobId).catch(() => {
        /* already terminal or network blip — frontend state is already 'cancelled' */
      })
    }
  }
  running.value = false
  status.value = 'cancelled'
  errorMessage.value = '已停止运行'
  // A user-initiated stop is not a transport problem: drop the reconnect banner.
  streamExhausted.value = false
}

async function run() {
  if (!form.topic.trim()) {
    ElMessage.warning('请输入内容主题')
    return
  }
  if (!dynamicSourcesValid.value) {
    ElMessage.warning('至少保留一个研究来源')
    return
  }
  resetWorkspace()
  running.value = true
  if (mode.value === 'dynamic') {
    await runDynamic()
  } else {
    await runWorkflow()
  }
}

async function runDynamic() {
  status.value = 'planning'
  const payload: PipelineRunPayload = {
    topic: form.topic.trim(),
    content_type: form.content_type,
    style: form.style,
    length: form.length,
    keywords: keywordList.value,
    provider: modelConfig.provider || undefined,
    model: modelConfig.model || undefined,
    temperature: modelConfig.temperature,
    max_tokens: modelConfig.max_tokens,
    save_final: true,
    use_web_search: research.use_web_search,
    use_history_search: research.use_history_search,
    research_focus: research.research_focus.trim() || undefined
  }

  try {
    const handle = await createPipelineRun(payload)
    runId.value = handle.run_id
    await subscribe(handle.run_id)
  } catch (error) {
    running.value = false
    status.value = 'failed'
    errorMessage.value = (error as Error).message
    ElMessage.error(errorMessage.value)
  }
}

async function subscribe(id: string) {
  await pipelineStream.subscribe(id)
}

async function runWorkflow() {
  workflowPolling.reset()
  plan.value = ['strategy', 'writer', 'editor', 'review'].map((id, idx) => ({
    index: idx + 1,
    agent_id: id as SubAgentId,
    description: WORKFLOW_DESCRIPTIONS[id] || '',
    instruction: '',
    inputs_from: [],
    status: idx === 0 ? 'running' : 'pending',
    output: '',
    duration_ms: 0,
    prompt_tokens: 0,
    completion_tokens: 0,
    cost_estimate: 0
  }))
  status.value = 'running'

  const payload: AgentRunPayload = {
    topic: form.topic.trim(),
    content_type: form.content_type,
    style: form.style,
    length: form.length,
    keywords: keywordList.value,
    provider: modelConfig.provider || undefined,
    model: modelConfig.model || undefined,
    temperature: modelConfig.temperature,
    max_tokens: modelConfig.max_tokens,
    save_final: true
  }

  try {
    const job = await createAgentRunJob(payload)
    workflowJobId = job.id
    runId.value = job.id
    const result = await pollWorkflowJob(job.id)
    if (workflowPolling.isAborted()) return
    applyWorkflowResult(result)
  } catch (error) {
    if (workflowPolling.isAborted()) return
    running.value = false
    status.value = 'failed'
    errorMessage.value = (error as Error).message
    ElMessage.error(errorMessage.value)
  }
}

async function pollWorkflowJob(jobId: string): Promise<AgentRunResponse> {
  return workflowPolling.poll(jobId, {
    extract: extractAgentRun,
    onUpdate: advanceWorkflowSteps
  })
}

function advanceWorkflowSteps(job: JobResponse) {
  if (!plan.value.length) return
  const expected = Math.min(plan.value.length, Math.max(1, Math.floor(((job.progress || 0) / 100) * plan.value.length)))
  for (let i = 0; i < plan.value.length; i++) {
    const step = plan.value[i]
    if (i < expected - 1) {
      if (step.status !== 'completed') step.status = 'completed'
    } else if (i === expected - 1) {
      if (step.status !== 'completed') step.status = 'running'
    }
  }
}

function applyWorkflowResult(result: AgentRunResponse) {
  result.steps.forEach((step: AgentStep, idx: number) => {
    const target = plan.value[idx]
    if (!target) return
    target.agent_id = step.id as SubAgentId
    target.description = step.role || target.description
    target.status = step.status === 'failed' ? 'failed' : 'completed'
    target.output = step.output || ''
    target.duration_ms = step.duration_ms || 0
  })
  finalContent.value = {
    title: result.final_content.title,
    content: result.final_content.content,
    content_type: result.final_content.content_type,
    style: result.final_content.style,
    tags: result.final_content.tags || []
  }
  savedContentId.value = result.saved_content_id ?? null
  status.value = 'completed'
  running.value = false
  ElMessage.success(savedContentId.value ? `已完成，已保存 #${savedContentId.value}` : '已完成')
}

async function copyFinal() {
  if (!finalContent.value?.content) return
  try {
    await navigator.clipboard.writeText(finalContent.value.content)
    ElMessage.success('已复制最终稿')
  } catch {
    ElMessage.error('复制失败，请手动选择文本复制')
  }
}

function optimizeInChat() {
  if (!savedContentId.value) return
  const title = finalContent.value?.title?.trim() || ''
  const seed = title
    ? `帮我优化 #${savedContentId.value}（《${title}》）这篇内容：先调用 view_content 看一下当前版本，然后给出 2-3 条具体的改进方向，等我确认后再调 refine_content。`
    : `帮我优化 #${savedContentId.value} 这篇内容：先调用 view_content 看一下当前版本，然后给出 2-3 条具体的改进方向，等我确认后再调 refine_content。`
  router.push({ path: '/chat', query: { seed } })
}

onMounted(() => {
  const topic = typeof route.query.topic === 'string' ? route.query.topic.trim() : ''
  const researchFocus = typeof route.query.research_focus === 'string' ? route.query.research_focus.trim() : ''
  if (topic) form.topic = topic
  if (researchFocus) research.research_focus = researchFocus
  if (topic || researchFocus) {
    const nextQuery: Record<string, string> = {}
    if (typeof route.query.mode === 'string' && route.query.mode) nextQuery.mode = route.query.mode
    void router.replace({ query: nextQuery })
  }
})

onBeforeUnmount(() => {
  closeStream()
})
</script>

<!-- STYLE_PLACEHOLDER -->

<style scoped>
.studio-page {
  max-width: 1520px;
  margin: 0 auto;
  padding: 32px 36px 40px;
  background: var(--c-bg);
  color: var(--c-text);
}

.studio-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 24px;
}

.banner-copy {
  max-width: 760px;
}

.surface-kicker {
  display: inline-block;
  color: var(--c-text-tertiary);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.banner-copy h1 {
  margin: 0 0 8px;
  color: var(--c-text);
  font-family: var(--font-display);
  font-size: 30px;
  font-weight: 600;
  line-height: 1.3;
  letter-spacing: -0.6px;
}

.banner-copy p {
  margin: 0;
  color: var(--c-text-secondary);
  font-size: 14px;
  line-height: 1.55;
}

.mode-toggle {
  flex-shrink: 0;
  padding: 5px;
  border: 1px solid var(--c-border);
  border-radius: 12px;
  background: var(--c-surface);
}

.run-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 24px;
  padding: 14px 18px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-card);
  background: var(--c-surface);
}

.run-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  min-width: 176px;
}

.run-actions:has(.run-progress) {
  flex: 1;
  max-width: 380px;
}

.ghost-action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 12px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-control);
  color: var(--c-text);
  background: var(--c-surface);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  font-family: var(--font-ui);
  transition: border-color 100ms ease;
}

.ghost-action:hover {
  border-color: var(--c-accent);
  background: var(--c-bg-soft);
}

.ghost-action:disabled {
  opacity: 0.5;
  cursor: default;
}

.ghost-action:focus-visible,
.stop-action:focus-visible {
  outline: 2px solid var(--c-accent);
  outline-offset: 3px;
}

.ghost-action.accent {
  border-color: var(--c-accent);
  color: var(--c-accent);
}

.ghost-action.accent:hover {
  background: var(--c-accent-soft);
}

.ghost-action :deep(.el-icon) {
  font-size: 14px;
}

.run-progress {
  flex: 1;
  display: grid;
  gap: 6px;
  min-width: 0;
}

.progress-bar {
  height: 6px;
  border-radius: 999px;
  background: var(--c-bg-soft);
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: var(--c-accent);
  transition: width 240ms ease;
}

.progress-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--c-text-secondary);
}

.progress-state {
  font-family: var(--font-ui);
  color: var(--c-accent);
  font-weight: 600;
  letter-spacing: 0;
}

.progress-count {
  font-family: var(--font-mono);
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
}

.stop-action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 14px;
  border: 1px solid var(--c-fail);
  border-radius: var(--r-control);
  color: var(--c-fail);
  background: var(--c-fail-soft);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  font-family: var(--font-ui);
}

.stop-action :deep(.el-icon) {
  font-size: 14px;
}

.signal-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
  min-width: 0;
}

.signal-card {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.signal-card span {
  color: var(--c-text-tertiary);
  font-size: 12px;
  font-weight: 500;
}

.signal-card strong {
  color: var(--c-text);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: 0;
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
}

.studio-grid {
  display: grid;
  grid-template-columns: minmax(290px, 340px) minmax(0, 1fr);
  align-items: start;
  gap: 24px;
  margin: 0 auto;
}

.studio-rail {
  min-width: 0;
  display: grid;
  align-content: start;
  gap: 20px;
}

.studio-center {
  min-width: 0;
  display: grid;
  gap: 20px;
  align-content: start;
}


.studio-surface {
  min-width: 0;
  padding: 24px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-card);
  background: var(--c-surface);
  box-shadow: var(--shadow-panel);
}

.surface-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 20px;
}

.surface-head.compact {
  margin-bottom: 12px;
}

.surface-head h2 {
  margin: 0;
  color: var(--c-text);
  font-size: 17px;
  font-weight: 600;
  line-height: 1.5;
  letter-spacing: 0;
}

.surface-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.surface-pill {
  display: inline-flex;
  align-items: center;
  min-height: 25px;
  padding: 2px 9px;
  border: 1px solid var(--c-border-soft);
  border-radius: 999px;
  color: var(--c-text-secondary);
  background: var(--c-bg-soft);
  font-size: 12px;
  font-weight: 500;
  font-family: var(--font-ui);
  letter-spacing: 0;
  white-space: nowrap;
}

.surface-pill.success {
  color: var(--c-ok);
  border-color: var(--c-ok-soft);
  background: var(--c-ok-soft);
}

.surface-pill.running {
  color: var(--c-warn);
  border-color: var(--c-warn-soft);
  background: var(--c-warn-soft);
}

.surface-pill.failed {
  color: var(--c-fail);
  border-color: var(--c-fail-soft);
  background: var(--c-fail-soft);
}

.surface-pill.warn {
  color: var(--c-warn);
  border-color: var(--c-warn-soft);
  background: var(--c-warn-soft);
}

.surface-alert {
  margin-bottom: 14px;
}

.field-stack {
  display: grid;
  gap: 20px;
}

.field-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}

.field-block {
  display: grid;
  gap: 8px;
}

.field-block > span {
  color: var(--c-text-secondary);
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.01em;
}

.quick-prompts {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.prompt-chip {
  min-height: 26px;
  padding: 4px 10px;
  border: 1px solid var(--c-border);
  border-radius: 999px;
  color: var(--c-text-secondary);
  background: var(--c-surface);
  cursor: pointer;
  font-size: 12px;
  line-height: 1.45;
  text-align: left;
  white-space: normal;
  word-break: break-word;
  font-family: var(--font-ui);
  transition: border-color 100ms ease, color 100ms ease;
}

.prompt-chip:hover {
  border-color: var(--c-border-strong);
  color: var(--c-text);
}

.length-group,
.style-segmented {
  width: 100%;
}

.timeline-empty {
  padding: 4px 0;
  color: var(--c-text-tertiary);
  text-align: center;
  font-size: 13px;
}

.timeline-empty p {
  margin: 18px 0 0;
  line-height: 1.7;
}

.flow-preview {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.flow-preview > span {
  display: grid;
  gap: 8px;
  padding: 16px 8px;
  border: 1px solid var(--c-border-soft);
  border-radius: var(--r-control);
  color: var(--c-text-secondary);
  background: var(--c-bg-soft);
  font-size: 14px;
}

.flow-preview small {
  color: var(--c-accent);
  font-family: var(--font-mono);
  font-size: 12px;
}

.timeline {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
}

.timeline-step {
  display: grid;
  gap: 4px;
  padding: 13px 14px;
  border: 1px solid var(--c-border-soft);
  border-radius: var(--r-control);
  background: var(--c-surface);
  cursor: pointer;
  outline: none;
  transition: border-color 120ms ease, background-color 120ms ease, transform 80ms ease;
}

.timeline-step:hover {
  border-color: var(--c-border-strong, var(--c-accent));
  background: var(--c-bg-soft);
}

.timeline-step:focus-visible {
  border-color: var(--c-accent);
  box-shadow: 0 0 0 2px var(--c-accent-soft);
}

.timeline-step:active {
  transform: translateY(1px);
}

.timeline-step.running {
  border-color: var(--c-accent);
  background: var(--c-accent-soft);
}

.timeline-step.completed {
  border-color: var(--c-border);
}

.timeline-step.failed {
  border-color: var(--c-fail);
  background: var(--c-fail-soft);
}

.timeline-step.is-revised {
  border-style: dashed;
  border-color: var(--c-accent);
  background: var(--c-accent-soft);
}

.timeline-step.is-research {
  border-color: var(--c-accent);
  background: var(--c-accent-soft);
}

.timeline-step.is-research.completed {
  border-color: var(--c-accent);
}

.research-glyph {
  display: inline-grid;
  place-items: center;
  width: 17px;
  height: 17px;
  margin-right: 5px;
  border: 1px solid var(--c-accent);
  border-radius: 999px;
  color: var(--c-accent);
  font-size: 10px;
  font-family: var(--font-mono);
  font-weight: 700;
  vertical-align: 1px;
}

.research-tag {
  display: inline-flex;
  align-items: center;
  height: 16px;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--c-accent-soft);
  color: var(--c-accent);
  font-size: 9.5px;
  font-weight: 600;
  font-family: var(--font-mono);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.tool-pill {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 7px;
  border-radius: 999px;
  background: var(--c-accent-soft);
  color: var(--c-accent);
  font-family: var(--font-mono);
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0;
}

.timeline-head {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
}

.timeline-name {
  color: var(--c-text);
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.timeline-index {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  border: 1px solid var(--c-border);
  background: var(--c-bg-soft);
  color: var(--c-text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
}

.timeline-step.running .timeline-index {
  border-color: var(--c-accent);
  color: var(--c-accent);
  background: var(--c-surface);
}

.timeline-step.completed .timeline-index {
  border-color: var(--c-ok);
  color: var(--c-ok);
  background: var(--c-ok-soft);
}

.timeline-step.failed .timeline-index {
  border-color: var(--c-fail);
  color: var(--c-fail);
  background: var(--c-fail-soft);
}

.timeline-meta {
  display: flex;
  align-items: center;
  gap: 6px;
}

.timeline-meta small {
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-family: var(--font-mono);
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
}

.timeline-duration {
  min-width: 4ch;
  text-align: right;
}

.timeline-chevron {
  color: var(--c-text-tertiary);
  font-size: 16px;
  line-height: 1;
  margin-left: 2px;
  transition: transform 120ms ease, color 120ms ease;
}

.timeline-step:hover .timeline-chevron {
  color: var(--c-text);
  transform: translateX(2px);
}

.timeline-revised-badge {
  justify-self: flex-start;
  margin-top: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--c-accent-soft);
  color: var(--c-accent);
  font-size: 11px;
  font-family: var(--font-mono);
  font-weight: 600;
  letter-spacing: 0;
}

.step-surface.completed {
  border-color: var(--c-border);
}

.step-surface.running {
  border-color: var(--c-accent);
}

.step-surface.failed {
  border-color: var(--c-fail);
}

.step-surface.is-research {
  border-color: var(--c-accent);
  background: var(--c-accent-soft);
}

.step-surface.is-research.completed {
  border-color: var(--c-accent);
}

/* Dialog header that replaces the inline step card surface-head. */
.step-dialog-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.step-dialog-duration {
  margin-left: auto;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-family: var(--font-mono);
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
}

.research-surface {
  border-color: var(--c-border);
  background: var(--c-surface);
}

.research-hint {
  margin: 0 0 14px;
  color: var(--c-text-secondary);
  font-size: 12.5px;
  line-height: 1.55;
}

.research-toggles {
  display: grid;
  gap: 8px;
  margin-bottom: 14px;
}

.research-note {
  margin: -2px 0 14px;
  color: var(--c-text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.research-toggle {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-control);
  background: var(--c-surface);
  cursor: pointer;
  user-select: none;
  transition: border-color 120ms ease, background-color 120ms ease;
}

.research-toggle:hover {
  border-color: var(--c-border-strong);
}

.research-toggle:focus-visible {
  outline: 2px solid var(--c-accent);
  outline-offset: 2px;
}

.research-toggle.active {
  border-color: var(--c-border);
  background: var(--c-accent-soft);
}

.toggle-copy strong {
  display: block;
  color: var(--c-text);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0;
}

.toggle-copy span {
  display: block;
  margin-top: 2px;
  color: var(--c-text-tertiary);
  font-size: 11.5px;
}

.step-description {
  margin: 0 0 12px;
  color: var(--c-text-secondary);
  font-size: 12.5px;
  line-height: 1.55;
}

.tool-trace {
  list-style: none;
  margin: 0 0 12px;
  padding: 8px 12px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg-soft);
  display: grid;
  gap: 4px;
  font-family: var(--font-mono);
  font-size: 11.5px;
  line-height: 1.55;
}

.tool-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
  color: var(--c-text-secondary);
}

.tool-row.failed {
  color: var(--c-fail);
}

.tool-row.completed .tool-name {
  color: var(--c-text);
}

.tool-arrow {
  color: var(--c-text-tertiary);
}

.tool-name {
  color: var(--c-accent);
  font-weight: 600;
}

.tool-args {
  color: var(--c-text-tertiary);
  word-break: break-word;
}

.tool-status {
  color: var(--c-warn);
  font-style: italic;
}

.tool-preview {
  flex: 1 0 100%;
  min-width: 0;
  margin-left: 18px;
  color: var(--c-text-secondary);
  word-break: break-word;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.tool-error {
  flex: 1 0 100%;
  min-width: 0;
  margin-left: 18px;
  color: var(--c-fail);
  word-break: break-word;
  overflow-wrap: anywhere;
}

.tool-duration {
  color: var(--c-text-tertiary);
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
}

.step-output {
  margin: 0;
  padding: 14px;
  max-height: 420px;
  overflow-y: auto;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg-code);
  color: var(--c-text);
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-mono);
  font-size: 12.5px;
  line-height: 1.6;
}

.step-running {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 12px 14px;
  border: 1px solid var(--c-accent);
  border-radius: 6px;
  background: var(--c-accent-soft);
  color: var(--c-accent);
  font-size: 13px;
}

.step-pending {
  padding: 12px 14px;
  border: 1px dashed var(--c-border);
  border-radius: 6px;
  color: var(--c-text-tertiary);
  font-size: 13px;
}

.step-empty {
  padding: 12px 14px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg-soft);
  color: var(--c-text-tertiary);
  font-size: 12.5px;
  line-height: 1.55;
}

.step-empty.failed {
  border-color: var(--c-fail);
  color: var(--c-fail);
  background: var(--c-fail-soft);
}

.is-loading {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.final-surface {
  padding: 28px;
  border-color: var(--c-border);
}

.final-body {
  margin: 0;
  padding: 24px 0 0;
  max-height: 680px;
  overflow-y: auto;
  border-top: 1px solid var(--c-border-soft);
  background: var(--c-surface);
  color: var(--c-text);
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-editorial);
  font-size: 15px;
  line-height: 1.95;
}

.draft-placeholder {
  min-height: 380px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.draft-icon {
  display: grid;
  place-items: center;
  width: 56px;
  height: 64px;
  margin-bottom: 24px;
  border: 1px solid var(--c-border);
  border-radius: 12px;
  color: var(--c-accent);
  background: var(--c-bg-soft);
  font-size: 25px;
  transform: rotate(-5deg);
}

.draft-placeholder h2 {
  margin: 0;
  font-family: var(--font-editorial);
  font-size: 23px;
  font-weight: 500;
  line-height: 1.5;
}

.draft-placeholder p {
  max-width: 340px;
  margin: 12px 0 32px;
  color: var(--c-text-secondary);
  font-size: 14px;
  line-height: 1.7;
}

.draft-placeholder > span {
  color: var(--c-text-tertiary);
  font-size: 12px;
}

@media (max-width: 1100px) {
  .studio-page {
    padding: 28px 24px;
  }

  .studio-grid {
    grid-template-columns: minmax(270px, 310px) minmax(0, 1fr);
    gap: 18px;
  }

  .studio-surface {
    padding: 20px;
  }

  .run-strip {
    flex-wrap: wrap;
  }

  .run-actions {
    margin-left: auto;
  }
}

@media (max-width: 800px) {
  .studio-page {
    padding: 24px 18px;
  }

  .studio-banner {
    align-items: flex-start;
    flex-direction: column;
  }

  .studio-grid {
    grid-template-columns: 1fr;
  }

  .mode-toggle {
    max-width: 100%;
  }

  .run-strip {
    gap: 18px;
  }

  .signal-row {
    width: 100%;
    gap: 10px 18px;
  }

  .run-actions:has(.run-progress) {
    max-width: none;
  }

  .surface-head {
    flex-wrap: wrap;
  }

  .draft-placeholder {
    min-height: 320px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .progress-bar-fill,
  .timeline-step,
  .timeline-chevron {
    transition: none;
  }

  .is-loading {
    animation: none;
  }
}
</style>
