<template>
  <div class="studio-page">
    <section class="studio-banner">
      <div class="banner-copy">
        <span class="banner-kicker">{{ modeKicker }}</span>
        <h1>{{ modeTitle }}</h1>
        <p>{{ modeDescription }}</p>
      </div>
      <el-segmented v-model="mode" :options="modeOptions" :disabled="running" class="mode-toggle" />
    </section>

    <section class="run-strip">
      <template v-if="!running">
        <button class="ghost-action" type="button" :disabled="!hasOutput" @click="resetWorkspace">
          <el-icon><Refresh /></el-icon>
          <span>重置</span>
        </button>
        <el-button type="primary" size="large" :icon="VideoPlay" @click="run">运行</el-button>
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
    </section>

    <section class="signal-row">
      <article class="signal-card" v-for="card in signalCards" :key="card.label">
        <span>{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
        <small>{{ card.note }}</small>
      </article>
    </section>

    <div class="studio-grid">
      <aside class="studio-rail">
        <section class="studio-surface">
          <div class="surface-head">
            <div>
              <span class="surface-kicker">Creative Brief</span>
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
              <span class="surface-kicker">Research Sources</span>
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
                <strong>Web Search</strong>
                <span>DuckDuckGo · 时事 / 横评</span>
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
                <strong>History Search</strong>
                <span>本地内容库 · 复用沉淀</span>
              </div>
            </div>
          </div>
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
              <span class="surface-kicker">Execution</span>
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
              <span class="surface-kicker">{{ mode === 'dynamic' ? 'Plan Timeline' : 'Pipeline Stages' }}</span>
              <h2>{{ pipelineTitle }}</h2>
            </div>
            <div class="surface-actions">
              <span v-if="runId" class="surface-pill mono">{{ runId }}</span>
              <span class="surface-pill" :class="statusPillClass">{{ statusText }}</span>
            </div>
          </div>

          <el-alert v-if="errorMessage" type="error" :title="errorMessage" show-icon :closable="false" class="surface-alert" />

          <div v-if="!plan.length && !running" class="timeline-empty">
            点击"运行"开始。{{ mode === 'dynamic' ? 'Planner 会先输出 JSON 计划，每步 token 实时回流。' : '4 个固定 Agent 依次执行：策略 → 初稿 → 润色 → 审核。' }}
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
                    {{ step.agent_id === 'researcher' ? '🔍' : '🛡' }}
                  </span>
                  {{ agentLabel(step.agent_id) }}
                </strong>
                <div class="timeline-meta">
                  <small v-if="toolEventsFor(step.index).length" class="tool-pill" :title="`${toolEventsFor(step.index).length} 个工具调用`">
                    🛠 {{ toolEventsFor(step.index).length }}
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
                  <span v-else class="tool-preview">{{ event.preview || '完成' }}</span>
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
              <span class="surface-kicker">Final Content</span>
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
      </main>
    </div>
  </div>
</template>

<!-- SCRIPT_PLACEHOLDER -->

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus/es/components/message/index'
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
  pipelineStreamUrl,
  type PipelinePlanStep,
  type PipelineRunPayload,
  type SubAgentId,
  type SubAgentToolEvent
} from '../api/agent'
import {
  createAgentRunJob,
  extractAgentRun,
  getJob,
  type JobResponse
} from '../api/jobs'
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
  { label: '内容生产线 · Workflow', value: 'workflow' },
  { label: '研究型 Pipeline · Dynamic', value: 'dynamic' }
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

let eventSource: EventSource | null = null
let workflowJobId: string | null = null
let workflowAbort = false

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

const modeKicker = computed(() =>
  mode.value === 'dynamic' ? '研究型 Pipeline · 边查边写' : '内容生产线 · 标准 4 步'
)

const modeTitle = computed(() =>
  mode.value === 'dynamic'
    ? '多步骤研究型内容生产线'
    : '主题清晰、不需要外部资料时走这条线'
)

