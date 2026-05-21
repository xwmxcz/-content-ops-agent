<template>
  <div class="studio-page">
    <section class="studio-banner">
      <div class="banner-copy">
        <span class="banner-kicker">Content Studio</span>
        <h1>把策略、写作、润色和审核放进一个内容工作台</h1>
        <p>
          面向内容运营的单主画布界面。左侧配置输入，中间编辑成稿，右侧查看 Agent 流程和审核结果。
        </p>
      </div>

      <div class="banner-actions">
        <button class="ghost-action" type="button" :disabled="loading" @click="resetWorkspace">
          <el-icon><Refresh /></el-icon>
          <span>重置工作台</span>
        </button>
        <el-button type="primary" size="large" :icon="VideoPlay" :loading="loading" @click="runPipeline">
          运行 Agent 流程
        </el-button>
      </div>
    </section>

    <section class="signal-row">
      <article v-for="card in signalCards" :key="card.label" class="signal-card">
        <span>{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
        <small>{{ card.note }}</small>
      </article>
    </section>

    <div class="studio-grid">
      <aside class="studio-rail left">
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
              <el-input
                v-model="form.topic"
                type="textarea"
                :rows="6"
                placeholder="例如：如何用 AI 提升内容运营效率"
              />
            </div>

            <div class="quick-prompts">
              <button
                v-for="prompt in quickPrompts"
                :key="prompt"
                type="button"
                class="prompt-chip"
                @click="form.topic = prompt"
              >
                {{ prompt }}
              </button>
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
              <el-input v-model="keywordsText" placeholder="AI, 效率, 工作流" />
            </div>
          </div>
        </section>

        <section class="studio-surface">
          <div class="surface-head compact">
            <div>
              <span class="surface-kicker">Execution</span>
              <h2>模型与执行参数</h2>
            </div>
          </div>
          <ModelSelector
            :model-value="modelConfig"
            @update:model-value="Object.assign(modelConfig, $event)"
          />
        </section>
      </aside>

      <main class="studio-center">
        <section class="studio-surface canvas-surface">
          <div class="surface-head">
            <div>
              <span class="surface-kicker">Final Draft</span>
              <h2>{{ finalTitle }}</h2>
            </div>
            <div class="surface-actions">
              <span v-if="runResult?.saved_content_id" class="surface-pill success">已保存 #{{ runResult.saved_content_id }}</span>
              <button class="ghost-action" type="button" :disabled="!editableContent" @click="copyFinal">
                <el-icon><DocumentCopy /></el-icon>
                <span>复制</span>
              </button>
              <button class="ghost-action" type="button" :disabled="!runResult?.saved_content_id" @click="router.push('/history')">
                <el-icon><Tickets /></el-icon>
                <span>历史</span>
              </button>
            </div>
          </div>

          <div class="blueprint-row">
            <div class="blueprint-chip">
              <span>平台</span>
              <strong>{{ platformLabel }}</strong>
            </div>
            <div class="blueprint-chip">
              <span>风格</span>
              <strong>{{ styleLabel }}</strong>
            </div>
            <div class="blueprint-chip">
              <span>模型</span>
              <strong>{{ modelLabel }}</strong>
            </div>
            <div class="blueprint-chip">
              <span>关键词</span>
              <strong>{{ keywordList.length ? `${keywordList.length} 个` : '未设置' }}</strong>
            </div>
          </div>

          <el-alert v-if="errorMessage" type="error" :title="errorMessage" show-icon :closable="false" class="surface-alert" />

          <div class="canvas-grid">
            <section class="draft-shell">
              <div class="editor-header">
                <span>成稿编辑区</span>
                <small>{{ runResult ? '流程已完成，可继续手动编辑' : '输入主题并运行流程后生成成稿' }}</small>
              </div>

              <div v-if="loading" class="draft-loading">
                <el-skeleton :rows="11" animated />
              </div>
              <div v-else-if="editableContent" class="draft-editor">
                <el-input
                  v-model="editableContent"
                  type="textarea"
                  :autosize="{ minRows: 22, maxRows: 30 }"
                  class="editor-input"
                />
              </div>
              <div v-else class="draft-empty">
                <strong>这里会出现可直接发布的最终稿</strong>
                <p>流程会先给出内容策略，再生成初稿、完成润色，并附带审核意见。</p>
              </div>
            </section>

            <aside class="preview-shell">
              <div class="preview-header">
                <span>平台预览</span>
                <small>{{ platformLabel }}</small>
              </div>

              <div class="preview-card">
                <div class="preview-meta">
                  <div class="preview-avatar">CO</div>
                  <div>
                    <strong>{{ platformLabel }} 发布视图</strong>
                    <span>{{ qualityTone }}</span>
                  </div>
                </div>

                <h3>{{ finalTitle }}</h3>
                <div class="preview-body">{{ editableContent || '暂无内容' }}</div>

                <div class="preview-tags">
                  <span v-for="tag in previewTags" :key="tag" class="preview-tag">#{{ tag }}</span>
                </div>
              </div>
            </aside>
          </div>
        </section>
      </main>

      <aside class="studio-rail right">
        <section class="studio-surface">
          <div class="surface-head compact">
            <div>
              <span class="surface-kicker">Pipeline Console</span>
              <h2>Agent 流程</h2>
            </div>
            <span class="surface-pill" :class="loading ? 'running' : runResult ? 'success' : ''">{{ pipelineState }}</span>
          </div>

          <div class="quality-panel">
            <div class="quality-score">
              <span>Quality</span>
              <strong>{{ qualityScore }}</strong>
            </div>
            <div class="quality-meta">
              <div>
                <span>提供商</span>
                <strong>{{ providerLabel }}</strong>
              </div>
              <div>
                <span>流程</span>
                <strong>4 个 Agent</strong>
              </div>
            </div>
          </div>

          <div class="agent-stack">
            <article v-for="step in visibleSteps" :key="step.id" class="agent-card" :class="step.status">
              <div class="agent-topline">
                <div class="agent-badge">
                  <el-icon v-if="step.status === 'completed'"><CircleCheck /></el-icon>
                  <el-icon v-else-if="step.status === 'failed'"><CircleClose /></el-icon>
                  <el-icon v-else-if="step.status === 'running'" class="is-loading"><Loading /></el-icon>
                  <span v-else>{{ step.id.slice(0, 1).toUpperCase() }}</span>
                </div>
                <div class="agent-copy">
                  <strong>{{ step.name }}</strong>
                  <span>{{ statusLabel(step.status) }}</span>
                </div>
                <small v-if="step.duration_ms">{{ step.duration_ms }} ms</small>
              </div>

              <p class="agent-role">{{ step.role }}</p>
              <p class="agent-input">{{ step.input_summary }}</p>
              <pre v-if="step.output" class="agent-output">{{ step.output }}</pre>
              <el-alert v-if="step.error" :title="step.error" type="error" :closable="false" />
            </article>
          </div>
        </section>

        <section class="studio-surface review-surface">
          <div class="surface-head compact">
            <div>
              <span class="surface-kicker">Review Notes</span>
              <h2>审核结果</h2>
            </div>
          </div>
          <pre class="review-copy">{{ reviewOutput || 'Review Agent 会在流程结束后给出评分、风险和改进建议。' }}</pre>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index'
import {
  CircleCheck,
  CircleClose,
  DocumentCopy,
  Loading,
  Refresh,
  Tickets,
  VideoPlay
} from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import ModelSelector from '../components/ModelSelector.vue'
import type { AgentRunPayload, AgentRunResponse, AgentStep } from '../api/agent'
import { createAgentRunJob, extractAgentRun, waitForJobResult, type JobResponse } from '../api/jobs'

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

const quickPrompts = [
  '如何用 AI 提升内容运营效率',
  '一周内容选题如何做得更稳',
  '品牌如何建立统一的内容语气',
  '内容团队如何做复盘和迭代'
]

const placeholderSteps: AgentStep[] = [
  {
    id: 'strategy',
    name: 'Strategy Agent',
    role: '内容策略',
    status: 'pending',
    input_summary: '分析主题、受众与内容角度。',
    output: '',
    duration_ms: 0
  },
  {
    id: 'writer',
    name: 'Writer Agent',
    role: '初稿写作',
    status: 'pending',
    input_summary: '把策略转成可编辑的第一版内容。',
    output: '',
    duration_ms: 0
  },
  {
    id: 'editor',
    name: 'Editor Agent',
    role: '润色编辑',
    status: 'pending',
    input_summary: '优化表达、结构和平台适配。',
    output: '',
    duration_ms: 0
  },
  {
    id: 'review',
    name: 'Review Agent',
    role: '质量审核',
    status: 'pending',
    input_summary: '给出评分、风险与改进建议。',
    output: '',
    duration_ms: 0
  }
]

const form = reactive({
  topic: '',
  content_type: 'xiaohongshu',
  style: 'professional',
  length: 'medium'
})

const modelConfig = reactive({
  provider: '',
  model: '',
  temperature: 0.7,
  max_tokens: 2048
})

const keywordsText = ref('')
const loading = ref(false)
const errorMessage = ref('')
const runResult = ref<AgentRunResponse>()
const editableContent = ref('')
const currentJob = ref<JobResponse>()

const keywordList = computed(() => parseKeywords())
const platformLabel = computed(() => {
  return contentTypeOptions.find(item => item.value === form.content_type)?.label ?? form.content_type
})
const styleLabel = computed(() => {
  return styleOptions.find(item => item.value === form.style)?.label ?? form.style
})
const modelLabel = computed(() => modelConfig.model || '自动选择')
const providerLabel = computed(() => runResult.value?.provider || modelConfig.provider || '未指定')
const finalTitle = computed(() => runResult.value?.final_content.title || form.topic || '未命名内容')
const previewTags = computed(() => runResult.value?.final_content.tags.length ? runResult.value.final_content.tags : keywordList.value)
const reviewOutput = computed(() => runResult.value?.steps.find(step => step.id === 'review')?.output ?? '')
const qualityScore = computed(() => {
  const match = reviewOutput.value.match(/(\d{2,3})/)
  return match ? match[1] : '--'
})
const qualityTone = computed(() => {
  if (!runResult.value) return '等待生成'
  return reviewOutput.value ? '已附带审核意见' : '已完成生成'
})
const pipelineState = computed(() => {
  if (loading.value && currentJob.value) {
    const labels: Record<string, string> = {
      queued: '排队中',
      running: '运行中',
      completed: '已完成',
      failed: '失败'
    }
    return `${labels[currentJob.value.status] ?? currentJob.value.status} ${currentJob.value.progress}%`
  }
  if (loading.value) return '提交中'
  if (runResult.value) return '已完成'
  return '待运行'
})
const signalCards = computed(() => [
  { label: '工作流', value: '4 Stage', note: 'Strategy / Writer / Editor / Review' },
  { label: '当前平台', value: platformLabel.value, note: '内容结构和表达会随平台调整' },
  { label: '模型', value: modelLabel.value, note: providerLabel.value },
  { label: '输出状态', value: runResult.value?.saved_content_id ? '已入库' : '草稿中', note: '最终稿可继续进入历史与复用流程' }
])

const visibleSteps = computed<AgentStep[]>(() => {
  if (runResult.value) return runResult.value.steps
  if (!loading.value) return placeholderSteps
  return placeholderSteps.map((step, index) => ({
    ...step,
    status: index === 0 ? 'running' : 'pending'
  }))
})

async function runPipeline() {
  if (!form.topic.trim()) {
    ElMessage.warning('请输入内容主题')
    return
  }

  loading.value = true
  errorMessage.value = ''
  runResult.value = undefined
  editableContent.value = ''
  currentJob.value = undefined

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
    currentJob.value = await createAgentRunJob(payload)
    runResult.value = await waitForJobResult(currentJob.value.id, extractAgentRun, job => {
      currentJob.value = job
    })
    editableContent.value = runResult.value.final_content.content
    ElMessage.success(
      runResult.value.saved_content_id ? `流程已完成，内容已保存 #${runResult.value.saved_content_id}` : '流程已完成'
    )
  } catch (error) {
    errorMessage.value = (error as Error).message
    ElMessage.error(errorMessage.value)
  } finally {
    loading.value = false
  }
}

