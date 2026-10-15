<template>
  <div class="page refine-page">
    <section class="refine-hero">
      <div>
        <h1 class="page-title">内容打磨</h1>
        <p class="page-subtitle">让已有的好内容，再进一步。改写表达、尝试新风格，或找到更好的标题。</p>
      </div>
      <div class="hero-actions">
        <el-button :icon="Refresh" :loading="loadingList" @click="loadRecent">刷新内容库</el-button>
      </div>
    </section>

    <div class="refine-grid">
      <section class="section source-section">
        <div class="section-head">
          <div>
            <h2>选择内容</h2>
          </div>
          <span class="section-pill">{{ source ? `#${source.id}` : '未选择' }}</span>
        </div>

        <div class="manual-loader">
          <el-input-number v-model="contentId" :min="1" :disabled="loading" aria-label="内容编号" />
          <el-button :icon="Search" :disabled="loading" :loading="loadingSource" @click="loadContent">加载</el-button>
        </div>
        <span class="list-caption">最近的内容，也可以输入编号加载</span>

        <div class="recent-list">
          <button
            v-for="item in recentItems"
            :key="item.id"
            type="button"
            class="recent-card"
            :class="{ active: source?.id === item.id }"
            :aria-pressed="source?.id === item.id"
            :disabled="loading"
            @click="selectContent(item.id)"
          >
            <strong>{{ item.title || '未命名内容' }}</strong>
            <span>{{ getContentTypeLabel(item.content_type) }} · {{ getStatusLabel(item.status) }}</span>
            <small>{{ item.content }}</small>
          </button>
          <p v-if="!loadingList && !recentItems.length" class="empty-list">内容库还没有稿件。先去创作工作台写下第一篇。</p>
        </div>

        <div v-if="source" class="source-preview">
          <div class="preview-topline">
            <strong>{{ source.title || '未命名内容' }}</strong>
            <span>{{ getStyleLabel(source.style) }}</span>
          </div>
          <div class="content-preview">{{ source.content }}</div>
        </div>
      </section>

      <section class="section action-section">
        <div class="section-head">
          <div>
            <h2>打磨方式</h2>
          </div>
        </div>

        <el-tabs v-model="activeTab">
          <el-tab-pane label="改写" name="rewrite">
            <el-input
              v-model="instruction"
              type="textarea"
              :rows="5"
              placeholder="例如：语气更亲切，结构更清晰，补充一个行动建议"
            />
            <el-button type="primary" :loading="loading" class="action-btn" @click="rewrite">执行改写</el-button>
          </el-tab-pane>

          <el-tab-pane label="风格切换" name="style">
            <p class="tab-copy">为这篇内容选择一种新的表达风格。</p>
            <el-segmented v-model="newStyle" :options="styleSegmentOptions" />
            <el-button type="primary" :loading="loading" class="action-btn" @click="switchStyle">切换风格</el-button>
          </el-tab-pane>

          <el-tab-pane label="标题优化" name="titles">
            <p class="tab-copy">选择候选标题数量，发现不同的切入角度。</p>
            <el-slider v-model="titleCount" :min="3" :max="10" show-input />
            <el-button type="primary" :loading="loading" class="action-btn" @click="titles">生成标题</el-button>
          </el-tab-pane>

          <el-tab-pane label="SEO" name="seo">
            <p class="tab-copy">获取关键词建议、标题优化方向、结构建议和 meta 描述。</p>
            <el-button type="primary" :loading="loading" @click="seo">分析 SEO</el-button>
          </el-tab-pane>
        </el-tabs>

        <details class="model-settings">
          <summary>模型与参数 <span>按需调整</span></summary>
          <ModelSelector
            :model-value="modelConfig"
            @update:model-value="Object.assign(modelConfig, $event)"
          />
        </details>
      </section>

      <section class="section result-section">
        <div class="section-head">
          <div>
            <h2>输出结果</h2>
          </div>
          <div class="hero-actions">
            <span v-if="currentJob" class="section-pill">{{ jobState }}</span>
            <el-button :icon="DocumentCopy" :disabled="!resultText" @click="copyResult">复制</el-button>
          </div>
        </div>

        <div v-if="!resultText && !loading" class="result-empty">
          <div class="result-icon"><el-icon><DocumentCopy /></el-icon></div>
          <h3>留一点空间，给更好的表达</h3>
          <p>选择一篇内容和打磨方式，操作结果会显示在这里。</p>
        </div>
        <el-skeleton v-else-if="loading" :rows="10" animated />
        <div v-else class="result-shell">
          <div class="content-preview">{{ resultText }}</div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElInputNumber } from 'element-plus/es/components/input-number/index'