const modeDescription = computed(() =>
  mode.value === 'dynamic'
    ? 'Planner 自动规划步骤，researcher / fact_checker 按需介入。适合横评、对比、盘点类内容。'
    : '4 步固定流程依次执行：策略 → 写作 → 润色 → 评分。节奏可预期、产出稳定，适合标准化批量产出。生成保存后，可一键跳到 Chat Agent 继续优化和安排发布日历。'
)

const activeSourceCount = computed(() =>
  Number(research.use_web_search) + Number(research.use_history_search)
)

const RESEARCH_AGENTS = new Set(['researcher', 'fact_checker'])

function isResearchStep(agentId: string): boolean {
  return RESEARCH_AGENTS.has(agentId)
}

const pipelineTitle = computed(() => {
  if (status.value === 'planning') return '生成 Plan 中…'
  if (status.value === 'running') return '执行中…'
  if (status.value === 'completed') return '执行完成'
  if (status.value === 'failed') return '执行失败'
  if (status.value === 'cancelled') return '已停止'
  return mode.value === 'dynamic' ? '动态 Pipeline' : '4 阶段 Workflow'
})

const statusText = computed(() => {
  switch (status.value) {
    case 'planning':
      return 'planning'
    case 'running':
      return 'running'
    case 'completed':
      return 'done'
    case 'failed':
      return 'failed'
    case 'cancelled':
      return 'stopped'
    default:
      return 'idle'
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
      { label: 'Mode', value: 'Research', note: 'Plan-then-Execute · 工具就位' },
      { label: 'Plan', value: totalPlanSteps.value || '--', note: totalPlanSteps.value ? `${completedSteps.value} 已完成` : '等待计划' },
      { label: 'Tool calls', value: totalToolCalls.value, note: totalToolCalls.value ? '研究 / 校验 工具已被调用' : '尚未调用工具' },
      { label: 'Revisions', value: revisionCount.value, note: revisionCount.value ? 'Planner 已介入修改' : '初始 plan 直跑' }
    ]
  }
  return [
    { label: 'Mode', value: 'Workflow', note: 'Fixed 4-stage' },
    { label: 'Plan', value: totalPlanSteps.value || '--', note: totalPlanSteps.value ? `${completedSteps.value} 已完成` : '等待计划' },
    { label: 'Status', value: statusText.value, note: progressLabel.value },
    { label: 'Saved', value: savedContentId.value ? `#${savedContentId.value}` : '--', note: savedContentId.value ? '可在 Chat 中优化' : '尚未保存' }
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

function resetWorkspace() {
  if (running.value) return
  closeStream()
  workflowJobId = null
  workflowAbort = false
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
}

function closeStream() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
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
    workflowAbort = true
  }
  running.value = false
  status.value = 'cancelled'
  errorMessage.value = '已停止运行'
}

async function run() {
  if (!form.topic.trim()) {
    ElMessage.warning('请输入内容主题')
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
    subscribe(handle.run_id)
  } catch (error) {
    running.value = false
    status.value = 'failed'
    errorMessage.value = (error as Error).message
    ElMessage.error(errorMessage.value)
  }
}

