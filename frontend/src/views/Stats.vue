<template>
  <div class="page stats-page">
    <section class="stats-hero">
      <div class="stats-heading">
        <span class="eyebrow">Analytics</span>
        <h1 class="page-title">统计分析</h1>
        <p class="page-subtitle">从内容类型和生产状态观察资产结构，判断选题覆盖、内容沉淀和交付节奏。</p>
      </div>
      <div class="hero-actions">
        <span class="sync-note">数据来自内容库实时统计</span>
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </div>
    </section>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <section class="summary-grid" aria-label="统计摘要">
      <article v-for="card in summaryCards" :key="card.label" class="summary-card" :class="card.tone">
        <div class="summary-top">
          <span>{{ card.label }}</span>
          <component :is="card.icon" />
        </div>
        <strong>{{ card.value }}</strong>
        <small>{{ card.caption }}</small>
        <div class="summary-meter" aria-hidden="true">
          <span :style="{ width: card.meter }" />
        </div>
      </article>
    </section>

    <section class="analytics-grid">
      <article class="analysis-panel type-panel">
        <header class="panel-header">
          <div>
            <span class="panel-kicker">Content Mix</span>
            <h2>内容类型分布</h2>
            <p>查看不同平台和内容格式在内容库里的占比。</p>
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
            <span class="panel-kicker">Workflow Status</span>
            <h2>内容状态分布</h2>
            <p>观察内容停留在草稿、Agent 完稿或其他生产状态的数量。</p>
          </div>
          <div class="panel-stat warm">
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
        <span class="panel-kicker">Readout</span>
        <h2>结构判断</h2>
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

