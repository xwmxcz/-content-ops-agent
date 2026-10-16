<template>
  <div class="studio-page">
    <section class="studio-banner">
      <div class="banner-copy">
        <span class="surface-kicker">CONTENT STUDIO · 多智能体协同创作</span>
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
              <el-input v-model="form.topic" type="textarea" :rows="4" placeholder="例如：周末徒步路线推荐，附新手装备清单与避坑建议" />
              <div class="quick-prompts">
                <button
                  v-for="prompt in quickPrompts"
                  :key="prompt"
                  type="button"
                  class="prompt-chip"
                  :disabled="running"
                  @click="form.topic = prompt"
                >
                  {{ prompt }}
                </button>
              </div>
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
              <el-input v-model="keywordsText" placeholder="徒步, 周末, 避坑（多个词用逗号分隔）" />
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

          <el-alert v-if="errorMessage" type="error" :title="errorMessage" show-icon :closable="false" class="surface-alert">
            <div v-if="canResume" class="resume-row">
              <el-button size="small" type="primary" :loading="resuming" @click="resumeRun">从断点继续</el-button>
              <span class="resume-hint">{{ resumeHint }}</span>
            </div>
          </el-alert>

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
              <span><small>STEP 01</small><strong>内容策略</strong><em>受众定位与切入角度</em></span>
              <span><small>STEP 02</small><strong>结构初稿</strong><em>展开论点与核心正文</em></span>
              <span><small>STEP 03</small><strong>编辑润色</strong><em>优化节奏与平台语感</em></span>
              <span><small>STEP 04</small><strong>质量审核</strong><em>事实把关与发布建议</em></span>
            </div>
            <div v-else class="flow-preview" aria-label="研究流程：规划、检索、撰稿、核验">
              <span><small>STEP 01</small><strong>动态规划</strong><em>拆解调研问题与路径</em></span>
              <span><small>STEP 02</small><strong>多源检索</strong><em>查证网页与历史内容库</em></span>
              <span><small>STEP 03</small><strong>深度撰稿</strong><em>融合一手依据生成初稿</em></span>
              <span><small>STEP 04</small><strong>事实核验</strong><em>交叉比对与润色定稿</em></span>
            </div>
            <p>{{ mode === 'dynamic' ? '填写主题并点击右上角“运行”，Agent 将自动规划研究步骤，边查证边创作。' : '在左侧填写主题或点击灵感示例，再点击“运行”开始。你可以随时点开每一步查看详情。' }}</p>
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

        <StudioStepDialog
          v-model:open="stepDialogOpen"
          :step="stepDialogStep"
          :tool-events="stepDialogStep ? toolEventsFor(stepDialogStep.index) : []"
          :streaming-output="stepDialogStep ? (streamingOutputs[stepDialogStep.index] || '') : ''"
        />

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
          <p>{{ running ? '创作完成后，最终稿件会实时呈现在这里。' : '在左侧输入选题或点击快捷灵感，剩下的交给多智能体创作工作流。' }}</p>
          <span>多步协同 · 自动入库 · 支持在 Chat 与打磨页二次精修</span>
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
import StudioStepDialog from '../components/StudioStepDialog.vue'
import {
  cancelPipelineRun,
  createPipelineRun,
  getPipelineRun,
  listPipelineRuns,
  resumePipelineRun,
  type PipelinePlanStep,
  type PipelineRunPayload,
  type PipelineRunSnapshot,
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
import { ACTIVE_STUDIO_SESSION_KEY } from '../workspaceSession'
import {
  agentLabel,
  contentTypeOptions,
  formatToolArgs,
  formatToolPreview,
  isResearchStep,
  modeOptions,
  statusLabel,
  statusToPill,
  styleOptions,
  toolEventsFor as resolveToolEvents,
  workflowDescription,
  type StudioMode
} from '../composables/useStudioPresentation'
import type { AgentRunPayload, AgentRunResponse, AgentStep } from '../api/agent'

interface FinalContent {
  title?: string
  content: string
  content_type: string
  style: string
  tags: string[]
}

type RunStatus = 'idle' | 'planning' | 'running' | 'completed' | 'failed' | 'cancelled'

const route = useRoute()
const router = useRouter()

const initialMode: StudioMode = route.query.mode === 'dynamic' ? 'dynamic' : 'workflow'
const mode = ref<StudioMode>(initialMode)

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
    clearActiveSession()
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
  onRunFailed(error, code) {
    status.value = 'failed'
    running.value = false
    errorMessage.value =
      code === 'no_content'
        ? '写作步骤全部失败，没有生成内容。通常是模型服务暂时不可用，可稍后从断点继续。'
        : code === 'worker_lost'
          ? '执行进程已中断或排队超时，已完成的步骤已保留。可点击“从断点继续”恢复运行。'
        : error || '运行失败'
    closeStream()
  },
  onRunCancelled() {
    clearActiveSession()
    status.value = 'cancelled'
    running.value = false
    errorMessage.value = '已停止运行'
    closeStream()
  },
  onRunResumed() {
    // The restored plan follows in plan_ready; this only lifts the failed state.
    status.value = 'running'
    running.value = true
    errorMessage.value = ''
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
      clearActiveSession()
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
      clearActiveSession()
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

// Only a run the server recorded as failed can be resumed: a request that never
// produced a run id has nothing to resume, and a cancelled run is final.
const resuming = ref(false)
const canResume = computed(
  () => mode.value === 'dynamic' && status.value === 'failed' && !!runId.value && !running.value
)
const resumeHint = computed(() =>
  completedSteps.value > 0
    ? `已完成的 ${completedSteps.value} 步不会重跑，也不会再次计费`
    : '将沿用原来的请求重新执行'
)

async function resumeRun() {
  const id = runId.value
  if (!id || resuming.value) return
  resuming.value = true
  try {
    await resumePipelineRun(id)
    errorMessage.value = ''
    status.value = 'running'
    running.value = true
    streamExhausted.value = false
    // Same run, same log: reopen at the cursor instead of replaying from zero.
    pipelineStream.resume()
  } catch (error) {
    ElMessage.error((error as Error).message || '无法继续运行')
  } finally {
    resuming.value = false
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

const quickPrompts = computed(() =>
  mode.value === 'dynamic'
    ? ['2026 主流降噪耳机横评与选购建议', 'AI 编程工具对比与团队落地实践', '近期高互动小红书图文结构拆解']
    : ['周末徒步路线与新手装备避坑指南', '远程办公效率翻倍的 5 个工作流习惯', '新消费品牌如何写好第一篇种草笔记']
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

function toolEventsFor(stepIndex: number) {
  return resolveToolEvents(stepIndex, stepToolEvents, plan.value)
}

function scrollToStep(index: number): void {
  stepDialogIndex.value = index
  stepDialogOpen.value = true
}

function activeSessionKey() {
  return ACTIVE_STUDIO_SESSION_KEY
}

function saveActiveSession(activeMode: StudioMode, id: string) {
  try {
    window.sessionStorage?.setItem(activeSessionKey(), JSON.stringify({ mode: activeMode, id }))
  } catch {
    /* ignore storage quota or privacy-mode errors */
  }
}

function clearActiveSession() {
  try {
    window.sessionStorage?.removeItem(activeSessionKey())
  } catch {
    /* ignore storage errors */
  }
}

function readActiveSession(): { mode: StudioMode; id: string } | null {
  try {
    const raw = window.sessionStorage?.getItem(activeSessionKey())
    if (!raw) return null
    const parsed = JSON.parse(raw) as { mode?: string; id?: string }
    if ((parsed.mode === 'dynamic' || parsed.mode === 'workflow') && typeof parsed.id === 'string' && parsed.id) {
      return { mode: parsed.mode, id: parsed.id }
    }
  } catch {
    /* ignore malformed storage */
  }
  return null
}

function resetWorkspace() {
  if (running.value) return
  clearActiveSession()
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
  clearActiveSession()
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
    saveActiveSession('dynamic', handle.run_id)
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

function initWorkflowPlan() {
  plan.value = ['strategy', 'writer', 'editor', 'review'].map((id, idx) => ({
    index: idx + 1,
    agent_id: id as SubAgentId,
    description: workflowDescription(id),
    instruction: '',
    inputs_from: [],
    status: idx === 0 ? 'running' : 'pending',
    output: '',
    duration_ms: 0,
    prompt_tokens: 0,
    completion_tokens: 0,
    cost_estimate: 0
  }))
}

async function runWorkflow() {
  const attempt = workflowPolling.reset()
  initWorkflowPlan()
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
    if (workflowPolling.isAborted(attempt)) return
    workflowJobId = job.id
    runId.value = job.id
    saveActiveSession('workflow', job.id)
    const result = await pollWorkflowJob(job.id)
    if (workflowPolling.isAborted(attempt)) return
    applyWorkflowResult(result)
  } catch (error) {
    if (workflowPolling.isAborted(attempt)) return
    clearActiveSession()
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
  if (!form.topic && job.payload && typeof job.payload.topic === 'string') {
    form.topic = job.payload.topic
  }
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
  clearActiveSession()
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

async function applyPipelineSnapshot(snapshot: PipelineRunSnapshot) {
  mode.value = 'dynamic'
  runId.value = snapshot.id
  const req = (snapshot.request || {}) as Record<string, unknown>
  if (!form.topic) {
    const restoredTopic = (typeof req.topic === 'string' && req.topic) || snapshot.topic || ''
    if (restoredTopic) form.topic = restoredTopic
  }
  if (typeof req.content_type === 'string' && req.content_type) form.content_type = req.content_type
  else if (snapshot.content_type) form.content_type = snapshot.content_type
  if (typeof req.style === 'string' && req.style) form.style = req.style
  else if (snapshot.style) form.style = snapshot.style
  if (typeof req.length === 'string' && req.length) form.length = req.length
  if (Array.isArray(req.keywords) && !keywordsText.value) {
    keywordsText.value = req.keywords.filter((k): k is string => typeof k === 'string').join(', ')
  }
  if (typeof req.use_web_search === 'boolean') research.use_web_search = req.use_web_search
  if (typeof req.use_history_search === 'boolean') research.use_history_search = req.use_history_search
  if (typeof req.research_focus === 'string' && !research.research_focus) research.research_focus = req.research_focus

  if (snapshot.plan?.length) {
    plan.value = snapshot.plan.map(step => ({ ...step }))
    snapshot.plan.forEach(step => {
      if (step.output) streamingOutputs[step.index] = step.output
      if (step.tool_events?.length) stepToolEvents[step.index] = step.tool_events
    })
  }
  totalPromptTokens.value = snapshot.total_prompt_tokens ?? 0
  totalCompletionTokens.value = snapshot.total_completion_tokens ?? 0
  totalCost.value = snapshot.total_cost ?? 0
  revisionCount.value = snapshot.revision_count ?? 0
  savedContentId.value = snapshot.saved_content_id ?? null

  if (snapshot.status === 'running') {
    saveActiveSession('dynamic', snapshot.id)
    running.value = true
    status.value = snapshot.plan?.length ? 'running' : 'planning'
    // The snapshot already contains every event through next_event_seq - 1.
    // Replaying from zero would double-count totals while restoring a page.
    pipelineStream.prepare(snapshot.id, Math.max(0, (snapshot.next_event_seq ?? 1) - 1))
    pipelineStream.resume()
  } else if (snapshot.status === 'failed') {
    saveActiveSession('dynamic', snapshot.id)
    running.value = false
    status.value = 'failed'
    errorMessage.value = snapshot.error || '运行失败'
    // Keep the run identity and cursor so a resume after a page refresh opens
    // the stream after the historical failure event.
    pipelineStream.prepare(snapshot.id, Math.max(0, (snapshot.next_event_seq ?? 1) - 1))
  } else {
    clearActiveSession()
    running.value = false
    status.value = snapshot.status === 'completed' ? 'completed' : 'cancelled'
  }
}

async function restorePipelineRun(id: string) {
  try {
    const snapshot = await getPipelineRun(id)
    await applyPipelineSnapshot(snapshot)
  } catch {
    clearActiveSession()
  }
}

async function restoreWorkflowJob(id: string) {
  const attempt = workflowPolling.reset()
  mode.value = 'workflow'
  workflowJobId = id
  runId.value = id
  running.value = true
  status.value = 'running'
  initWorkflowPlan()
  try {
    const result = await pollWorkflowJob(id)
    if (workflowPolling.isAborted(attempt)) return
    applyWorkflowResult(result)
  } catch (error) {
    if (workflowPolling.isAborted(attempt)) return
    clearActiveSession()
    running.value = false
    status.value = 'failed'
    errorMessage.value = (error as Error).message
  }
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

onMounted(async () => {
  const topic = typeof route.query.topic === 'string' ? route.query.topic.trim() : ''
  const researchFocus = typeof route.query.research_focus === 'string' ? route.query.research_focus.trim() : ''
  const queryRunId = typeof route.query.run_id === 'string' ? route.query.run_id.trim() : ''
  if (topic) form.topic = topic
  if (researchFocus) research.research_focus = researchFocus
  if (topic || researchFocus || queryRunId) {
    const nextQuery: Record<string, string> = {}
    if (typeof route.query.mode === 'string' && route.query.mode) nextQuery.mode = route.query.mode
    void router.replace({ query: nextQuery })
  }
  if (queryRunId) {
    await restorePipelineRun(queryRunId)
    return
  }
  if (topic || researchFocus) return

  const saved = readActiveSession()
  if (saved) {
    if (saved.mode === 'dynamic') await restorePipelineRun(saved.id)
    else await restoreWorkflowJob(saved.id)
    return
  }
  if (mode.value === 'dynamic' && typeof listPipelineRuns === 'function') {
    try {
      const recent = await listPipelineRuns({ limit: 5 })
      const recoverable = recent?.find(item => item.status === 'running' || item.status === 'failed')
      if (recoverable && !running.value && !runId.value) {
        await applyPipelineSnapshot(recoverable)
      }
    } catch {
      /* recovery discovery is best-effort */
    }
  }
})

onBeforeUnmount(() => {
  workflowPolling.abort()
  closeStream()
})
</script>

<!-- STYLE_PLACEHOLDER -->

<style scoped>
.studio-page {
  width: 100%;
  max-width: 1680px;
  margin: 0 auto;
  padding: 28px 40px 48px;
  background: transparent;
  color: var(--c-text);
}

.studio-banner {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 20px;
  padding: 4px 0 22px;
  border-bottom: 1px solid var(--c-border);
}

.banner-copy {
  max-width: 740px;
}

.surface-kicker {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  color: var(--c-text-tertiary);
  font-size: 12px;
  font-weight: 500;
}

.banner-copy h1 {
  margin: 0 0 6px;
  color: var(--c-text);
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: -0.025em;
}

.banner-copy p {
  margin: 0;
  color: var(--c-text-secondary);
  font-size: 14px;
  line-height: 1.65;
}

.mode-toggle {
  flex-shrink: 0;
}

.run-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 24px;
  padding: 14px 20px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-card);
  background: #ffffff;
  box-shadow: var(--shadow-panel);
}

.run-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  min-width: 196px;
}

.run-actions:has(.run-progress) {
  flex: 1;
  max-width: 400px;
}

.ghost-action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 14px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-control);
  color: var(--c-text-secondary);
  background: #ffffff;
  cursor: pointer;
  font-size: 13px;
  font-weight: 550;
  font-family: var(--font-ui);
  transition: border-color 140ms ease, background-color 140ms ease, color 140ms ease;
}

.ghost-action:hover:not(:disabled) {
  border-color: var(--c-border-strong);
  color: var(--c-text);
  background: #faf9f6;
}

.ghost-action:disabled {
  opacity: 0.45;
  cursor: default;
}

.ghost-action:focus-visible,
.stop-action:focus-visible {
  outline: 2px solid var(--c-border-focus);
  outline-offset: 2px;
}

.ghost-action.accent {
  border-color: var(--c-text);
  color: var(--c-text);
}

.ghost-action.accent:hover {
  background: var(--c-bg-soft);
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
  background: var(--c-text);
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
  color: var(--c-text);
  font-weight: 600;
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
  border: 1px solid rgba(185, 28, 28, 0.25);
  border-radius: var(--r-control);
  color: var(--c-fail);
  background: var(--c-fail-soft);
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  font-family: var(--font-ui);
}

.stop-action :deep(.el-icon) {
  font-size: 14px;
}

.signal-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.signal-card {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border: 1px solid var(--c-border-soft);
  border-radius: 9px;
  background: #faf9f6;
}

.signal-card span {
  color: var(--c-text-tertiary);
  font-size: 12px;
  font-weight: 500;
}

.signal-card strong {
  color: var(--c-text);
  font-size: 13px;
  font-weight: 650;
  line-height: 1.2;
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
}

.studio-grid {
  display: grid;
  grid-template-columns: minmax(350px, 410px) minmax(0, 1fr);
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
  background: #ffffff;
  box-shadow: var(--shadow-panel);
}

.surface-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 18px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--c-border-soft);
}

.surface-head.compact {
  margin-bottom: 14px;
  padding-bottom: 12px;
}

.surface-head h2 {
  margin: 0;
  color: var(--c-text);
  font-size: 16px;
  font-weight: 650;
  line-height: 1.4;
  letter-spacing: -0.01em;
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
  min-height: 24px;
  padding: 2px 10px;
  border: 1px solid var(--c-border);
  border-radius: 999px;
  color: var(--c-text-secondary);
  background: #faf9f6;
  font-size: 12px;
  font-weight: 500;
  font-family: var(--font-ui);
  white-space: nowrap;
}

.surface-pill.success {
  color: var(--c-ok);
  border-color: rgba(21, 128, 61, 0.2);
  background: var(--c-ok-soft);
}

.surface-pill.running {
  color: var(--c-warn);
  border-color: rgba(180, 83, 9, 0.2);
  background: var(--c-warn-soft);
}

.surface-pill.failed {
  color: var(--c-fail);
  border-color: rgba(185, 28, 28, 0.2);
  background: var(--c-fail-soft);
}

.surface-pill.warn {
  color: var(--c-warn);
  border-color: rgba(180, 83, 9, 0.2);
  background: var(--c-warn-soft);
}

.surface-alert {
  margin-bottom: 14px;
}

.resume-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 6px;
}