function subscribe(id: string) {
  closeStream()
  const evt = new EventSource(pipelineStreamUrl(id))
  eventSource = evt

  evt.addEventListener('plan_ready', e => {
    const data = JSON.parse((e as MessageEvent).data) as { plan: PipelinePlanStep[] }
    plan.value = data.plan.map(step => ({ ...step }))
    status.value = 'running'
  })

  evt.addEventListener('step_start', e => {
    const data = JSON.parse((e as MessageEvent).data) as { index: number }
    streamingOutputs[data.index] = ''
    stepToolEvents[data.index] = []
    const step = plan.value.find(s => s.index === data.index)
    if (step) step.status = 'running'
  })

  evt.addEventListener('step_token', e => {
    const data = JSON.parse((e as MessageEvent).data) as { index: number; delta: string }
    streamingOutputs[data.index] = (streamingOutputs[data.index] || '') + data.delta
  })

  evt.addEventListener('tool_call_start', e => {
    const data = JSON.parse((e as MessageEvent).data) as {
      index: number
      name: string
      args: Record<string, unknown>
    }
    if (!stepToolEvents[data.index]) stepToolEvents[data.index] = []
    stepToolEvents[data.index].push({
      name: data.name,
      args: data.args || {},
      status: 'started',
      preview: '',
      duration_ms: 0
    })
  })

  evt.addEventListener('tool_call_result', e => {
    const data = JSON.parse((e as MessageEvent).data) as {
      index: number
      name: string
      args: Record<string, unknown>
      status: 'completed' | 'failed'
      preview?: string
      error?: string | null
      duration_ms?: number
    }
    const list = stepToolEvents[data.index] || (stepToolEvents[data.index] = [])
    const pending = [...list].reverse().find(t => t.name === data.name && t.status === 'started')
    const event: SubAgentToolEvent = {
      name: data.name,
      args: data.args || {},
      status: data.status,
      preview: data.preview || '',
      error: data.error || null,
      duration_ms: data.duration_ms || 0
    }
    if (pending) Object.assign(pending, event)
    else list.push(event)
  })

  evt.addEventListener('step_complete', e => {
    const data = JSON.parse((e as MessageEvent).data) as {
      index: number
      output: string
      duration_ms: number
      prompt_tokens: number
      completion_tokens: number
      cost_estimate: number
      tool_events?: SubAgentToolEvent[]
    }
    const step = plan.value.find(s => s.index === data.index)
    if (step) {
      step.status = 'completed'
      step.output = data.output
      step.duration_ms = data.duration_ms
      step.prompt_tokens = data.prompt_tokens
      step.completion_tokens = data.completion_tokens
      step.cost_estimate = data.cost_estimate
      step.tool_events = data.tool_events || []
    }
    streamingOutputs[data.index] = data.output
    if (data.tool_events) stepToolEvents[data.index] = data.tool_events
    totalPromptTokens.value += data.prompt_tokens
    totalCompletionTokens.value += data.completion_tokens
    totalCost.value += data.cost_estimate
  })

  evt.addEventListener('step_failed', e => {
    const data = JSON.parse((e as MessageEvent).data) as { index: number; error: string }
    const step = plan.value.find(s => s.index === data.index)
    if (step) step.status = 'failed'
    errorMessage.value = `Step ${data.index} 失败：${data.error}`
  })

  evt.addEventListener('plan_revised', e => {
    const data = JSON.parse((e as MessageEvent).data) as { plan: PipelinePlanStep[]; revision: number }
    const knownIndices = new Set(plan.value.map(s => s.index))
    plan.value = data.plan.map(step => {
      const isNew = !knownIndices.has(step.index)
      return { ...step, revised_at: isNew ? data.revision : step.revised_at }
    })
    revisionCount.value = data.revision
  })

  evt.addEventListener('run_complete', e => {
    const data = JSON.parse((e as MessageEvent).data) as {
      final_content: FinalContent
      saved_content_id?: number | null
      total_prompt_tokens: number
      total_completion_tokens: number
      total_cost: number
      revision_count: number
    }
    finalContent.value = data.final_content
    savedContentId.value = data.saved_content_id ?? null
    totalPromptTokens.value = data.total_prompt_tokens
    totalCompletionTokens.value = data.total_completion_tokens
    totalCost.value = data.total_cost
    revisionCount.value = data.revision_count
    status.value = 'completed'
    running.value = false
    closeStream()
    ElMessage.success(savedContentId.value ? `已完成，已保存 #${savedContentId.value}` : '已完成')
  })

  evt.addEventListener('run_failed', e => {
    const data = JSON.parse((e as MessageEvent).data) as { error?: string }
    status.value = 'failed'
    running.value = false
    errorMessage.value = data.error || '运行失败'
    closeStream()
  })

  evt.onerror = () => {
    if (status.value !== 'completed' && status.value !== 'failed' && status.value !== 'cancelled') {
      status.value = 'failed'
      running.value = false
      errorMessage.value = errorMessage.value || 'SSE 连接中断'
      closeStream()
    }
  }
}