import { ElMessage } from 'element-plus/es/components/message/index'
import { ElSegmented } from 'element-plus/es/components/segmented/index'
import { ElSkeleton } from 'element-plus/es/components/skeleton/index'
import { ElSlider } from 'element-plus/es/components/slider/index'
import { ElTabPane, ElTabs } from 'element-plus/es/components/tabs/index'
import 'element-plus/es/components/input-number/style/css'
import 'element-plus/es/components/segmented/style/css'
import 'element-plus/es/components/skeleton/style/css'
import 'element-plus/es/components/slider/style/css'
import 'element-plus/es/components/tabs/style/css'
import { DocumentCopy, Refresh, Search } from '@element-plus/icons-vue'
import ModelSelector from '../components/ModelSelector.vue'
import { getContent, getContents, type ContentItem } from '../api/content'
import { createRefineJob, createSeoJob, createTitlesJob, extractContent, extractText, waitForJobResult, type JobResponse } from '../api/jobs'
import { STYLE_OPTIONS, getContentTypeLabel, getStatusLabel, getStyleLabel } from '../constants/content'

const route = useRoute()
const styleSegmentOptions = STYLE_OPTIONS.map(item => ({ ...item }))

const modelConfig = reactive({ provider: '', model: '', temperature: 0.7, max_tokens: 2048 })
const contentId = ref(1)
const source = ref<ContentItem>()
const recentItems = ref<ContentItem[]>([])
const activeTab = ref('rewrite')
const instruction = ref('')
const newStyle = ref('professional')
const titleCount = ref(5)
const resultText = ref('')
const loading = ref(false)
const loadingList = ref(false)
const loadingSource = ref(false)
let sourceRequest = 0
const currentJob = ref<JobResponse>()

const jobState = computed(() => {
  if (!currentJob.value) return ''
  if (currentJob.value.status === 'failed' && currentJob.value.next_retry_at) return '等待自动重试'
  const labels: Record<string, string> = {
    queued: '排队中',
    running: '运行中',
    completed: '已完成',
    failed: '失败'
  }
  return `${labels[currentJob.value.status] ?? currentJob.value.status} ${currentJob.value.progress}%`
})

async function loadRecent() {
  loadingList.value = true
  try {
    recentItems.value = await getContents({ limit: 8 })
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loadingList.value = false
  }
}

async function loadContent() {
  if (loading.value) return
  const request = ++sourceRequest
  const id = contentId.value
  source.value = undefined
  loadingSource.value = false
  resultText.value = ''
  currentJob.value = undefined
  if (!Number.isSafeInteger(id) || id <= 0) {
    ElMessage.warning('请输入有效的内容编号')
    return
  }
  loadingSource.value = true
  try {
    const content = await getContent(id)
    if (request === sourceRequest) source.value = content
  } catch (error) {
    if (request === sourceRequest) ElMessage.error((error as Error).message)
  } finally {
    if (request === sourceRequest) loadingSource.value = false
  }
}

async function selectContent(id: number) {
  if (loading.value) return
  contentId.value = id
  await loadContent()
}