function resetWorkspace() {
  form.topic = ''
  keywordsText.value = ''
  runResult.value = undefined
  editableContent.value = ''
  errorMessage.value = ''
  currentJob.value = undefined
}

async function copyFinal() {
  if (!editableContent.value) return
  try {
    await navigator.clipboard.writeText(editableContent.value)
    ElMessage.success('已复制最终稿')
  } catch {
    ElMessage.error('复制失败，请手动选择文本复制')
  }
}

function parseKeywords() {
  return keywordsText.value
    .split(/[,\n，]/)
    .map(item => item.trim())
    .filter(Boolean)
}

function statusLabel(status: AgentStep['status']) {
  const labels: Record<AgentStep['status'], string> = {
    pending: '待运行',
    running: '运行中',
    completed: '已完成',
    failed: '失败'
  }
  return labels[status]
}
</script>

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
  margin: 0 auto 24px;
  max-width: 1520px;
}

.banner-copy {
  max-width: 720px;
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
  font-size: 32px;
  font-weight: 600;
  line-height: 1.15;
  letter-spacing: -0.025em;
}

.banner-copy p {
  margin: 0;
  color: var(--c-text-secondary);
  font-size: 14px;
  line-height: 1.55;
}

.banner-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
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
  transition: border-color 100ms ease, background-color 100ms ease;
}

