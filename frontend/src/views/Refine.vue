<template>
  <div class="page refine-page">
    <section class="refine-hero">
      <div>
        <span class="hero-kicker">内容打磨</span>
        <h1 class="page-title">内容打磨</h1>
        <p class="page-subtitle">从内容库中选择现有内容，直接改写、换风格、做标题优化或 SEO 分析。</p>
      </div>
      <div class="hero-actions">
        <el-button :icon="Refresh" :loading="loadingList" @click="loadRecent">刷新内容库</el-button>
      </div>
    </section>

    <div class="refine-grid">
      <section class="section source-section">
        <div class="section-head">
          <div>
            <span class="section-kicker">来源</span>
            <h2>选择内容</h2>
          </div>
          <span class="section-pill">{{ source ? `#${source.id}` : '未选择' }}</span>
        </div>

        <div class="manual-loader">
          <el-input-number v-model="contentId" :min="1" />
          <el-button :icon="Search" @click="loadContent">加载</el-button>
        </div>

        <div class="recent-list">
          <button
            v-for="item in recentItems"
            :key="item.id"
            type="button"
            class="recent-card"
            :class="{ active: source?.id === item.id }"
            @click="selectContent(item.id)"
          >
            <strong>{{ item.title || '未命名内容' }}</strong>
            <span>{{ getContentTypeLabel(item.content_type) }} · {{ getStatusLabel(item.status) }}</span>
            <small>{{ item.content }}</small>
          </button>
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
            <span class="section-kicker">操作</span>
            <h2>打磨方式</h2>
          </div>
        </div>

        <ModelSelector
          :model-value="modelConfig"
          @update:model-value="Object.assign(modelConfig, $event)"
        />
        <div class="section-divider"></div>

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
            <el-segmented v-model="newStyle" :options="styleSegmentOptions" />
            <el-button type="primary" :loading="loading" class="action-btn" @click="switchStyle">切换风格</el-button>
          </el-tab-pane>

          <el-tab-pane label="标题优化" name="titles">
            <el-slider v-model="titleCount" :min="3" :max="10" show-input />
            <el-button type="primary" :loading="loading" class="action-btn" @click="titles">生成标题</el-button>
          </el-tab-pane>

          <el-tab-pane label="SEO" name="seo">
            <p class="tab-copy">获取关键词建议、标题优化方向、结构建议和 meta 描述。</p>
            <el-button type="primary" :loading="loading" @click="seo">分析 SEO</el-button>
          </el-tab-pane>
        </el-tabs>
      </section>

      <section class="section result-section">
        <div class="section-head">
          <div>
            <span class="section-kicker">结果</span>
            <h2>输出结果</h2>
          </div>
          <div class="hero-actions">
            <span v-if="currentJob" class="section-pill">{{ jobState }}</span>
            <el-button :icon="DocumentCopy" :disabled="!resultText" @click="copyResult">复制</el-button>
          </div>
        </div>

        <el-empty v-if="!resultText && !loading" description="操作结果会显示在这里" />
        <el-skeleton v-else-if="loading" :rows="10" animated />
        <div v-else class="result-shell">
          <div class="content-preview">{{ resultText }}</div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElEmpty } from 'element-plus/es/components/empty/index'
import { ElInputNumber } from 'element-plus/es/components/input-number/index'
import { ElMessage } from 'element-plus/es/components/message/index'
import { ElSegmented } from 'element-plus/es/components/segmented/index'
import { ElSkeleton } from 'element-plus/es/components/skeleton/index'
import { ElSlider } from 'element-plus/es/components/slider/index'
import { ElTabPane, ElTabs } from 'element-plus/es/components/tabs/index'
import 'element-plus/es/components/empty/style/css'
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
const currentJob = ref<JobResponse>()

const jobState = computed(() => {
  if (!currentJob.value) return ''
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
  } finally {
    loadingList.value = false
  }
}

async function loadContent() {
  try {
    source.value = await getContent(contentId.value)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function selectContent(id: number) {
  contentId.value = id
  await loadContent()
}

async function run(task: () => Promise<string>) {
  if (!source.value) {
    ElMessage.warning('请先选择内容')
    return
  }
  loading.value = true
  currentJob.value = undefined
  try {
    resultText.value = await task()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function rewrite() {
  run(async () => {
    const job = await createRefineJob({
      content_id: contentId.value,
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
  run(async () => {
    const job = await createRefineJob({
      content_id: contentId.value,
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
  run(async () => {
    const job = await createTitlesJob({
      content_id: contentId.value,
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
  run(async () => {
    const job = await createSeoJob({
      content_id: contentId.value,
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
  if (Number.isFinite(routeId) && routeId > 0) {
    contentId.value = routeId
    await loadContent()
  }
})
</script>

<style scoped>
.refine-page {
  display: grid;
  gap: 20px;
  padding: 24px 32px;
  background: var(--c-bg);
}

.refine-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.hero-kicker,
.section-kicker {
  display: inline-block;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.refine-hero .page-title {
  margin-top: 6px;
  font-size: var(--fs-h1);
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1.15;
}

.refine-hero .page-subtitle {
  color: var(--c-text-secondary);
  font-size: 14px;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.refine-grid {
  display: grid;
  grid-template-columns: minmax(280px, 360px) minmax(320px, 420px) minmax(0, 1fr);
  gap: 16px;
}

.source-section,
.action-section,
.result-section {
  display: grid;
  align-content: start;
  gap: 14px;
  padding: 20px;
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.section-head h2 {
  margin: 4px 0 0;
  color: var(--c-text);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0;
}

.section-pill {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border: 1px solid var(--c-border);
  border-radius: 999px;
  color: var(--c-text-secondary);
  background: var(--c-surface);
  font-size: 11px;
  font-family: var(--font-mono);
  letter-spacing: 0;
}

.manual-loader {
  display: flex;
  align-items: center;
  gap: 8px;
}

.recent-list {
  display: grid;
  gap: 8px;
  max-height: 360px;
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
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  color: var(--c-text);
  background: var(--c-surface);
  text-align: left;
  cursor: pointer;
  transition: border-color 100ms ease, background-color 100ms ease;
}

.recent-card:hover {
  border-color: var(--c-border-strong);
}

.recent-card.active {
  border-color: var(--c-accent);
  background: var(--c-accent-soft);
}

.recent-card strong {
  color: var(--c-text);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0;
}

.recent-card span,
.recent-card small,
.preview-topline span,
.tab-copy {
  color: var(--c-text-tertiary);
  font-size: 11.5px;
  font-family: var(--font-mono);
}

.recent-card small {
  font-family: var(--font-ui);
  color: var(--c-text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.source-preview,
.result-shell {
  padding: 14px;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  background: var(--c-bg-soft);
  max-height: 320px;
  overflow-y: auto;
}

.preview-topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.preview-topline strong {
  color: var(--c-text);
  font-size: 13px;
  font-weight: 600;
}

.section-divider {
  height: 1px;
  background: var(--c-border);
}

.action-btn {
  margin-top: 12px;
}

.tab-copy {
  font-family: var(--font-ui);
  color: var(--c-text-secondary);
  font-size: 13px;
  line-height: 1.55;
  margin: 0 0 12px;
}

@media (max-width: 1120px) {
  .refine-page {
    padding: 16px;
  }

  .refine-hero {
    align-items: flex-start;
    flex-direction: column;
  }

  .refine-grid {
    grid-template-columns: 1fr;
  }
}
</style>
