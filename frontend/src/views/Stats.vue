<template>
  <div class="page stats-page">
    <section class="stats-hero">
      <div class="stats-heading">
        <h1 class="page-title">统计分析</h1>
        <p class="page-subtitle">看清内容积累，找到下一步的创作方向。</p>
      </div>
      <div class="hero-actions">
        <span class="sync-note">数据来自内容库实时统计</span>
        <el-button :icon="Refresh" :loading="loading || performanceLoading" @click="load">刷新</el-button>
      </div>
    </section>

    <div v-if="error" class="error-banner" role="alert">
      {{ error }} <el-button size="small" :loading="loading" @click="loadCounts">重试内容统计</el-button>
    </div>

    <section class="summary-grid" aria-label="统计摘要" :aria-busy="loading">
      <article v-for="card in summaryCards" :key="card.label" class="summary-card">
        <div class="summary-top">
          <span>{{ card.label }}</span>
          <component :is="card.icon" />
        </div>
        <strong>{{ card.value }}</strong>
        <small>{{ card.caption }}</small>
      </article>
    </section>

    <section class="analysis-panel performance-panel" aria-label="内容效果分析" :aria-busy="performanceLoading">
      <header class="panel-header performance-header">
        <div>
          <h2>内容效果</h2>
          <p>按内容创建日期选择范围，汇总各平台最近录入的累计读数。不是期间新增量，也不是平台实时数据。</p>
        </div>
        <div class="performance-filters">
          <label for="performance-days">内容创建范围
            <select id="performance-days" v-model.number="performanceDays">
              <option :value="7">近 7 天</option><option :value="30">近 30 天</option>
              <option :value="90">近 90 天</option><option :value="365">近 365 天</option>
            </select>
          </label>
          <label for="performance-platform">效果平台
            <select id="performance-platform" v-model="performancePlatform" :title="performancePlatform ? platformLabel(performancePlatform) : '全部平台'">
              <option value="">全部平台</option>
              <option v-for="platform in availablePlatforms" :key="platform" :value="platform">{{ platformLabel(platform) }}</option>
            </select>
          </label>
        </div>
      </header>
      <div v-if="performanceError" class="error-banner" role="alert">
        {{ performanceError }} <el-button size="small" @click="loadPerformance">重试效果数据</el-button>
      </div>
      <p v-else-if="performanceLoading" role="status">正在加载效果数据…</p>
      <template v-else-if="performance">
        <p class="performance-caption">
          {{ performance.window_start }} 至 {{ performance.window_end }} 创建的 {{ formatNumber(performance.total_contents) }} 篇内容，
          {{ formatNumber(performance.measured_contents) }} 篇有{{ performancePlatform ? '所选平台的' : '' }}读数，
          {{ formatNumber(performance.missing_contents) }} 篇未录入。未录入不计作零阅读。
        </p>
        <div v-if="performance.totals.metric_rows" class="performance-content">
          <div class="performance-summary">
            <article><span>累计浏览</span><strong>{{ formatNumber(performance.totals.views) }}</strong></article>
            <article><span>累计互动</span><strong>{{ formatNumber(performance.totals.interactions) }}</strong><small>点赞 + 评论 + 分享</small></article>
            <article><span>整体互动率</span><strong>{{ formatRate(performance.totals.engagement_rate) }}</strong><small>总互动 ÷ 总浏览；零浏览时无法计算</small></article>
            <article><span>数据覆盖</span><strong>{{ performance.total_contents ? Math.round(performance.measured_contents / performance.total_contents * 100) : 0 }}%</strong><small>{{ performance.totals.metric_rows }} 组内容/平台读数</small></article>
          </div>
          <div class="performance-table-wrap">
            <table class="performance-table">
              <caption>平台表现</caption>
              <thead><tr><th>平台</th><th>已录入内容</th><th>浏览</th><th>点赞</th><th>评论</th><th>分享</th><th>互动率</th></tr></thead>
              <tbody><tr v-for="row in performance.by_platform" :key="row.platform">
                <th scope="row">{{ platformLabel(row.platform) }}</th><td>{{ formatNumber(row.metric_rows) }}</td>
                <td>{{ formatNumber(row.views) }}</td><td>{{ formatNumber(row.likes) }}</td><td>{{ formatNumber(row.comments) }}</td><td>{{ formatNumber(row.shares) }}</td><td>{{ formatRate(row.engagement_rate) }}</td>
              </tr></tbody>
            </table>
          </div>
          <div class="performance-chart">
            <h3>按内容创建日期看累计浏览</h3>
            <p class="performance-caption">每根柱表示当天创建的内容目前累计获得的浏览，不代表当天新增浏览。</p>
            <v-chart class="chart" :option="performanceOption" autoresize />
          </div>
          <div class="performance-table-wrap">
            <table class="performance-table">
              <caption>累计浏览前 10 名（按内容 / 平台）</caption>
              <thead><tr><th>内容</th><th>平台</th><th>浏览</th><th>互动</th><th>互动率</th></tr></thead>
              <tbody><tr v-for="row in performance.top_contents" :key="`${row.content_id}:${row.platform}`">
                <th scope="row" class="performance-title">{{ row.title || `内容 #${row.content_id}` }}</th><td>{{ platformLabel(row.platform) }}</td>
                <td>{{ formatNumber(row.views) }}</td><td>{{ formatNumber(row.interactions) }}</td><td>{{ formatRate(row.engagement_rate) }}</td>
              </tr></tbody>
            </table>
          </div>
          <p class="performance-caption">最新录入时间：{{ performance.last_recorded_at?.replace('T', ' ') || '未知' }}。同一内容多平台分别计入，不能视作去重用户数。</p>
        </div>
        <div v-else class="performance-empty">
          <p>当前范围{{ performancePlatform ? '及平台' : '' }}尚无效果读数。</p>
          <router-link to="/history">到内容库录入或导入效果数据</router-link>
        </div>
      </template>
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
            <span>{{ dominantType ? `${dominantType.label} 占比` : stats ? '暂无主类型' : '等待统计数据' }}</span>
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
        <el-empty v-else-if="stats" class="empty-state" description="暂无内容类型数据" />
        <p v-else class="stats-unavailable" :role="loading ? 'status' : undefined">{{ loading ? '正在加载内容类型数据…' : '内容类型数据尚未加载' }}</p>
      </article>

      <article class="analysis-panel status-panel">
        <header class="panel-header">
          <div>
            <h2>内容状态分布</h2>
            <p>从草稿到发布，了解内容进展</p>
          </div>
          <div class="panel-stat">
            <strong>{{ dominantStatus?.value ?? (stats ? 0 : '—') }}</strong>
            <span>{{ dominantStatus ? dominantStatus.label : stats ? '暂无状态' : '等待统计数据' }}</span>
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
        <el-empty v-else-if="stats" class="empty-state" description="暂无内容状态数据" />
        <p v-else class="stats-unavailable" :role="loading ? 'status' : undefined">{{ loading ? '正在加载内容状态数据…' : '内容状态数据尚未加载' }}</p>
      </article>
    </section>

    <section class="insight-band">
      <div>
        <h2>内容小结</h2>
      </div>
      <div class="insight-grid">
        <article>
          <span>覆盖类型</span>
          <strong>{{ stats ? typeRows.length : '—' }}</strong>
          <small>{{ !stats ? '等待统计数据' : typeRows.length > 1 ? '内容格式较分散' : typeRows.length ? '当前主要集中在单一内容格式' : '暂无内容类型数据' }}</small>
        </article>
        <article>
          <span>最大类型</span>
          <strong>{{ dominantType?.label ?? '-' }}</strong>
          <small>{{ dominantType ? `${dominantType.value} 篇，${dominantType.percentLabel}` : stats ? '暂无可分析数据' : '等待统计数据' }}</small>
        </article>
        <article>
          <span>主要状态</span>
          <strong>{{ dominantStatus?.label ?? '-' }}</strong>
          <small>{{ dominantStatus ? `${dominantStatus.value} 篇，${dominantStatus.percentLabel}` : stats ? '暂无可分析数据' : '等待统计数据' }}</small>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { readWorkspace, workspaceKeys } from '../query/client'