.ghost-action:hover {
  border-color: var(--c-border-strong);
}

.ghost-action:disabled {
  opacity: 0.5;
  cursor: default;
}

.ghost-action :deep(.el-icon) {
  font-size: 14px;
}

/* Signal row (top metric strip) ----------------------------------------- */

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
}

.signal-card strong {
  display: block;
  margin: 6px 0 4px;
  color: var(--c-text);
  font-size: 18px;
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
  grid-template-columns: minmax(290px, 340px) minmax(0, 1fr) minmax(320px, 380px);
  gap: 16px;
  max-width: 1520px;
  margin: 0 auto;
}

.studio-center,
.studio-rail {
  min-width: 0;
}

.studio-surface {
  min-width: 0;
  padding: 20px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg);
}

.left,
.right {
  display: grid;
  align-content: start;
  gap: 16px;
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
  height: 24px;
  padding: 0 8px;
  border: 1px solid var(--c-border);
  border-radius: 999px;
  color: var(--c-text-secondary);
  background: var(--c-bg);
  cursor: pointer;
  font-size: 12px;
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

.surface-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.blueprint-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 16px;
}

.blueprint-chip {
  padding: 10px 12px;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  background: var(--c-bg-soft);
}

.blueprint-chip span {
  display: block;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.blueprint-chip strong {
  display: block;
  margin-top: 4px;
  color: var(--c-text);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.3;
  letter-spacing: -0.01em;
}

.surface-alert {
  margin-bottom: 14px;
}

.canvas-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
}