const palette = ['#2563eb', '#0f766e', '#b7791f', '#c2410c', '#475467', '#7c3aed', '#0891b2']

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
    meter: meterFor(totalContents.value, Math.max(totalContents.value, 10)),
    tone: 'blue',
    icon: DataAnalysis,
  },
  {
    label: '内容类型',
    value: formatNumber(typeRows.value.length),
    caption: '当前覆盖的平台和格式',
    meter: meterFor(typeRows.value.length, 6),
    tone: 'green',
    icon: CollectionTag,
  },
  {
    label: '生产状态',
    value: formatNumber(statusRows.value.length),
    caption: '内容所处流程阶段',
    meter: meterFor(statusRows.value.length, 5),
    tone: 'amber',
    icon: Finished,
  },
  {
    label: '主类型占比',
    value: dominantType.value?.percentLabel ?? '0%',
    caption: dominantType.value ? dominantType.value.label : '暂无主类型',
    meter: dominantType.value?.percentLabel ?? '0%',
    tone: 'slate',
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
      radius: ['54%', '76%'],
      center: ['50%', '52%'],
      avoidLabelOverlap: true,
      itemStyle: {
        borderColor: '#ffffff',
        borderWidth: 3,
      },
      label: {
        color: '#475467',
        formatter: '{b}\n{d}%',
        lineHeight: 18,
      },
      labelLine: {
        length: 12,
        length2: 8,
        lineStyle: {
          color: '#98a2b3',
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
    axisLine: { lineStyle: { color: '#dbe1ea' } },
    axisLabel: {
      color: '#667085',
      interval: 0,
      margin: 12,
      formatter: (value: string) => (value.length > 6 ? `${value.slice(0, 6)}...` : value),
    },
  },
  yAxis: {
    type: 'value',
    minInterval: 1,
    splitLine: { lineStyle: { color: '#e8edf3' } },
    axisLabel: { color: '#667085' },
  },
  series: [
    {
      name: '状态数量',
      type: 'bar',
      data: statusRows.value.map(row => ({
        value: row.value,
        itemStyle: { color: row.color },
      })),
      barMaxWidth: 64,
      itemStyle: {
        borderRadius: [4, 4, 0, 0],
      },
      label: {
        show: true,
        position: 'top',
        color: '#101828',
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

function meterFor(value: number, max: number) {
  if (max <= 0) return '0%'
  return `${Math.min(100, Math.round((value / max) * 100))}%`
}

onMounted(load)
</script>

<style scoped>
.stats-page {
  display: grid;
  gap: 20px;
  max-width: 1440px;
}

.stats-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding: 4px 0 2px;
}

.stats-heading {
  max-width: 720px;
}

.eyebrow,
.panel-kicker {
  display: inline-block;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  line-height: 1.3;
  text-transform: uppercase;
}

.stats-heading .page-title {
  margin-top: 6px;
}

.stats-heading .page-subtitle {
  max-width: 680px;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.sync-note {
  color: var(--c-text-tertiary);
  font-size: 12px;
}

.error-banner {
  border: 1px solid var(--c-fail);
  border-radius: var(--r-card);
  background: var(--c-fail-soft);
  color: var(--c-fail);
  padding: 10px 12px;
  font-size: 13px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.summary-card,
.analysis-panel,
.insight-band {
  border: 1px solid var(--c-border);
  border-radius: var(--r-card);
  background: var(--c-surface);
  box-shadow: var(--shadow-panel);
}

.summary-card {
  min-height: 132px;
  padding: 16px 18px;
  display: grid;
  align-content: space-between;
  gap: 10px;
}

.summary-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.summary-top span {
  color: var(--c-text-secondary);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.summary-top svg {
  width: 18px;
  height: 18px;
  color: var(--metric-color);
}

.summary-card strong {
  color: var(--c-text);
  font-size: 32px;
  font-weight: 650;
  letter-spacing: 0;
  line-height: 1;
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
}

.summary-card small {
  color: var(--c-text-tertiary);
  font-size: 12px;
  line-height: 1.4;
}

.summary-card.blue {
  --metric-color: #2563eb;
}

.summary-card.green {
  --metric-color: #0f766e;
}

.summary-card.amber {
  --metric-color: #b7791f;
}

.summary-card.slate {
  --metric-color: #475467;
}

.summary-meter,
.distribution-meter,
.status-meter {
  overflow: hidden;
  height: 6px;
  border-radius: 999px;
  background: var(--c-bg-code);
}

.summary-meter span,
.distribution-meter span,
.status-meter span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--metric-color);
}

.analytics-grid {
  display: grid;
  grid-template-columns: minmax(360px, 0.84fr) minmax(0, 1.45fr);
  gap: 16px;
  align-items: stretch;
}

.analysis-panel {
  min-width: 0;
  padding: 20px;
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.panel-header h2,
.insight-band h2 {
  margin: 4px 0 0;
  color: var(--c-text);
  font-size: 18px;
  font-weight: 650;
  letter-spacing: 0;
  line-height: 1.25;
}

.panel-header p {
  margin: 6px 0 0;
  color: var(--c-text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.panel-stat {
  min-width: 112px;
  padding: 10px 12px;
  border: 1px solid var(--c-border-soft);
  border-radius: var(--r-card);
  background: var(--c-accent-soft);
  text-align: right;
}

.panel-stat.warm {
  background: var(--c-warn-soft);
}

.panel-stat strong {
  display: block;
  color: var(--c-text);
  font-size: 22px;
  font-weight: 650;
  line-height: 1.05;
}

.panel-stat span {
  display: block;
  margin-top: 4px;
  color: var(--c-text-secondary);
  font-size: 12px;
  line-height: 1.35;
}

.type-body,
.status-body {
  display: grid;
  gap: 16px;
}

.type-body {
  grid-template-columns: minmax(0, 1fr);
}

.status-body {
  grid-template-columns: minmax(0, 1fr) minmax(220px, 280px);
  align-items: center;
}

.chart-frame {
  min-width: 0;
  border: 1px solid var(--c-border-soft);
  border-radius: var(--r-card);
  background: linear-gradient(180deg, #ffffff 0%, #fbfcfe 100%);
}

.donut-frame {
  padding: 4px;
}

.bar-frame {
  padding: 10px 10px 0;
}

.chart {
  width: 100%;
}

.donut-chart {
  height: 300px;
}

.status-chart {
  height: 330px;
}

.distribution-list,
.status-list {
  display: grid;
  gap: 10px;
}

.distribution-row,
.status-item {
  border: 1px solid var(--c-border-soft);
  border-radius: var(--r-card);
  background: #fbfcfe;
  padding: 11px 12px;
}

.distribution-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 9px;
}

.distribution-head span {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
  color: var(--c-text);
  font-size: 13px;
  font-weight: 600;
}

.distribution-head i {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  flex: 0 0 auto;
}

.distribution-head strong {
  color: var(--c-text);
  font-size: 13px;
  font-weight: 650;
  white-space: nowrap;
}

.distribution-row small {
  display: block;
  margin-top: 7px;
  color: var(--c-text-tertiary);
  font-size: 12px;
  text-align: right;
}

.status-item {
  display: grid;
  gap: 9px;
}

.status-item div:first-child {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.status-item strong {
  min-width: 0;
  color: var(--c-text);
  font-size: 13px;
  font-weight: 650;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-item span {
  color: var(--c-text-tertiary);
  font-size: 12px;
  white-space: nowrap;
}

.empty-state {
  min-height: 300px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.insight-band {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 20px;
  align-items: stretch;
  padding: 18px 20px;
}

.insight-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.insight-grid article {
  min-width: 0;
  border-left: 1px solid var(--c-border-soft);
  padding-left: 16px;
}

.insight-grid span,
.insight-grid small {
  display: block;
  color: var(--c-text-tertiary);
  font-size: 12px;
  line-height: 1.45;
}

.insight-grid strong {
  display: block;
  margin: 5px 0 4px;
  color: var(--c-text);
  font-size: 16px;
  font-weight: 650;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 1180px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .analytics-grid,
  .status-body,
  .insight-band {
    grid-template-columns: 1fr;
  }

  .status-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .insight-grid article {
    border-left: 0;
    padding-left: 0;
  }
}

@media (max-width: 760px) {
  .stats-page {
    padding: 16px;
  }

  .stats-hero,
  .panel-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .hero-actions {
    justify-content: flex-start;
  }

  .summary-grid,
  .status-list,
  .insight-grid {
    grid-template-columns: 1fr;
  }

  .analysis-panel,
  .insight-band {
    padding: 16px;
  }

  .donut-chart,
  .status-chart {
    height: 280px;
  }

  .panel-stat {
    width: 100%;
    text-align: left;
  }
}
</style>