async function runWorkflow() {
  workflowAbort = false
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
    if (workflowAbort) return
    applyWorkflowResult(result)
  } catch (error) {
    if (workflowAbort) return
    running.value = false
    status.value = 'failed'
    errorMessage.value = (error as Error).message
    ElMessage.error(errorMessage.value)
  }
}

async function pollWorkflowJob(jobId: string): Promise<AgentRunResponse> {
  const started = Date.now()
  const timeoutMs = 360000
  while (Date.now() - started < timeoutMs) {
    if (workflowAbort) throw new Error('已停止')
    const job: JobResponse = await getJob(jobId)
    advanceWorkflowSteps(job)
    if (job.status === 'completed') {
      const result = extractAgentRun(job)
      if (!result) throw new Error('任务已完成，但结果为空')
      return result
    }
    if (job.status === 'failed') throw new Error(job.error || '任务执行失败')
    await new Promise(resolve => window.setTimeout(resolve, 1500))
  }
  throw new Error('任务等待超时')
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

onBeforeUnmount(() => {
  closeStream()
})
</script>

<!-- STYLE_PLACEHOLDER -->

<style scoped>
.studio-page {
  padding: 24px 32px 32px;
  background: var(--c-bg);
  color: var(--c-text);
}

.studio-banner {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin: 0 auto 16px;
  max-width: 1520px;
}

.banner-copy {
  max-width: 760px;
}

.banner-kicker,
.surface-kicker {
  display: inline-block;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.banner-copy h1 {
  margin: 8px 0 6px;
  color: var(--c-text);
  font-size: 30px;
  font-weight: 600;
  line-height: 1.18;
  letter-spacing: -0.025em;
}

.banner-copy p {
  margin: 0;
  color: var(--c-text-secondary);
  font-size: 14px;
  line-height: 1.55;
}

.mode-toggle {
  flex-shrink: 0;
}

.run-strip {
  display: flex;
  align-items: center;
  gap: 12px;
  max-width: 1520px;
  margin: 0 auto 16px;
  padding: 12px 16px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg);
}

.ghost-action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  color: var(--c-text);
  background: var(--c-bg);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  font-family: var(--font-ui);
  transition: border-color 100ms ease;
}

.ghost-action:hover {
  border-color: var(--c-border-strong);
}

.ghost-action:disabled {
  opacity: 0.5;
  cursor: default;
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
  font-family: var(--font-mono);
  color: var(--c-accent);
  font-weight: 600;
  letter-spacing: -0.01em;
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
  height: 32px;
  padding: 0 14px;
  border: 1px solid var(--c-fail);
  border-radius: 4px;
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
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  max-width: 1520px;
  margin: 0 auto 16px;
}

.signal-card {
  padding: 14px 16px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg);
}

.signal-card span {
  display: block;
  color: var(--c-text-tertiary);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.signal-card strong {
  display: block;
  margin: 6px 0 4px;
  color: var(--c-text);
  font-size: 22px;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -0.015em;
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
}

.signal-card small {
  color: var(--c-text-tertiary);
  font-size: 12px;
  line-height: 1.45;
}

.studio-grid {
  display: grid;
  grid-template-columns: minmax(290px, 360px) minmax(0, 1fr);
  grid-template-rows: 1fr;
  gap: 16px;
  max-width: 1520px;
  margin: 0 auto;
}

.studio-rail {
  min-width: 0;
  display: grid;
  align-content: start;
  gap: 16px;
}

.studio-center {
  min-width: 0;
  display: grid;
  grid-template-rows: 1fr auto;
  gap: 16px;
  align-content: start;
}


.studio-surface {
  min-width: 0;
  padding: 20px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg);
}

.surface-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.surface-head.compact {
  margin-bottom: 12px;
}

.surface-head h2 {
  margin: 4px 0 0;
  color: var(--c-text);
  font-size: 18px;
  font-weight: 600;
  line-height: 1.25;
  letter-spacing: -0.015em;
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
  height: 22px;
  padding: 0 8px;
  border: 1px solid var(--c-border);
  border-radius: 999px;
  color: var(--c-text-secondary);
  background: var(--c-bg);
  font-size: 11px;
  font-weight: 500;
  font-family: var(--font-mono);
  letter-spacing: -0.01em;
  white-space: nowrap;
}