import { workspaceSessionId, workspaceSessionReady } from '../workspaceSession'
import { use } from 'echarts/core'
import { BarChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import { CollectionTag, DataAnalysis, Finished, PieChart as PieIcon, Refresh } from '@element-plus/icons-vue'
import { ElEmpty } from 'element-plus/es/components/empty/index'
import 'element-plus/es/components/empty/style/css'
import { getPerformanceStats, getStats } from '../api/stats'
import { getContentTypeLabel } from '../constants/content'

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

const performanceDays = ref(30)
const performancePlatform = ref('')
const availablePlatforms = ref<string[]>([])
const countsQuery = useQuery({
  queryKey: computed(() => workspaceKeys.counts()),
  enabled: workspaceSessionReady,
  queryFn: ({ queryKey, signal }) => readWorkspace(queryKey[1], signal, () => getStats(signal))
})
const performanceQuery = useQuery({
  queryKey: computed(() => [...workspaceKeys.performance(), { days: performanceDays.value, platform: performancePlatform.value || undefined }] as const),
  enabled: workspaceSessionReady,
  queryFn: ({ queryKey, signal }) => readWorkspace(queryKey[1], signal, () => getPerformanceStats(queryKey[4], signal))
})
const stats = countsQuery.data
const loading = countsQuery.isFetching
const error = computed(() => !countsQuery.error.value ? '' : stats.value
  ? '内容统计刷新失败，当前显示上次成功加载的数据，可能已过期。'
  : '内容统计加载失败，请重试。')
const performance = performanceQuery.data
const performanceLoading = performanceQuery.isFetching
const performanceError = computed(() => !performanceQuery.error.value ? '' : performance.value
  ? '效果数据刷新失败，当前显示上次成功加载的数据，可能已过期。'
  : '效果数据加载失败，请重试。')
watch(performance, result => {
  if (result) availablePlatforms.value = [...new Set([...result.available_platforms, ...(performancePlatform.value ? [performancePlatform.value] : [])])].sort()
}, { immediate: true })
watch(workspaceSessionId, () => { availablePlatforms.value = []; performancePlatform.value = '' }, { flush: 'sync' })

function platformLabel(platform: string) {
  return platform === 'unknown' ? '未标注平台' : getContentTypeLabel(platform)
}

function formatRate(value: number | null) {
  return value === null ? '—' : `${(value * 100).toFixed(1)}%`
}

const performanceOption = computed(() => ({
  color: [palette[0]],
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { top: 20, right: 20, bottom: 44, left: 64 },
  xAxis: {
    type: 'category', data: performance.value?.by_creation_date.map(row => row.date.slice(5)) ?? [],
    axisLabel: { color: themeColor('--c-text-tertiary') }
  },
  yAxis: { type: 'value', minInterval: 1, axisLabel: { color: themeColor('--c-text-tertiary') } },
  series: [{ name: '这些内容的累计浏览', type: 'bar', barMaxWidth: 36,
    data: performance.value?.by_creation_date.map(row => row.metric_rows ? row.views : null) ?? [] }]
}))

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
    value: stats.value ? formatNumber(totalContents.value) : '—',
    caption: '内容库资产总量',
    icon: DataAnalysis,
  },
  {
    label: '内容类型',
    value: stats.value ? formatNumber(typeRows.value.length) : '—',
    caption: '当前覆盖的平台和格式',
    icon: CollectionTag,
  },
  {
    label: '生产状态',
    value: stats.value ? formatNumber(statusRows.value.length) : '—',
    caption: '内容所处流程阶段',
    icon: Finished,
  },
  {
    label: '主类型占比',
    value: dominantType.value?.percentLabel ?? (stats.value ? '0%' : '—'),
    caption: dominantType.value ? dominantType.value.label : stats.value ? '暂无主类型' : '等待统计数据',
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

async function loadCounts() { await countsQuery.refetch() }
async function loadPerformance() { await performanceQuery.refetch() }
async function load() { await Promise.all([loadCounts(), loadPerformance()]) }

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

</script>

<style scoped>
.stats-page { display: grid; gap: 24px; }
.performance-content { display: grid; gap: 24px; }
.performance-header > div { min-width: 0; }
.performance-filters { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; flex: 0 1 320px; width: 100%; max-width: 320px; min-width: 0; }
.performance-filters label { display: grid; gap: 6px; min-width: 0; color: var(--c-text-secondary); font-size: 12px; }
.performance-filters select { box-sizing: border-box; width: 100%; max-width: 100%; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 8px; border: 1px solid var(--c-border); border-radius: var(--r-control); color: var(--c-text); background: var(--c-surface); font: inherit; }
.performance-caption { color: var(--c-text-tertiary); font-size: 12px; line-height: 1.7; }
.performance-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 20px; padding: 20px 0; }
.performance-summary article { display: grid; align-content: start; gap: 8px; min-width: 0; }
.performance-summary span, .performance-summary small { color: var(--c-text-secondary); font-size: 12px; line-height: 1.5; }
.performance-summary strong { min-width: 0; overflow-wrap: anywhere; font: 600 clamp(20px, 2.8vw, 28px)/1.25 var(--font-display); font-variant-numeric: tabular-nums; }
.performance-table-wrap { overflow-x: auto; }
.performance-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.performance-table caption, .performance-chart h3 { margin: 0 0 12px; text-align: left; font-size: 14px; font-weight: 600; }
.performance-table th, .performance-table td { padding: 12px 10px; border-bottom: 1px solid var(--c-border-soft); text-align: right; white-space: nowrap; }
.performance-table th:first-child { text-align: left; }
.performance-table .performance-title { white-space: normal; min-width: 140px; max-width: 360px; overflow-wrap: anywhere; }
.performance-empty { padding: 28px 0; color: var(--c-text-secondary); text-align: center; }
.performance-empty a { color: var(--c-accent); font-size: 13px; }
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
.summary-card > strong { min-width: 0; overflow-wrap: anywhere; color: var(--c-text); font: 600 32px/1.25 var(--font-display); letter-spacing: -0.04em; font-variant-numeric: tabular-nums; }
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
.stats-unavailable { display: grid; place-content: center; min-height: 280px; margin: 0; color: var(--c-text-tertiary); font-size: 13px; }
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
  .performance-header { flex-direction: column; }
  .performance-filters { flex: none; max-width: none; }
  .performance-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
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
