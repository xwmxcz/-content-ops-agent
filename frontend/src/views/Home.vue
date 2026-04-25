<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1 class="page-title">工作台</h1>
        <p class="page-subtitle">集中查看内容资产、发布计划和生成入口。</p>
      </div>
      <el-button type="primary" :icon="EditPen" @click="$router.push('/generate')">生成内容</el-button>
    </div>

    <div class="grid-3">
      <div class="metric">
        <span class="muted">总内容</span>
        <strong>{{ stats?.total_contents ?? '-' }}</strong>
      </div>
      <div class="metric">
        <span class="muted">内容类型</span>
        <strong>{{ Object.keys(stats?.by_type ?? {}).length }}</strong>
      </div>
      <div class="metric">
        <span class="muted">状态数量</span>
        <strong>{{ Object.keys(stats?.by_status ?? {}).length }}</strong>
      </div>
    </div>

    <div class="section recent">
      <div class="page-header">
        <div>
          <h2 class="page-title">最近内容</h2>
          <p class="page-subtitle">最新生成或打磨的内容记录。</p>
        </div>
        <el-button :icon="Tickets" @click="$router.push('/history')">查看全部</el-button>
      </div>
      <el-empty v-if="!content.items.length" description="暂无内容" />
      <div v-else class="recent-list">
        <ContentCard v-for="item in content.items" :key="item.id" :item="item" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { EditPen, Tickets } from '@element-plus/icons-vue'
import ContentCard from '../components/ContentCard.vue'
import { getStats, type StatsPayload } from '../api/stats'
import { useContentStore } from '../stores/content'

const content = useContentStore()
const stats = ref<StatsPayload>()

onMounted(async () => {
  await Promise.all([
    content.refresh(6),
    getStats().then(result => {
      stats.value = result
    })
  ])
})
</script>

<style scoped>
.recent {
  margin-top: 18px;
}

.recent-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 14px;
}
</style>
