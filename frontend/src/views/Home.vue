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
  gap: 18px;
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
  flex-wrap: wrap;
}

.stats-row,
.quick-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.metric-card,
.quick-card {
  padding: 16px;
  border: 1px solid rgba(24, 33, 38, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 18px 50px rgba(21, 31, 39, 0.08);
  backdrop-filter: blur(14px);
}

.metric-card span,
.quick-card span {
  display: block;
  color: #69757a;
  font-size: 13px;
  line-height: 1.5;
}

.metric-card strong,
.quick-card strong {
  display: block;
  margin: 8px 0 6px;
  color: #182126;
}

.metric-card strong {
  font-size: 28px;
}

.metric-card small {
  color: #7a8489;
}

.quick-card {
  text-align: left;
  cursor: pointer;
}

.quick-card strong {
  font-size: 16px;
}

.recent-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 14px;
}

@media (max-width: 960px) {
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