.surface-pill.success {
  color: var(--c-ok);
  border-color: var(--c-ok);
  background: var(--c-ok-soft);
}

.surface-pill.running {
  color: var(--c-warn);
  border-color: var(--c-warn);
  background: var(--c-warn-soft);
}

.surface-pill.failed {
  color: var(--c-fail);
  border-color: var(--c-fail);
  background: var(--c-fail-soft);
}

.surface-pill.warn {
  color: var(--c-warn);
  border-color: var(--c-warn);
  background: var(--c-warn-soft);
}

.surface-alert {
  margin-bottom: 14px;
}

.field-stack {
  display: grid;
  gap: 16px;
}

.field-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}

.field-block {
  display: grid;
  gap: 6px;
}

.field-block > span {
  color: var(--c-text-secondary);
  font-size: 12px;
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
  background: var(--c-bg);
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
  padding: 28px 16px;
  border: 1px dashed var(--c-border);
  border-radius: 6px;
  color: var(--c-text-tertiary);
  text-align: center;
  font-size: 13px;
}

.timeline {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}

.timeline-step {
  display: grid;
  gap: 4px;
  padding: 8px 12px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg);
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
  border-color: var(--c-ok);
}

.timeline-step.failed {
  border-color: var(--c-fail);
  background: var(--c-fail-soft);
}

.timeline-step.is-revised {
  border-style: dashed;
  border-color: #6e56cf;
  background: rgba(110, 86, 207, 0.06);
}

.timeline-step.is-research {
  border-color: rgba(110, 86, 207, 0.45);
  background: linear-gradient(180deg, rgba(110, 86, 207, 0.08), rgba(110, 86, 207, 0.02));
}

.timeline-step.is-research.completed {
  border-color: #6e56cf;
}

.research-glyph {
  display: inline-block;
  margin-right: 4px;
  font-size: 13px;
  vertical-align: -1px;
}

.research-tag {
  display: inline-flex;
  align-items: center;
  height: 16px;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(110, 86, 207, 0.16);
  color: #6e56cf;
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
  letter-spacing: -0.01em;
}

.timeline-head {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
}

.timeline-name {
  color: var(--c-text);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: -0.01em;
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
  background: #ffffff;
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
  background: rgba(110, 86, 207, 0.16);
  color: #6e56cf;
  font-size: 11px;
  font-family: var(--font-mono);
  font-weight: 600;
  letter-spacing: -0.01em;
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
  border-color: rgba(110, 86, 207, 0.4);
  background: linear-gradient(180deg, rgba(110, 86, 207, 0.05), transparent 36%);
}

.step-surface.is-research.completed {
  border-color: #6e56cf;
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
  border-color: rgba(110, 86, 207, 0.5);
  background: linear-gradient(180deg, rgba(110, 86, 207, 0.07), transparent 60%);
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

.research-toggle {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg);
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
  border-color: rgba(110, 86, 207, 0.55);
  background: rgba(110, 86, 207, 0.06);
}

.toggle-copy strong {
  display: block;
  color: var(--c-text);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: -0.01em;
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
  flex: 1;
  min-width: 0;
  color: var(--c-text-secondary);
  word-break: break-word;
  white-space: pre-wrap;
}

.tool-error {
  flex: 1;
  min-width: 0;
  color: var(--c-fail);
  word-break: break-word;
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
  border-color: var(--c-ok);
}

.final-body {
  margin: 0;
  padding: 16px;
  max-height: 540px;
  overflow-y: auto;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg-soft);
  color: var(--c-text);
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-ui);
  font-size: 14px;
  line-height: 1.7;
}

@media (max-width: 1180px) {
  .signal-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .studio-grid {
    grid-template-columns: 1fr;
  }


}

@media (max-width: 980px) {
  .studio-page {
    padding: 16px;
  }

  .studio-banner {
    align-items: flex-start;
    flex-direction: column;
  }

  .signal-row {
    grid-template-columns: 1fr;
  }
}
</style>