.draft-shell,
.preview-shell {
  min-width: 0;
}

.editor-header,
.preview-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.editor-header span,
.preview-header span {
  flex-shrink: 0;
  color: var(--c-text);
  font-weight: 600;
  font-size: 13px;
  white-space: nowrap;
  letter-spacing: -0.01em;
}

.editor-header small,
.preview-header small {
  flex: 1 1 auto;
  min-width: 0;
  color: var(--c-text-tertiary);
  font-size: 12px;
}

.draft-editor,
.draft-loading,
.draft-empty {
  min-height: 620px;
  padding: 16px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg);
  transition: border-color 120ms ease;
}

.draft-editor:focus-within {
  border-color: var(--c-accent);
  box-shadow: 0 0 0 3px var(--c-accent-ring);
}

.draft-empty {
  display: grid;
  align-content: center;
  gap: 8px;
  color: var(--c-text-tertiary);
  text-align: center;
}

.draft-empty strong {
  color: var(--c-text);
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.draft-empty p {
  margin: 0;
  color: var(--c-text-secondary);
  font-size: 13px;
  line-height: 1.55;
}

.editor-input :deep(.el-textarea__inner) {
  min-height: 584px !important;
  padding: 0;
  border: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
  color: var(--c-text);
  font-family: var(--font-ui);
  font-size: 14.5px;
  line-height: 1.7;
  letter-spacing: -0.005em;
}

.editor-input :deep(.el-textarea__inner:focus) {
  box-shadow: none !important;
}

/* Platform preview card -------------------------------------------------- */

.preview-card {
  display: grid;
  align-content: start;
  gap: 14px;
  min-height: 620px;
  padding: 20px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  color: var(--c-text);
  background: var(--c-bg-soft);
}

.preview-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.preview-avatar {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  color: #ffffff;
  background: var(--c-accent);
  font-weight: 600;
  font-size: 12px;
}

.preview-meta strong {
  display: block;
  color: var(--c-text);
  font-size: 13px;
  font-weight: 600;
}

.preview-meta span {
  display: block;
  color: var(--c-text-tertiary);
  font-size: 12px;
}

.preview-card h3 {
  margin: 0;
  color: var(--c-text);
  font-size: 18px;
  font-weight: 600;
  line-height: 1.3;
  letter-spacing: -0.015em;
}

.preview-body {
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--c-text);
  font-size: 14px;
  line-height: 1.7;
}

.preview-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: auto;
}