.resume-hint {
  font-size: 12px;
  color: var(--c-text-secondary);
}

.field-stack {
  display: grid;
  gap: 18px;
}

.field-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  gap: 12px;
}

.field-block {
  display: grid;
  gap: 8px;
}

.field-block > span {
  color: var(--c-text-secondary);
  font-size: 12.5px;
  font-weight: 600;
}

.quick-prompts {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 2px;
}

.prompt-chip {
  min-height: 26px;
  padding: 4px 11px;
  border: 1px solid var(--c-border);
  border-radius: 999px;
  color: var(--c-text-secondary);
  background: #faf9f6;
  cursor: pointer;
  font-size: 11.5px;
  font-weight: 500;
  line-height: 1.4;
  text-align: left;
  white-space: normal;
  word-break: break-word;
  font-family: var(--font-ui);
  transition: border-color 140ms ease, color 140ms ease, background-color 140ms ease;
}

.prompt-chip:hover:not(:disabled) {
  border-color: var(--c-border-strong);
  color: var(--c-text);
  background: var(--c-bg-soft);
}

.prompt-chip:disabled {
  opacity: 0.5;
  cursor: default;
}

.length-group,
.style-segmented {
  width: 100%;
}

.length-group :deep(.el-radio-button) {
  flex: 1;
}

