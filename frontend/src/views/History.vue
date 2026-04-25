<template>
  <div class="page history-page">
    <section class="history-hero">
      <div>
        <span class="hero-kicker">Content Library</span>
        <h1 class="page-title">历史内容</h1>
        <p class="page-subtitle">按状态和类型筛选内容，搜索关键词，并把已有内容直接送去打磨。</p>
      </div>
      <div class="hero-actions">
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </div>
    </section>

    <section class="section filter-section">
      <div class="filter-grid">
        <el-input v-model="query" placeholder="搜索标题或正文" />
        <el-select v-model="filters.content_type" clearable placeholder="内容类型">
          <el-option v-for="item in CONTENT_TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-select v-model="filters.status" clearable placeholder="状态">
          <el-option label="草稿" value="draft" />
          <el-option label="已打磨" value="refined" />
          <el-option label="已发布" value="published" />
          <el-option label="Agent 成稿" value="agent_final" />
        </el-select>
        <el-button type="primary" @click="load">筛选</el-button>
      </div>
    </section>

    <section class="results-grid">
      <div class="section list-section">
        <div class="section-head">
          <div>
            <span class="section-kicker">Library</span>
            <h2>内容列表</h2>
          </div>
          <span class="section-pill">{{ filteredItems.length }} 条</span>
        </div>

        <el-empty v-if="!filteredItems.length && !loading" description="暂无匹配内容" />
        <div v-else class="library-grid">
          <button
            v-for="item in filteredItems"
            :key="item.id"
            type="button"
            class="library-card"
            :aria-label="`查看内容 ${item.title || item.id}`"
            @click="open(item.id)"
          >
            <ContentCard :item="item" />
          </button>
        </div>
      </div>

      <div class="section detail-section">
        <div class="section-head">
          <div>
            <span class="section-kicker">Detail</span>
            <h2>{{ selected?.title || '内容详情' }}</h2>
          </div>
          <div class="detail-actions">
            <el-button :icon="Edit" :disabled="!selected" @click="goRefine">去打磨</el-button>
            <el-button :icon="DocumentCopy" :disabled="!selected?.content" @click="copyContent">复制</el-button>
          </div>
        </div>

        <el-empty v-if="!selected" description="点击左侧内容查看详情" />
        <div v-else class="detail-shell">
          <div class="detail-meta">
            <div class="meta-card">
              <span>类型</span>
              <strong>{{ getContentTypeLabel(selected.content_type) }}</strong>
            </div>
            <div class="meta-card">
              <span>风格</span>
              <strong>{{ getStyleLabel(selected.style) }}</strong>
            </div>
            <div class="meta-card">
              <span>状态</span>
              <strong>{{ getStatusLabel(selected.status) }}</strong>
            </div>
          </div>
          <div class="content-preview">{{ selected.content }}</div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus/es/components/message/index'
import { DocumentCopy, Edit, Refresh } from '@element-plus/icons-vue'
import ContentCard from '../components/ContentCard.vue'
import { getContent, getContents, type ContentItem } from '../api/content'
import { CONTENT_TYPE_OPTIONS, getContentTypeLabel, getStatusLabel, getStyleLabel } from '../constants/content'

const router = useRouter()

const filters = reactive({ content_type: '', status: '' })
const query = ref('')
const items = ref<ContentItem[]>([])
const loading = ref(false)
const selected = ref<ContentItem>()

const filteredItems = computed(() => {
  const term = query.value.trim().toLowerCase()
  if (!term) return items.value
  return items.value.filter(item => {
    return [item.title ?? '', item.content].join(' ').toLowerCase().includes(term)
  })
})

async function load() {
  loading.value = true
  try {
    items.value = await getContents({
      limit: 100,
      content_type: filters.content_type || undefined,
      status: filters.status || undefined
    })
    if (selected.value) {
      const stillExists = items.value.find(item => item.id === selected.value?.id)
      if (stillExists) {
        await open(stillExists.id)
      }
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function open(id: number) {
  selected.value = await getContent(id)
}

function goRefine() {
  if (!selected.value) return
  void router.push({ path: '/refine', query: { id: String(selected.value.id) } })
}

async function copyContent() {
  if (!selected.value?.content) return
  try {
    await navigator.clipboard.writeText(selected.value.content)
    ElMessage.success('已复制内容')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

onMounted(load)
</script>

<style scoped>
.history-page {
  display: grid;
  gap: 18px;
}

.history-hero {
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

.filter-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) repeat(2, minmax(180px, 220px)) auto;
  gap: 12px;
}

.results-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(360px, 0.8fr);
  gap: 16px;
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
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

.library-grid {
  display: grid;
  gap: 12px;
}

.library-card {
  padding: 0;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.detail-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.detail-shell {
  display: grid;
  gap: 16px;
}

.detail-meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.meta-card {
  padding: 12px;
  border: 1px solid rgba(24, 33, 38, 0.08);
  border-radius: 8px;
  background: rgba(248, 244, 237, 0.86);
}

.meta-card span {
  display: block;
  color: #738086;
  font-size: 12px;
}

.meta-card strong {
  display: block;
  margin-top: 6px;
  color: #182126;
  font-size: 14px;
}

@media (max-width: 1120px) {
  .history-hero {
    align-items: flex-start;
    flex-direction: column;
  }

  .filter-grid,
  .results-grid,
  .detail-meta {
    grid-template-columns: 1fr;
  }
}
</style>