.preview-tag {
  height: 22px;
  padding: 0 8px;
  border: 1px solid var(--c-border);
  border-radius: 999px;
  color: var(--c-text-secondary);
  background: var(--c-bg);
  font-size: 11px;
  font-family: var(--font-mono);
  line-height: 20px;
}

/* Pipeline / agent stack ------------------------------------------------- */

.quality-panel {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr);
  gap: 12px;
  margin-bottom: 16px;
  padding: 14px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg-soft);
}

.quality-score {
  display: grid;
  align-content: start;
}

.quality-score span {
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.quality-score strong {
  margin-top: 4px;
  color: var(--c-text);
  font-size: 36px;
  font-weight: 600;
  line-height: 1;
  letter-spacing: -0.03em;
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
}

.quality-meta {
  display: grid;
  gap: 8px;
}

.quality-meta div {
  display: grid;
  gap: 2px;
}

.quality-meta span {
  display: block;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.quality-meta strong {
  display: block;
  color: var(--c-text);
  font-size: 13px;
  font-weight: 500;
  font-family: var(--font-mono);
  letter-spacing: -0.01em;
  word-break: break-all;
}

.agent-stack {
  display: grid;
  gap: 8px;
}

.agent-card {
  padding: 12px 14px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg);
  transition: border-color 120ms ease;
}

.agent-card.completed {
  border-color: var(--c-border);
  background: var(--c-bg);
}

.agent-card.failed {
  border-color: var(--c-fail);
  background: var(--c-fail-soft);
}

.agent-card.running {
  border-color: var(--c-accent);
  background: var(--c-accent-soft);
}

.agent-topline {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
}

.agent-badge {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  color: var(--c-text-tertiary);
  background: var(--c-bg-soft);
  border: 1px solid var(--c-border);
  font-weight: 600;
  font-size: 11px;
  font-family: var(--font-mono);
}

.agent-badge :deep(.el-icon) {
  font-size: 14px;
}

.agent-card.completed .agent-badge {
  color: var(--c-ok);
  background: var(--c-ok-soft);
  border-color: var(--c-ok);
}

.agent-card.failed .agent-badge {
  color: var(--c-fail);
  background: var(--c-fail-soft);
  border-color: var(--c-fail);
}

.agent-card.running .agent-badge {
  color: var(--c-accent);
  background: #ffffff;
  border-color: var(--c-accent);
  position: relative;
}

.agent-card.running .agent-badge::after {
  content: '';
  position: absolute;
  inset: -3px;
  border-radius: 999px;
  border: 2px solid var(--c-accent);
  opacity: 0.4;
  animation: agent-pulse 1.6s ease-out infinite;
}

@keyframes agent-pulse {
  0% { transform: scale(0.85); opacity: 0.5; }
  100% { transform: scale(1.4); opacity: 0; }
}

.is-loading {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.agent-copy strong {
  display: block;
  color: var(--c-text);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.agent-copy span {
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-family: var(--font-mono);
}

.agent-topline small {
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-family: var(--font-mono);
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
}

.agent-role,
.agent-input {
  margin: 8px 0 0;
  color: var(--c-text-secondary);
  font-size: 12px;
  line-height: 1.55;
}

.agent-output {
  margin: 10px 0 0;
  padding: 10px 12px;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  background: var(--c-bg-code);
  color: var(--c-text);
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.55;
}

.review-copy {
  margin: 0;
  padding: 14px;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  background: var(--c-bg-code);
  color: var(--c-text);
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-mono);
  font-size: 12.5px;
  line-height: 1.6;
}

.review-surface {
  position: sticky;
  top: 20px;
}

@media (max-width: 1440px) {
  .signal-row,
  .blueprint-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .studio-grid {
    grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
  }

  .right {
    grid-column: 1 / -1;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .review-surface {
    position: static;
  }
}

@media (max-width: 1180px) {
  .canvas-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .draft-editor,
  .draft-loading,
  .draft-empty,
  .preview-card {
    min-height: 0;
  }

  .editor-input :deep(.el-textarea__inner) {
    min-height: 360px !important;
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

  .signal-row,
  .studio-grid,
  .field-grid,
  .canvas-grid,
  .right,
  .blueprint-row {
    grid-template-columns: 1fr;
  }

  .draft-editor,
  .draft-loading,
  .draft-empty,
  .preview-card {
    min-height: auto;
  }

  .editor-input :deep(.el-textarea__inner) {
    min-height: 420px !important;
  }
}
</style>
