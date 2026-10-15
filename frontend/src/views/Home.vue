<template>
  <div class="page dashboard-page">
    <section class="dashboard-hero">
      <div>
        <h1 class="page-title">内容运营概览</h1>
        <p class="page-subtitle">每一份内容积累，都在这里。</p>
      </div>
      <div class="hero-actions">
        <el-button type="primary" :icon="EditPen" @click="$router.push('/')">打开工作台</el-button>
        <el-button :icon="Tickets" @click="$router.push('/history')">历史内容</el-button>
      </div>
    </section>

    <div class="summary-actions">
      <p v-if="statsError" class="load-error" role="alert">{{ statsError }}{{ stats ? '，当前显示上次加载的数据。' : '' }}</p>
      <p v-else-if="statsLoading" role="status">统计加载中…</p>
      <el-button :icon="Refresh" :loading="statsLoading" @click="loadStats">{{ statsError ? '重试统计' : '刷新统计' }}</el-button>
    </div>
    <section class="stats-row" :aria-busy="statsLoading">
      <article class="metric-card">
        <span>总内容</span>
        <strong>{{ stats?.total_contents ?? '—' }}</strong>
        <small>已进入内容库的记录总数</small>
      </article>
      <article class="metric-card">
        <span>内容类型</span>
        <strong>{{ stats ? Object.keys(stats.by_type).length : '—' }}</strong>
        <small>当前覆盖的平台和格式</small>
      </article>
      <article class="metric-card">
        <span>状态类型</span>
        <strong>{{ stats ? Object.keys(stats.by_status).length : '—' }}</strong>
        <small>草稿、打磨和发布阶段分布</small>
      </article>
      <article class="metric-card">
        <span>最近更新</span>
        <strong class="metric-date">{{ recentItems[0]?.created_at?.slice(0, 10) || (recentLoaded && !recentError ? '暂无' : '—') }}</strong>
        <small>最近一次进入内容库的日期</small>
      </article>
    </section>

    <section class="quick-row">
      <button class="quick-card" type="button" @click="$router.push('/')">
        <span class="quick-icon"><EditPen /></span>
        <div>
          <strong>内容工作台</strong>
          <span>策略、生成、审阅集中处理</span>
        </div>
        <ArrowRight class="quick-arrow" />
      </button>
      <button class="quick-card" type="button" @click="$router.push('/refine')">
        <span class="quick-icon"><MagicStick /></span>
        <div>
          <strong>打磨已有内容</strong>
          <span>改写、换风格、做 SEO</span>
        </div>
        <ArrowRight class="quick-arrow" />
      </button>
      <button class="quick-card" type="button" @click="$router.push('/chat')">
        <span class="quick-icon"><ChatDotRound /></span>
        <div>
          <strong>Agent 对话</strong>
          <span>做策略、选题和运营问答</span>
        </div>
        <ArrowRight class="quick-arrow" />
      </button>
    </section>

    <section class="section recent">
      <div class="page-header">
        <div>
          <h2 class="page-title">最近内容</h2>
          <p class="page-subtitle">接着上次的灵感，继续创作。</p>
        </div>
        <el-button :icon="Refresh" :loading="recentLoading" @click="loadRecent">{{ recentError ? '重试内容' : '刷新内容' }}</el-button>
      </div>

      <p v-if="recentError" class="load-error" role="alert">{{ recentError }}{{ recentLoaded ? '，当前显示上次加载的数据。' : '' }}</p>
      <p v-if="recentLoading && !recentLoaded" role="status">内容加载中…</p>
      <el-empty v-else-if="recentLoaded && !recentError && !recentItems.length" description="暂无内容" />
      <div v-else-if="recentItems.length" class="recent-list" :aria-busy="recentLoading">
        <ContentCard v-for="item in recentItems" :key="item.id" :item="item" />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElEmpty } from 'element-plus/es/components/empty/index'
import 'element-plus/es/components/empty/style/css'
import { ArrowRight, ChatDotRound, EditPen, MagicStick, Refresh, Tickets } from '@element-plus/icons-vue'
import ContentCard from '../components/ContentCard.vue'
import { getStats, type StatsPayload } from '../api/stats'
import { getContents, type ContentItem } from '../api/content'

const stats = ref<StatsPayload>()
const statsLoading = ref(false)
const statsError = ref('')
const recentItems = ref<ContentItem[]>([])
const recentLoaded = ref(false)
const recentLoading = ref(false)
const recentError = ref('')
let statsRequest = 0
let recentRequest = 0

async function loadStats() {
  const request = ++statsRequest
  statsLoading.value = true
  statsError.value = ''
  try {
    const loaded = await getStats()
    if (request === statsRequest) stats.value = loaded
  } catch (error) {
    if (request === statsRequest) statsError.value = `统计加载失败：${error instanceof Error ? error.message : '请稍后重试'}`
  } finally {
    if (request === statsRequest) statsLoading.value = false
  }
}