async function run(task: (sourceId: number) => Promise<string>) {
  if (loading.value) return
  if (!source.value) {
    ElMessage.warning('请先选择内容')
    return
  }
  loading.value = true
  currentJob.value = undefined
  try {
    resultText.value = await task(source.value.id)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function rewrite() {
  run(async sourceId => {
    const job = await createRefineJob({
      content_id: sourceId,
      instruction: instruction.value,
      provider: modelConfig.provider,
      model: modelConfig.model,
      temperature: modelConfig.temperature,
      max_tokens: modelConfig.max_tokens
    })
    currentJob.value = job
    const result = await waitForJobResult(job.id, extractContent, nextJob => {
      currentJob.value = nextJob
    })
    await loadRecent()
    return result.content
  })
}

function switchStyle() {
  run(async sourceId => {
    const job = await createRefineJob({
      content_id: sourceId,
      new_style: newStyle.value,
      provider: modelConfig.provider,
      model: modelConfig.model,
      temperature: modelConfig.temperature,
      max_tokens: modelConfig.max_tokens
    })
    currentJob.value = job
    const result = await waitForJobResult(job.id, extractContent, nextJob => {
      currentJob.value = nextJob
    })
    await loadRecent()
    return result.content
  })
}

function titles() {
  run(async sourceId => {
    const job = await createTitlesJob({
      content_id: sourceId,
      count: titleCount.value,
      provider: modelConfig.provider,
      model: modelConfig.model
    })
    currentJob.value = job
    return waitForJobResult(job.id, extractText, nextJob => {
      currentJob.value = nextJob
    })
  })
}

function seo() {
  run(async sourceId => {
    const job = await createSeoJob({
      content_id: sourceId,
      provider: modelConfig.provider,
      model: modelConfig.model
    })
    currentJob.value = job
    return waitForJobResult(job.id, extractText, nextJob => {
      currentJob.value = nextJob
    })
  })
}

async function copyResult() {
  if (!resultText.value) return
  try {
    await navigator.clipboard.writeText(resultText.value)
    ElMessage.success('已复制结果')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

onMounted(async () => {
  await loadRecent()
  const routeId = Number(route.query.id)
  if (Number.isSafeInteger(routeId) && routeId > 0) {
    contentId.value = routeId
    await loadContent()
  }
})

onBeforeUnmount(() => { sourceRequest += 1 })
</script>

<style scoped>
.refine-page {
  display: grid;
  gap: 24px;
  width: 100%;
  max-width: 1760px;
  padding: 28px 36px 44px;
  background: transparent;
}

.refine-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  padding: 4px 0 22px;
  border-bottom: 1px solid var(--c-border);
}

.refine-hero .page-title {
  margin: 0;
  color: var(--c-text);
  font-family: var(--font-display);
  font-size: clamp(23px, 2.1vw, 29px);
  font-weight: 700;
  letter-spacing: -0.025em;
  line-height: 1.25;
}

.refine-hero .page-subtitle {
  margin-top: 6px;
  color: var(--c-text-secondary);
  font-size: 13.5px;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.refine-grid {
  display: grid;
  grid-template-columns: minmax(340px, 410px) minmax(0, 1fr);
  grid-template-areas: 'source action' 'source result';
  gap: 24px;
  align-items: start;
}

.source-section,
.action-section,
.result-section {
  display: grid;
  align-content: start;
  min-width: 0;
  gap: 20px;
  padding: 24px;
}

.source-section {
  grid-area: source;
}

.action-section {
  grid-area: action;
}

.result-section {
  grid-area: result;
  min-height: 420px;
  align-content: stretch;
  grid-template-rows: auto minmax(0, 1fr);
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--c-border-soft);
}

.section-head h2 {
  margin: 0;
  color: var(--c-text);
  font-size: 16px;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.section-pill {
  display: inline-flex;
  align-items: center;
  min-height: 25px;
  padding: 2px 10px;
  border: 1px solid var(--c-border);
  border-radius: 999px;
  color: var(--c-text-secondary);
  background: #faf9f6;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0;
}

.manual-loader {
  display: flex;
  align-items: center;
  gap: 8px;
}

.manual-loader :deep(.el-input-number) {
  flex: 1;
  min-width: 0;
}

.list-caption {
  margin-top: -10px;
  color: var(--c-text-tertiary);
  font-size: 12px;
}

.recent-list {
  display: grid;
  gap: 10px;
  max-height: 380px;
  overflow-y: auto;
  padding-right: 4px;
}

.recent-list::-webkit-scrollbar,
.source-preview::-webkit-scrollbar {
  width: 8px;
}

.recent-list::-webkit-scrollbar-thumb,
.source-preview::-webkit-scrollbar-thumb {
  background: var(--c-border);
  border-radius: 4px;
}

.recent-list::-webkit-scrollbar-thumb:hover,
.source-preview::-webkit-scrollbar-thumb:hover {
  background: var(--c-text-tertiary);
}

.recent-card {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border: 1px solid var(--c-border);
  border-radius: 10px;
  color: var(--c-text);
  background: #faf9f6;
  text-align: left;
  cursor: pointer;
  transition: border-color 150ms ease, box-shadow 150ms ease, background-color 150ms ease;
}

.recent-card:hover {
  border-color: var(--c-border-hover);
  background: #ffffff;
  box-shadow: 0 4px 12px -4px rgba(24, 24, 27, 0.06);
}

.recent-card:focus-visible {
  outline: 2px solid var(--c-text);
  outline-offset: -2px;
}

.recent-card.active {
  border-color: var(--c-text);
  background: #ffffff;
  box-shadow: inset 3px 0 0 var(--c-text), 0 4px 12px -4px rgba(24, 24, 27, 0.07);
}

.recent-card strong {
  color: var(--c-text);
  font-size: 13.5px;
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1.5;
}

.recent-card span,
.recent-card small,
.preview-topline span,
.tab-copy {
  color: var(--c-text-tertiary);
  font-size: 12px;
}

.recent-card small {
  font-family: var(--font-ui);
  color: var(--c-text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.65;
}

.source-preview {
  padding: 16px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-control);
  background: #faf9f6;
  max-height: 320px;
  overflow-y: auto;
  font-size: 13px;
}

.result-shell {
  padding-top: 20px;
  border-top: 1px solid var(--c-border-soft);
  max-height: 600px;
  overflow-y: auto;
  font-family: var(--font-editorial);
  font-size: 15px;
}

.empty-list {
  margin: 0;
  padding: 20px 4px;
  color: var(--c-text-tertiary);
  font-size: 13px;
  line-height: 1.7;
}

.preview-topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.preview-topline strong {
  color: var(--c-text);
  font-size: 13px;
  font-weight: 600;
}

.model-settings {
  padding-top: 18px;
  border-top: 1px solid var(--c-border-soft);
}

.model-settings summary {
  color: var(--c-text-secondary);
  font-size: 13px;
  cursor: pointer;
}

.model-settings summary span {
  margin-left: 8px;
  color: var(--c-text-tertiary);
  font-size: 12px;
}

.model-settings[open] summary {
  margin-bottom: 20px;
}

.model-settings summary:focus-visible {
  outline: 2px solid var(--c-text);
  outline-offset: 4px;
}

.action-btn {
  display: flex;
  margin-top: 18px;
}

.tab-copy {
  font-family: var(--font-ui);
  color: var(--c-text-secondary);
  font-size: 13px;
  line-height: 1.55;
  margin: 0 0 12px;
}

.result-empty {
  display: grid;
  justify-items: center;
  align-content: center;
  min-height: 280px;
  padding: 32px 20px;
  border: 1px dashed var(--c-border-hover);
  border-radius: 12px;
  background: #faf9f6;
  text-align: center;
}

.result-icon {
  display: grid;
  place-items: center;
  width: 56px;
  height: 60px;
  margin-bottom: 18px;
  border: 1px solid var(--c-border);
  border-radius: 12px;
  color: var(--c-text);
  background: #ffffff;
  box-shadow: 0 6px 18px -4px rgba(24, 24, 27, 0.06);
  font-size: 24px;
}

.result-empty h3 {
  margin: 0;
  color: var(--c-text);
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: 650;
  line-height: 1.4;
}

.result-empty p {
  margin: 8px 0 0;
  color: var(--c-text-secondary);
  font-size: 13px;
  line-height: 1.7;
}

@media (max-width: 1100px) {
  .refine-page {
    padding: 28px 24px;
  }

  .refine-grid {
    grid-template-columns: minmax(250px, 280px) minmax(0, 1fr);
    gap: 18px;
  }

  .source-section,
  .action-section,
  .result-section {
    padding: 20px;
  }
}

@media (max-width: 800px) {
  .refine-page {
    padding: 24px 18px;
  }

  .refine-hero {
    align-items: flex-start;
    flex-direction: column;
  }

  .refine-grid {
    grid-template-columns: 1fr;
    grid-template-areas: 'source' 'action' 'result';
  }

  .recent-list {
    max-height: 240px;
  }

  .section-head {
    flex-wrap: wrap;
  }

  .result-empty h3 {
    font-size: 18px;
  }
}
</style>
