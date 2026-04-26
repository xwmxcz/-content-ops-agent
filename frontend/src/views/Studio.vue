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
  padding: 20px 22px;
}

.studio-banner {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  margin: 0 auto 16px;
  max-width: 1520px;
}

.banner-copy {
  max-width: 860px;
}

.banner-kicker,
.surface-kicker {
  display: inline-block;
  color: #6b7468;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.banner-copy h1 {
  max-width: 880px;
  margin: 8px 0 10px;
  color: #162126;
  font-size: clamp(30px, 4vw, 42px);
  line-height: 1.05;
}

.banner-copy p {
  max-width: 700px;
  margin: 0;
  color: #5c676e;
  font-size: 15px;
  line-height: 1.7;
}

.banner-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.ghost-action {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  padding: 0 14px;
  border: 1px solid rgba(22, 33, 38, 0.12);
  border-radius: 8px;
  color: #24333a;
  background: rgba(255, 255, 255, 0.76);
  cursor: pointer;
}

.ghost-action:disabled {
  opacity: 0.48;
  cursor: default;
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
  border: 1px solid rgba(22, 33, 38, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 18px 50px rgba(21, 31, 39, 0.08);
  backdrop-filter: blur(14px);
}

.signal-card span,
.blueprint-chip span,
.quality-score span,
.quality-meta span {
  display: block;
  color: #6a7378;
  font-size: 12px;
}

.signal-card strong,
.blueprint-chip strong,
.quality-meta strong {
  display: block;
  margin: 5px 0 6px;
  color: #182126;
  font-size: 18px;
}

.signal-card small {
  color: #7a8389;
  line-height: 1.5;
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
  padding: 16px;
  border: 1px solid rgba(22, 33, 38, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 18px 50px rgba(21, 31, 39, 0.08);
  backdrop-filter: blur(14px);
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
  margin-bottom: 14px;
}

.surface-head.compact {
  margin-bottom: 12px;
}

.surface-head h2 {
  margin: 5px 0 0;
  color: #182126;
  font-size: 20px;
  line-height: 1.2;
}

.surface-pill {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid rgba(15, 133, 116, 0.18);
  border-radius: 999px;
  color: #0f5f55;
  background: rgba(15, 133, 116, 0.1);
  font-size: 12px;
  white-space: nowrap;
}

.surface-pill.success {
  color: #0e6657;
}

.surface-pill.running {
  color: #8b5a16;
  border-color: rgba(196, 147, 63, 0.24);
  background: rgba(196, 147, 63, 0.12);
}

.field-stack {
  display: grid;
  gap: 14px;
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
  color: #425158;
  font-size: 13px;
  font-weight: 600;
}

.quick-prompts {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.prompt-chip {
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid rgba(22, 33, 38, 0.1);
  border-radius: 999px;
  color: #304147;
  background: rgba(248, 244, 237, 0.92);
  cursor: pointer;
  font-size: 12px;
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
  gap: 10px;
  margin-bottom: 14px;
}

.blueprint-chip {
  padding: 12px;
  border: 1px solid rgba(22, 33, 38, 0.08);
  border-radius: 8px;
  background: linear-gradient(180deg, rgba(250, 246, 239, 0.94), rgba(255, 255, 255, 0.88));
}

.surface-alert {
  margin-bottom: 14px;
}

.canvas-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 14px;
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
  margin-bottom: 10px;
}

.editor-header span,
.preview-header span {
  color: #172228;
  font-weight: 700;
}

.editor-header small,
.preview-header small {
  color: #768187;
}

.draft-editor,
.draft-loading,
.draft-empty {
  min-height: 620px;
  padding: 16px;
  border: 1px solid rgba(22, 33, 38, 0.08);
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(249, 250, 252, 0.9), rgba(255, 255, 255, 0.96)),
    repeating-linear-gradient(180deg, transparent, transparent 31px, rgba(17, 36, 45, 0.04) 31px, rgba(17, 36, 45, 0.04) 32px);
}

.draft-empty {
  display: grid;
  align-content: center;
  gap: 10px;
  color: #546068;
  text-align: center;
}

.draft-empty strong {
  color: #182126;
  font-size: 18px;
}

.editor-input :deep(.el-textarea__inner) {
  min-height: 584px !important;
  padding: 0;
  border: 0;
  background: transparent;
  color: #182126;
  line-height: 1.9;
}

.preview-card {
  display: grid;
  align-content: start;
  gap: 14px;
  min-height: 620px;
  padding: 18px;
  border: 1px solid rgba(22, 33, 38, 0.08);
  border-radius: 8px;
  color: #1d2730;
  background: linear-gradient(180deg, #fffdf9 0%, #f8faf7 100%);
}

.preview-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.preview-avatar {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 8px;
  color: #12353b;
  background: linear-gradient(135deg, rgba(122, 210, 192, 0.36), rgba(212, 175, 116, 0.32));
  font-weight: 800;
}

.preview-meta strong,
.preview-card h3 {
  display: block;
}

.preview-meta span {
  color: #748087;
  font-size: 12px;
}

.preview-card h3 {
  margin: 0;
  color: #162126;
  font-size: 20px;
  line-height: 1.35;
}

.preview-body {
  white-space: pre-wrap;
  word-break: break-word;
  color: #273138;
  line-height: 1.85;
}

.preview-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: auto;
}

.preview-tag {
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  color: #0e5a53;
  background: rgba(15, 133, 116, 0.1);
  font-size: 12px;
  line-height: 28px;
}

.quality-panel {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: 12px;
  margin-bottom: 14px;
  padding: 12px;
  border: 1px solid rgba(22, 33, 38, 0.08);
  border-radius: 8px;
  background: linear-gradient(180deg, rgba(250, 246, 239, 0.94), rgba(255, 255, 255, 0.88));
}

.quality-score {
  display: grid;
  align-content: start;
}

.quality-score strong {
  margin-top: 6px;
  color: #162126;
  font-size: 40px;
  line-height: 1;
}

.quality-meta {
  display: grid;
  gap: 10px;
}

.agent-stack {
  display: grid;
  gap: 10px;
}

.agent-card {
  padding: 12px;
  border: 1px solid rgba(22, 33, 38, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.62);
}

.agent-card.completed {
  border-color: rgba(15, 133, 116, 0.18);
  background: rgba(15, 133, 116, 0.05);
}

.agent-card.failed {
  border-color: rgba(191, 55, 55, 0.2);
  background: rgba(191, 55, 55, 0.05);
}

.agent-card.running {
  border-color: rgba(196, 147, 63, 0.28);
  background: rgba(196, 147, 63, 0.06);
}

.agent-topline {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
}

.agent-badge {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border: 1px solid rgba(22, 33, 38, 0.1);
  border-radius: 8px;
  color: #334148;
  background: rgba(255, 255, 255, 0.8);
  font-weight: 700;
}

.agent-copy strong {
  display: block;
  color: #172228;
}

.agent-copy span,
.agent-topline small,
.agent-role,
.agent-input {
  color: #6c767b;
  font-size: 12px;
}

.agent-role,
.agent-input {
  margin: 8px 0 0;
  line-height: 1.6;
}

.agent-output,
.review-copy {
  margin: 10px 0 0;
  color: #243039;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  line-height: 1.65;
}

.review-surface {
  position: sticky;
  top: 20px;
}

@media (max-width: 1320px) {
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
