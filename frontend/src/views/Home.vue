<template>
  <div class="page dashboard-page">
    <section class="dashboard-hero">
      <div>
        <span class="hero-kicker">Operations Snapshot</span>
        <h1 class="page-title">内容运营概览</h1>
        <p class="page-subtitle">查看内容资产、工作流入口和近期产出，把日常动作压缩到一个总览页。</p>
      </div>
      <div class="hero-actions">
        <el-button type="primary" :icon="EditPen" @click="$router.push('/')">打开工作台</el-button>
        <el-button :icon="Tickets" @click="$router.push('/history')">历史内容</el-button>
      </div>
    </section>

    <section class="stats-row">
      <article class="metric-card">
        <span>总内容</span>
        <strong>{{ stats?.total_contents ?? 0 }}</strong>
        <small>已进入内容库的记录总数</small>
      </article>
      <article class="metric-card">
        <span>内容类型</span>
        <strong>{{ Object.keys(stats?.by_type ?? {}).length }}</strong>
        <small>当前覆盖的平台和格式</small>
      </article>
      <article class="metric-card">
        <span>状态类型</span>
        <strong>{{ Object.keys(stats?.by_status ?? {}).length }}</strong>
        <small>草稿、打磨和发布阶段分布</small>
      </article>
      <article class="metric-card">
        <span>最近更新</span>
        <strong>{{ content.items[0]?.created_at?.slice(0, 10) || '-' }}</strong>
        <small>最近一次进入内容库的日期</small>
      </article>
    </section>

    <section class="quick-row">
      <button class="quick-card" type="button" @click="$router.push('/')">
        <strong>内容工作台</strong>
        <span>策略、生成、审阅集中处理</span>
      </button>
      <button class="quick-card" type="button" @click="$router.push('/refine')">
        <strong>打磨已有内容</strong>
        <span>改写、换风格、做 SEO</span>
      </button>
      <button class="quick-card" type="button" @click="$router.push('/chat')">
        <strong>Agent 对话</strong>
        <span>做策略、选题和运营问答</span>
      </button>
    </section>

    <section class="section recent">
      <div class="page-header">
        <div>
          <h2 class="page-title">最近内容</h2>
          <p class="page-subtitle">最近生成或打磨过的内容，点击历史页查看详情。</p>
        </div>
        <el-button :icon="Refresh" :loading="content.loading" @click="load">刷新</el-button>
      </div>

      <el-empty v-if="!content.items.length" description="暂无内容" />
      <div v-else class="recent-list">
        <ContentCard v-for="item in content.items" :key="item.id" :item="item" />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { EditPen, Refresh, Tickets } from '@element-plus/icons-vue'
import ContentCard from '../components/ContentCard.vue'
import { getStats, type StatsPayload } from '../api/stats'
import { useContentStore } from '../stores/content'

const content = useContentStore()
const stats = ref<StatsPayload>()

async function load() {
  await Promise.all([
    content.refresh(6),
    getStats().then(result => {
      stats.value = result
    })
  ])
}

onMounted(load)
</script>

<style scoped>
.dashboard-page {
  display: grid;
  gap: 24px;
  padding: 24px 32px;
  background: var(--c-bg);
}

.dashboard-hero,
.stats-row,
.quick-row {
  max-width: 1280px;
}

.dashboard-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.hero-kicker {
  display: inline-block;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.dashboard-hero .page-title {
  margin-top: 6px;
  font-size: 32px;
  font-weight: 600;
  letter-spacing: -0.025em;
  line-height: 1.15;
}

.dashboard-hero .page-subtitle {
  margin-top: 6px;
  color: var(--c-text-secondary);
  font-size: 14px;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.stats-row,
.quick-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.metric-card,
.quick-card {
  padding: 16px 20px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg);
  box-shadow: none;
  backdrop-filter: none;
  transition: border-color 100ms ease;
}

.quick-card:hover {
  border-color: var(--c-border-strong);
}

.metric-card span,
.quick-card span {
  display: block;
  color: var(--c-text-tertiary);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  line-height: 1.4;
}

.metric-card strong,
.quick-card strong {
  display: block;
  margin: 8px 0 4px;
  color: var(--c-text);
  font-weight: 600;
  letter-spacing: -0.02em;
}

.metric-card strong {
  font-size: 28px;
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
}

.metric-card small {
  color: var(--c-text-tertiary);
  font-size: 12px;
}

.quick-card {
  text-align: left;
  cursor: pointer;
}

.quick-card strong {
  font-size: 14.5px;
}

.quick-card span {
  font-size: 12.5px;
  text-transform: none;
  letter-spacing: -0.005em;
  color: var(--c-text-secondary);
  font-weight: 400;
}

.recent {
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg);
  padding: 24px;
}

.recent .page-title {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -0.015em;
}

.recent .page-subtitle {
  font-size: 13px;
  color: var(--c-text-secondary);
}

.recent-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
}

@media (max-width: 960px) {
  .dashboard-page {
    padding: 16px;
  }

  .dashboard-hero {
    align-items: flex-start;
    flex-direction: column;
  }

  .stats-row,
  .quick-row {
    grid-template-columns: 1fr;
  }
}
</style>