async function loadRecent() {
  const request = ++recentRequest
  recentLoading.value = true
  recentError.value = ''
  try {
    const loaded = await getContents({ limit: 6 })
    if (request !== recentRequest) return
    recentItems.value = loaded
    recentLoaded.value = true
  } catch (error) {
    if (request === recentRequest) recentError.value = `内容加载失败：${error instanceof Error ? error.message : '请稍后重试'}`
  } finally {
    if (request === recentRequest) recentLoading.value = false
  }
}

onMounted(() => { void Promise.all([loadStats(), loadRecent()]) })
onBeforeUnmount(() => { statsRequest += 1; recentRequest += 1 })
</script>

<style scoped>
.dashboard-page { display: grid; gap: 24px; }
.summary-actions { display: flex; align-items: center; justify-content: flex-end; gap: 16px; color: var(--c-text-secondary); font-size: 13px; }
.summary-actions p { margin: 0 auto 0 0; }
.load-error { color: var(--c-fail); font-size: 13px; }
.dashboard-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  padding: 4px 0 22px;
  border-bottom: 1px solid var(--c-border);
}
.dashboard-hero .page-title {
  color: var(--c-text);
  font-family: var(--font-display);
  font-size: clamp(23px, 2.1vw, 29px);
  font-weight: 700;
  letter-spacing: -0.025em;
}
.dashboard-hero .page-subtitle {
  margin-top: 6px;
  color: var(--c-text-secondary);
  font-size: 13.5px;
}
.hero-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.hero-actions :deep(.el-button + .el-button) { margin-left: 0; }
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  padding: 24px 8px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-card);
  background: var(--c-surface);
  box-shadow: var(--shadow-panel);
}
.metric-card { position: relative; min-width: 0; padding: 4px 24px; }
.metric-card + .metric-card { border-left: 1px solid var(--c-border-soft); }
.metric-card > span { display: block; color: var(--c-text-secondary); font-size: 12px; font-weight: 600; }
.metric-card strong {
  display: block;
  margin: 8px 0 4px;
  color: var(--c-text);
  font: 700 30px/1.25 var(--font-display);
  letter-spacing: -0.035em;
  font-variant-numeric: tabular-nums;
}
.metric-card strong.metric-date { font-size: clamp(18px, 1.8vw, 22px); letter-spacing: -0.02em; line-height: 1.56; }
.metric-card small { color: var(--c-text-tertiary); font-size: 11.5px; line-height: 1.5; }
.quick-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.quick-card {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
  padding: 20px 22px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-card);
  background: var(--c-surface);
  box-shadow: var(--shadow-panel);
  text-align: left;
  cursor: pointer;
  transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
}
.quick-card:hover {
  transform: translateY(-2px);
  border-color: var(--c-border-hover);
  box-shadow: var(--shadow-hover);
}
.quick-card:focus-visible { outline: 2px solid var(--c-text); outline-offset: 3px; }
.quick-icon {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  border: 1px solid var(--c-border);
  border-radius: 10px;
  color: var(--c-text);
  background: #faf9f6;
  transition: background-color 160ms ease, color 160ms ease, border-color 160ms ease;
}
.quick-card:hover .quick-icon {
  background: var(--c-text);
  border-color: var(--c-text);
  color: #faf9f5;
}
.quick-icon svg { width: 19px; height: 19px; }
.quick-card div { min-width: 0; }
.quick-card strong { display: block; margin-bottom: 4px; color: var(--c-text); font-size: 14.5px; font-weight: 650; }
.quick-card div > span { display: block; color: var(--c-text-secondary); font-size: 12.5px; line-height: 1.5; }
.quick-arrow { width: 16px; height: 16px; flex-shrink: 0; margin-left: auto; color: var(--c-text-tertiary); transition: transform 160ms ease, color 160ms ease; }
.quick-card:hover .quick-arrow { transform: translateX(3px); color: var(--c-text); }
.recent { min-width: 0; padding: 26px; border: 1px solid var(--c-border); border-radius: var(--r-card); background: var(--c-surface); box-shadow: var(--shadow-panel); }
.recent .page-header { margin-bottom: 22px; }
.recent .page-title { font-size: 16.5px; font-weight: 650; }
.recent .page-subtitle { margin-top: 5px; color: var(--c-text-tertiary); font-size: 12.5px; }
.recent-list { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
@media (max-width: 1180px) {
  .quick-card { padding: 18px; gap: 10px; }
  .quick-arrow { display: none; }
  .recent-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .metric-card { padding: 0 18px; }
}
@media (max-width: 900px) {
  .dashboard-hero { align-items: flex-start; flex-direction: column; gap: 16px; padding: 4px 0 18px; }
  .quick-row { grid-template-columns: 1fr; }
  .quick-arrow { display: block; }
  .stats-row { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px 0; padding: 20px 0; }
  .metric-card:nth-child(3) { border-left: 0; }
}
@media (max-width: 600px) {
  .dashboard-page { gap: 20px; }
  .metric-card strong { font-size: 26px; }
  .metric-card strong.metric-date { font-size: 18px; line-height: 1.85; }
  .recent { padding: 18px; }
  .recent-list { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) {
  .quick-card, .quick-arrow, .quick-icon { transition: none; }
}
</style>