.length-group :deep(.el-radio-button__inner) {
  width: 100%;
  padding-left: 0;
  padding-right: 0;
}

.timeline-empty {
  padding: 4px 0;
  color: var(--c-text-tertiary);
  text-align: center;
  font-size: 13px;
}

.timeline-empty p {
  margin: 16px 0 0;
  color: var(--c-text-secondary);
  line-height: 1.7;
}

.flow-preview {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.flow-preview > span {
  display: grid;
  gap: 6px;
  padding: 18px 16px;
  border: 1px solid var(--c-border-soft);
  border-radius: 11px;
  color: var(--c-text);
  background: #faf9f6;
  text-align: left;
  font-size: 14px;
}

.flow-preview small {
  display: inline-flex;
  justify-self: start;
  color: var(--c-text-tertiary);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
}

.flow-preview strong {
  color: var(--c-text);
  font-size: 14.5px;
  font-weight: 650;
}

.flow-preview em {
  font-style: normal;
  color: var(--c-text-secondary);
  font-size: 12px;
  line-height: 1.55;
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
  padding: 14px 16px;
  border: 1px solid var(--c-border);
  border-radius: 11px;
  background: var(--c-surface);
  cursor: pointer;
  outline: none;
  transition: border-color 120ms ease, background-color 120ms ease;
}

.timeline-step:hover {
  border-color: var(--c-border-strong);
  background: #faf9f6;
}

.timeline-step:focus-visible {
  border-color: var(--c-border-focus);
  box-shadow: 0 0 0 2px var(--c-accent-ring);
}

.timeline-step.running {
  border-color: var(--c-text);
  background: #faf9f6;
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
  width: 18px;
  height: 18px;
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
  height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  background: var(--c-accent-soft);
  color: var(--c-accent);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0;
}

.timeline-head {
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
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
  width: 26px;
  height: 26px;
  border-radius: 999px;
  border: 1px solid var(--c-border);
  background: var(--c-bg-soft);
  color: var(--c-text-secondary);
  font-family: var(--font-mono);
  font-size: 11.5px;
  font-weight: 700;
}

.timeline-step.running .timeline-index {
  border-color: var(--c-text);
  color: var(--c-text);
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
  gap: 8px;
}

.timeline-meta small {
  color: var(--c-text-tertiary);
  font-size: 11.5px;
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
  border-color: var(--c-text);
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
  padding: 11px 14px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-control);
  background: #faf9f6;
  cursor: pointer;
  user-select: none;
  transition: border-color 120ms ease, background-color 120ms ease;
}

