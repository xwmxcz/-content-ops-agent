<template>
  <div class="page stats-page">
    <section class="stats-hero">
      <div class="stats-heading">
        <h1 class="page-title">统计分析</h1>
        <p class="page-subtitle">看清内容积累，找到下一步的创作方向。</p>
      </div>
      <div class="hero-actions">
        <span class="sync-note">数据来自内容库实时统计</span>
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </div>
    </section>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <section class="summary-grid" aria-label="统计摘要">
      <article v-for="card in summaryCards" :key="card.label" class="summary-card">
        <div class="summary-top">
          <span>{{ card.label }}</span>
          <component :is="card.icon" />
        </div>
        <strong>{{ card.value }}</strong>
        <small>{{ card.caption }}</small>
      </article>
    </section>

    <section class="analytics-grid">
      <article class="analysis-panel type-panel">
        <header class="panel-header">
          <div>
            <h2>内容类型分布</h2>
            <p>各平台与内容格式的积累</p>
          </div>
          <div class="panel-stat">
            <strong>{{ dominantType?.percentLabel ?? '-' }}</strong>
            <span>{{ dominantType ? `${dominantType.label} 占比` : '暂无主类型' }}</span>
          </div>
        </header>

        <div v-if="hasTypeData" class="type-body">
          <div class="chart-frame donut-frame">
            <v-chart class="chart donut-chart" :option="typeOption" autoresize />
          </div>
          <div class="distribution-list">
            <div v-for="row in typeRows" :key="row.key" class="distribution-row">
              <div class="distribution-head">
                <span>
                  <i :style="{ background: row.color }" />
                  {{ row.label }}
                </span>
                <strong>{{ row.value }} 篇</strong>
              </div>
              <div class="distribution-meter" aria-hidden="true">
                <span :style="{ width: row.percentLabel, background: row.color }" />
              </div>
              <small>{{ row.percentLabel }}</small>
            </div>
          </div>
        </div>
        <el-empty v-else class="empty-state" description="暂无内容类型数据" />
      </article>

      <article class="analysis-panel status-panel">
        <header class="panel-header">
          <div>
            <h2>内容状态分布</h2>
            <p>从草稿到发布，了解内容进展</p>
          </div>
          <div class="panel-stat">
            <strong>{{ dominantStatus?.value ?? 0 }}</strong>
            <span>{{ dominantStatus ? dominantStatus.label : '暂无状态' }}</span>
          </div>
        </header>

        <div v-if="hasStatusData" class="status-body">
          <div class="chart-frame bar-frame">
            <v-chart class="chart status-chart" :option="statusOption" autoresize />
          </div>
          <div class="status-list">
            <div v-for="row in statusRows" :key="row.key" class="status-item">
              <div>
                <strong>{{ row.label }}</strong>
                <span>{{ row.percentLabel }} / {{ row.value }} 篇</span>
              </div>
              <div class="status-meter" aria-hidden="true">
                <span :style="{ width: row.percentLabel, background: row.color }" />
              </div>
            </div>
          </div>
        </div>
        <el-empty v-else class="empty-state" description="暂无内容状态数据" />
      </article>
    </section>

    <section class="insight-band">
      <div>
        <h2>内容小结</h2>
      </div>
      <div class="insight-grid">
        <article>
          <span>覆盖类型</span>
          <strong>{{ typeRows.length }}</strong>
          <small>{{ typeRows.length > 1 ? '内容格式较分散' : '当前主要集中在单一内容格式' }}</small>
        </article>
        <article>
          <span>最大类型</span>
          <strong>{{ dominantType?.label ?? '-' }}</strong>
          <small>{{ dominantType ? `${dominantType.value} 篇，${dominantType.percentLabel}` : '暂无可分析数据' }}</small>
        </article>
        <article>
          <span>主要状态</span>
          <strong>{{ dominantStatus?.label ?? '-' }}</strong>
          <small>{{ dominantStatus ? `${dominantStatus.value} 篇，${dominantStatus.percentLabel}` : '暂无可分析数据' }}</small>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { use } from 'echarts/core'
import { BarChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import { CollectionTag, DataAnalysis, Finished, PieChart as PieIcon, Refresh } from '@element-plus/icons-vue'
import { ElEmpty } from 'element-plus/es/components/empty/index'
import 'element-plus/es/components/empty/style/css'
import { getStats, type StatsPayload } from '../api/stats'

use([BarChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

type Row = {
  key: string
  label: string
  value: number
  percent: number
  percentLabel: string
  color: string
}

const theme = getComputedStyle(document.documentElement)
const themeColor = (token: string) => theme.getPropertyValue(token).trim()
const palette = Array.from({ length: 6 }, (_, index) => themeColor(`--c-chart-${index + 1}`))

const typeLabels: Record<string, string> = {
  blog: '博客',
  wechat: '公众号',
  xiaohongshu: '小红书',
  short_video: '短视频',
  twitter: '社媒短帖',
  linkedin: 'LinkedIn',
}

const statusLabels: Record<string, string> = {
  draft: '草稿',
  refined: '已打磨',
  agent_final: 'Agent 完稿',
  published: '已发布',
  scheduled: '已排期',
}

const stats = ref<StatsPayload>()
const loading = ref(false)
const error = ref('')

const totalContents = computed(() => stats.value?.total_contents ?? 0)
const typeRows = computed(() => buildRows(stats.value?.by_type ?? {}, typeLabels))
const statusRows = computed(() => buildRows(stats.value?.by_status ?? {}, statusLabels, 2))
const hasTypeData = computed(() => typeRows.value.length > 0)
const hasStatusData = computed(() => statusRows.value.length > 0)
const dominantType = computed(() => typeRows.value[0])
const dominantStatus = computed(() => statusRows.value[0])

const summaryCards = computed(() => [
  {
    label: '总内容',
    value: formatNumber(totalContents.value),
    caption: '内容库资产总量',
    icon: DataAnalysis,
  },
  {
    label: '内容类型',
    value: formatNumber(typeRows.value.length),
    caption: '当前覆盖的平台和格式',
    icon: CollectionTag,
  },
  {
    label: '生产状态',
    value: formatNumber(statusRows.value.length),
    caption: '内容所处流程阶段',
    icon: Finished,
  },
  {
    label: '主类型占比',
    value: dominantType.value?.percentLabel ?? '0%',
    caption: dominantType.value ? dominantType.value.label : '暂无主类型',
    icon: PieIcon,
  },
])

const typeOption = computed(() => ({
  color: palette,
  tooltip: {
    trigger: 'item',
    formatter: '{b}<br/>{c} 篇 ({d}%)',
  },
  legend: {
    show: false,
  },
  series: [
    {
      name: '内容类型',
      type: 'pie',
      radius: ['58%', '78%'],
      center: ['50%', '52%'],
      avoidLabelOverlap: true,
      itemStyle: {
        borderColor: themeColor('--c-surface'),
        borderWidth: 3,
      },
      label: {
        color: themeColor('--c-text-secondary'),
        formatter: '{b}\n{d}%',
        lineHeight: 18,
      },
      labelLine: {
        length: 12,
        length2: 8,
        lineStyle: {
          color: themeColor('--c-border-strong'),
        },
      },
      data: typeRows.value.map(row => ({
        name: row.label,
        value: row.value,
      })),
    },
  ],
}))

const statusOption = computed(() => ({
  color: statusRows.value.map(row => row.color),
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
    formatter: (params: Array<{ name: string; value: number }>) => {
      const item = params[0]
      return `${item.name}<br/>${item.value} 篇`
    },
  },
  grid: {
    top: 24,
    right: 18,
    bottom: 42,
    left: 42,
  },
  xAxis: {
    type: 'category',
    data: statusRows.value.map(row => row.label),
    axisTick: { show: false },
    axisLine: { lineStyle: { color: themeColor('--c-border') } },
    axisLabel: {
      color: themeColor('--c-text-tertiary'),
      interval: 0,
      margin: 12,
      formatter: (value: string) => (value.length > 6 ? `${value.slice(0, 6)}...` : value),
    },
  },
  yAxis: {
    type: 'value',
    minInterval: 1,
    splitLine: { lineStyle: { color: themeColor('--c-border-soft'), type: 'dashed' } },
    axisLabel: { color: themeColor('--c-text-tertiary') },
  },
  series: [
    {
      name: '状态数量',
      type: 'bar',
      data: statusRows.value.map(row => ({
        value: row.value,
        itemStyle: { color: row.color },
      })),
      barMaxWidth: 48,
      itemStyle: {
        borderRadius: [6, 6, 0, 0],
      },
      label: {
        show: true,
        position: 'top',
        color: themeColor('--c-text'),
        fontWeight: 600,
      },
    },
  ],
}))

async function load() {
  loading.value = true
  error.value = ''
  try {
    stats.value = await getStats()
  } catch {
    error.value = '统计数据加载失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}

function buildRows(source: Record<string, number>, labels: Record<string, string>, offset = 0): Row[] {
  const entries = Object.entries(source)
    .map(([key, value]) => [key, Number(value) || 0] as const)
    .filter(([, value]) => value > 0)
    .sort((a, b) => b[1] - a[1])
  const total = entries.reduce((sum, [, value]) => sum + value, 0)

  return entries.map(([key, value], index) => {
    const percent = total > 0 ? Math.round((value / total) * 100) : 0
    return {
      key,
      label: labels[key] ?? key,
      value,
      percent,
      percentLabel: `${percent}%`,
      color: palette[(index + offset) % palette.length],
    }
  })
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value)
}

onMounted(load)
</script>

<style scoped>
.stats-page { display: grid; gap: 24px; }
.stats-hero { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-bottom: 4px; }
.stats-heading { min-width: 0; }
.stats-heading .page-title { font-family: var(--font-display); letter-spacing: -0.035em; }
.hero-actions { display: flex; align-items: center; justify-content: flex-end; gap: 12px; flex-wrap: wrap; }
.sync-note { color: var(--c-text-tertiary); font-size: 11px; }
.error-banner { padding: 12px 16px; border: 1px solid var(--c-fail); border-radius: var(--r-control); color: var(--c-fail); background: var(--c-fail-soft); font-size: 13px; }
.summary-grid,
.analysis-panel,
.insight-band { border: 1px solid var(--c-border); border-radius: var(--r-card); background: var(--c-surface); }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); padding: 24px 6px; }
.summary-card { display: grid; align-content: start; gap: 8px; min-width: 0; padding: 0 24px; }
.summary-card + .summary-card { border-left: 1px solid var(--c-border-soft); }
.summary-top { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.summary-top span { color: var(--c-text-secondary); font-size: 12px; }
.summary-top svg { width: 16px; height: 16px; color: var(--c-text-tertiary); }
.summary-card > strong { color: var(--c-text); font: 600 32px/1.25 var(--font-display); letter-spacing: -0.04em; font-variant-numeric: tabular-nums; }
.summary-card small { color: var(--c-text-tertiary); font-size: 11px; line-height: 1.5; }
.analytics-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 20px; align-items: stretch; }
.analysis-panel { min-width: 0; padding: 24px; box-shadow: var(--shadow-panel); }
.panel-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
.panel-header h2,
.insight-band h2 { margin: 0; color: var(--c-text); font-size: 16px; font-weight: 600; line-height: 1.5; }
.panel-header p { margin: 5px 0 0; color: var(--c-text-tertiary); font-size: 12px; line-height: 1.6; }
.panel-stat { flex-shrink: 0; text-align: right; }
.panel-stat strong { display: block; color: var(--c-accent); font: 600 25px/1.2 var(--font-display); font-variant-numeric: tabular-nums; }
.panel-stat span { display: block; margin-top: 5px; color: var(--c-text-tertiary); font-size: 10px; line-height: 1.4; }
.type-body,
.status-body { display: grid; gap: 16px; }
.chart-frame { min-width: 0; }
.chart { width: 100%; height: 280px; }
.distribution-list,
.status-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px 24px; padding-top: 20px; border-top: 1px solid var(--c-border-soft); }
.distribution-row,
.status-item { min-width: 0; }
.distribution-head,
.status-item div:first-child { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
.distribution-head span { display: inline-flex; align-items: center; gap: 7px; min-width: 0; color: var(--c-text-secondary); font-size: 12px; }
.distribution-head i { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.distribution-head strong,
.status-item strong { color: var(--c-text); font-size: 12px; font-weight: 500; white-space: nowrap; }
.distribution-row small { display: block; margin-top: 6px; color: var(--c-text-tertiary); font-size: 10px; text-align: right; }
.distribution-meter,
.status-meter { overflow: hidden; height: 4px; border-radius: var(--r-pill); background: var(--c-bg-soft); }
.distribution-meter span,
.status-meter span { display: block; height: 100%; border-radius: inherit; }
.status-item strong { overflow: hidden; text-overflow: ellipsis; }
.status-item div > span { color: var(--c-text-tertiary); font-size: 10px; white-space: nowrap; }
.empty-state { display: flex; align-items: center; justify-content: center; min-height: 340px; }
.insight-band { display: grid; grid-template-columns: 160px minmax(0, 1fr); gap: 24px; align-items: start; padding: 24px; }
.insight-band h2 { padding-top: 2px; }
.insight-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 24px; }
.insight-grid article { min-width: 0; padding-left: 24px; border-left: 1px solid var(--c-border-soft); }
.insight-grid span,
.insight-grid small { display: block; color: var(--c-text-tertiary); font-size: 11px; line-height: 1.6; }
.insight-grid strong { display: block; overflow: hidden; margin: 7px 0 4px; color: var(--c-text); font-size: 15px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 1100px) {
  .analytics-grid { grid-template-columns: 1fr; }
  .stats-hero { align-items: flex-start; }
  .sync-note { display: none; }
  .summary-card { padding: 0 18px; }
  .insight-band { grid-template-columns: 1fr; gap: 18px; }
  .insight-grid article:first-child { border-left: 0; padding-left: 0; }
}
@media (max-width: 760px) {
  .stats-page { gap: 20px; }
  .stats-hero { flex-direction: column; gap: 16px; }
  .hero-actions { justify-content: flex-start; }
  .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px 0; padding: 20px 0; }
  .summary-card:nth-child(3) { border-left: 0; }
  .summary-card > strong { font-size: 28px; }
  .analysis-panel,
  .insight-band { padding: 18px; }
  .panel-header { gap: 10px; }
  .panel-stat strong { font-size: 22px; }
  .chart { height: 250px; }
  .distribution-list,
  .status-list { grid-template-columns: 1fr; gap: 18px; }
  .insight-grid { grid-template-columns: 1fr; gap: 16px; }
  .insight-grid article { padding-left: 0; border-left: 0; }
  .insight-grid article + article { padding-top: 16px; border-top: 1px solid var(--c-border-soft); }
}
</style>
