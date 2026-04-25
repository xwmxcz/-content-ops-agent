<template>
  <div class="page refine-page">
    <section class="refine-hero">
      <div>
        <span class="hero-kicker">Refine Workspace</span>
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
            <span class="section-kicker">Source</span>
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
            <span class="section-kicker">Action</span>
            <h2>打磨方式</h2>
          </div>
        </div>

        <ModelSelector v-model="modelConfig" />
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
            <el-segmented v-model="newStyle" :options="STYLE_OPTIONS" />
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
            <span class="section-kicker">Result</span>
            <h2>输出结果</h2>
          </div>
          <el-button :icon="DocumentCopy" :disabled="!resultText" @click="copyResult">复制</el-button>
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
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus/es/components/message/index'
import { DocumentCopy, Refresh, Search } from '@element-plus/icons-vue'
import ModelSelector from '../components/ModelSelector.vue'
import { analyzeSeo, generateTitles, getContent, getContents, refineContent, type ContentItem } from '../api/content'
import { STYLE_OPTIONS, getContentTypeLabel, getStatusLabel, getStyleLabel } from '../constants/content'

const route = useRoute()

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
    const result = await refineContent({
      content_id: contentId.value,
      instruction: instruction.value,
      provider: modelConfig.provider,
      model: modelConfig.model,
      temperature: modelConfig.temperature,
      max_tokens: modelConfig.max_tokens
    })
    return result.content
  })
}

function switchStyle() {
  run(async () => {
    const result = await refineContent({
      content_id: contentId.value,
      new_style: newStyle.value,
      provider: modelConfig.provider,
      model: modelConfig.model,
      temperature: modelConfig.temperature,
      max_tokens: modelConfig.max_tokens
    })
    return result.content
  })
}

function titles() {
  run(() =>
    generateTitles({
      content_id: contentId.value,
      count: titleCount.value,
      provider: modelConfig.provider,
      model: modelConfig.model
    })
  )
}

function seo() {
  run(() =>
    analyzeSeo({
      content_id: contentId.value,
      provider: modelConfig.provider,
      model: modelConfig.model
    })
  )
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
  gap: 18px;
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
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.section-head h2 {
  margin: 5px 0 0;
  color: #182126;
  font-size: 20px;
}

.section-pill {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  color: #0f5f55;
  background: rgba(15, 133, 116, 0.1);
  font-size: 12px;
}

.manual-loader {
  display: flex;
  align-items: center;
  gap: 10px;
}

.recent-list {
  display: grid;
  gap: 10px;
}

.recent-card {
  display: grid;
  gap: 6px;
  padding: 12px;
  border: 1px solid rgba(24, 33, 38, 0.08);
  border-radius: 8px;
  color: #243239;
  background: rgba(255, 255, 255, 0.78);
  text-align: left;
  cursor: pointer;
}

.recent-card.active {
  border-color: rgba(15, 133, 116, 0.22);
  background: rgba(15, 133, 116, 0.06);
}

.recent-card span,
.recent-card small,
.preview-topline span,
.tab-copy {
  color: #6d787e;
}

.source-preview,
.result-shell {
  padding: 14px;
  border: 1px solid rgba(24, 33, 38, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.88);
}

.preview-topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.section-divider {
  height: 1px;
  background: linear-gradient(90deg, rgba(24, 33, 38, 0.06), rgba(24, 33, 38, 0.16), rgba(24, 33, 38, 0.06));
}

.action-btn {
  margin-top: 14px;
}

.tab-copy {
  line-height: 1.6;
}

@media (max-width: 1120px) {
  .refine-hero {
    align-items: flex-start;
    flex-direction: column;
  }

  .refine-grid {
    grid-template-columns: 1fr;
  }
}
</style>