.research-toggle:hover {
  border-color: var(--c-border-strong);
}

.research-toggle:focus-visible {
  outline: 2px solid var(--c-border-focus);
  outline-offset: 2px;
}

.research-toggle.active {
  border-color: var(--c-border-strong);
  background: #ffffff;
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

.final-surface {
  padding: 28px;
  border-color: var(--c-border);
}

.final-body {
  margin: 0;
  padding: 20px 0 0;
  max-height: 680px;
  overflow-y: auto;
  border-top: 1px solid var(--c-border-soft);
  background: transparent;
  color: var(--c-text);
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-editorial);
  font-size: 15.5px;
  line-height: 1.95;
}

.draft-placeholder {
  min-height: 420px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  border: 1px solid var(--c-border);
  background-color: #ffffff;
  background-image: radial-gradient(#e5e2dc 1px, transparent 1px);
  background-size: 22px 22px;
}

.draft-icon {
  position: relative;
  z-index: 1;
  display: grid;
  place-items: center;
  width: 64px;
  height: 74px;
  margin-bottom: 22px;
  border: 1px solid var(--c-border);
  border-radius: 12px;
  color: var(--c-text);
  background: #ffffff;
  box-shadow: 0 8px 24px -6px rgba(24, 24, 27, 0.08);
  font-size: 24px;
}

.draft-icon::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 12px;
  border: 1px solid var(--c-border);
  background: #faf9f6;
  z-index: -1;
  transform: rotate(6deg) translate(8px, 3px);
}

