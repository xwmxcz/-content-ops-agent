<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1 class="page-title">统计分析</h1>
        <p class="page-subtitle">查看内容类型和状态分布。</p>
      </div>
      <el-button :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <div class="grid-3">
      <div class="metric">
        <span class="muted">总内容</span>
        <strong>{{ stats?.total_contents ?? 0 }}</strong>
      </div>
      <div class="metric">
        <span class="muted">类型</span>
        <strong>{{ Object.keys(stats?.by_type ?? {}).length }}</strong>
      </div>
      <div class="metric">
        <span class="muted">状态</span>
        <strong>{{ Object.keys(stats?.by_status ?? {}).length }}</strong>
      </div>
    </div>

    <div class="grid-2 chart-grid">
      <section class="section">
        <h2>内容类型</h2>
        <v-chart class="chart" :option="typeOption" autoresize />
      </section>
      <section class="section">
        <h2>内容状态</h2>
        <v-chart class="chart" :option="statusOption" autoresize />
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { use } from 'echarts/core'
import { BarChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import { Refresh } from '@element-plus/icons-vue'
import { getStats, type StatsPayload } from '../api/stats'

use([BarChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const stats = ref<StatsPayload>()

const typeOption = computed(() => ({
  tooltip: {},
  legend: { bottom: 0 },
  series: [
    {
      type: 'pie',
      radius: '62%',
      data: Object.entries(stats.value?.by_type ?? {}).map(([name, value]) => ({ name, value }))
    }
  ]
}))

const statusOption = computed(() => ({
  tooltip: {},
  xAxis: { type: 'category', data: Object.keys(stats.value?.by_status ?? {}) },
  yAxis: { type: 'value' },
  series: [{ type: 'bar', data: Object.values(stats.value?.by_status ?? {}), itemStyle: { color: '#c7892f' } }]
}))

async function load() {
  stats.value = await getStats()
}

onMounted(load)
</script>

<style scoped>
.chart-grid {
  margin-top: 18px;
}

.chart {
  height: 360px;
}
</style>