.draft-placeholder h2 {
  margin: 0;
  color: var(--c-text);
  font-family: var(--font-editorial);
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.01em;
  line-height: 1.45;
}

.draft-placeholder p {
  max-width: 440px;
  margin: 10px 0 22px;
  color: var(--c-text-secondary);
  font-size: 13.5px;
  line-height: 1.8;
}

.draft-placeholder > span {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px solid var(--c-border);
  background: #faf9f6;
  color: var(--c-text-secondary);
  font-size: 12px;
  font-weight: 500;
}

@media (max-width: 1180px) {
  .studio-page {
    padding: 24px;
  }

  .studio-grid {
    grid-template-columns: minmax(310px, 350px) minmax(0, 1fr);
    gap: 18px;
  }

  .flow-preview {
    grid-template-columns: repeat(2, minmax(0, 1fr));
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

@media (max-width: 840px) {
  .studio-page {
    padding: 20px 16px;
  }

  .studio-banner {
    align-items: flex-start;
    flex-direction: column;
    padding: 22px 20px;
  }

  .studio-grid {
    grid-template-columns: 1fr;
  }

  .flow-preview {
    grid-template-columns: 1fr;
  }

  .mode-toggle {
    max-width: 100%;
  }

  .run-strip {
    gap: 16px;
  }

  .signal-row {
    width: 100%;
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
  .timeline-chevron,
  .flow-preview > span {
    transition: none;
  }

  .draft-icon {
    animation: none;
  }
}
</style>
