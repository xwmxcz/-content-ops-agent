<template>
  <div class="calendar-page">
    <section class="calendar-hero">
      <div class="hero-copy">
        <h1>发布日历</h1>
        <p>把内容安排在合适的时间。<span>{{ calendarRangeLabel }}</span></p>
      </div>
      <div class="hero-actions">
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="openDialog()">添加计划</el-button>
      </div>
    </section>

    <section class="signal-grid">
      <article class="signal-card">
        <span>未来排期</span>
        <strong>{{ events.length }}</strong>
        <small>{{ activeDayCount }} 个日期有计划</small>
      </article>
      <article class="signal-card">
        <span>今日发布</span>
        <strong>{{ todayEvents.length }}</strong>
        <small>{{ todayLabel }}</small>
      </article>
      <article class="signal-card">
        <span>覆盖平台</span>
        <strong>{{ platformCount }}</strong>
        <small>{{ dominantPlatformLabel }}</small>
      </article>
      <article class="signal-card">
        <span>高峰日期</span>
        <strong>{{ busiestDay.count }}</strong>
        <small>{{ busiestDay.label }}</small>
      </article>
    </section>

    <section class="calendar-shell">
      <main class="calendar-panel">
        <div class="panel-head">
          <div>
            <h2>排期总览</h2>
          </div>
          <span class="range-pill">{{ events.length ? '已同步' : '暂无计划' }}</span>
        </div>

        <el-calendar>
          <template #date-cell="{ data }">
            <button
              class="calendar-cell"
              :class="{ today: data.day === todayKey, selected: data.day === selectedDay }"
              :aria-label="`${data.day}，${eventsByDate[data.day]?.length || 0} 条发布计划`"
              :aria-pressed="data.day === selectedDay"
              type="button"
              @click="selectDay(data.day)"
            >
              <span class="day-number">{{ dayNumber(data.day) }}</span>
              <span v-if="data.day === todayKey" class="today-dot">今天</span>
              <div class="event-stack">
                <span
                  v-for="event in visibleCellEvents(data.day)"
                  :key="event.event_id"
                  class="event-chip"
                  :class="platformClass(event.platform)"
                  :title="event.content_title || `#${event.content_id}`"
                >
                  <span class="chip-platform">{{ platformLabel(event.platform) }}</span>
                  <span class="chip-title">{{ event.content_title || `#${event.content_id}` }}</span>
                </span>
                <span v-if="overflowCount(data.day)" class="more-chip">+{{ overflowCount(data.day) }}</span>
              </div>
            </button>
          </template>
        </el-calendar>
      </main>

      <aside class="side-panel">
        <section class="side-section selected-day">
          <div class="panel-head compact">
            <div>
              <span class="panel-kicker">选中日期</span>
              <h2>{{ selectedDayTitle }}</h2>
            </div>
            <el-button size="small" :icon="Plus" @click="openDialog(selectedDay)">添加</el-button>
          </div>

          <div v-if="selectedDayEvents.length" class="day-agenda">
            <article v-for="event in selectedDayEvents" :key="event.event_id" class="agenda-row">
              <span class="agenda-marker" :class="platformClass(event.platform)"></span>
              <div>
                <strong>{{ event.content_title || `内容 #${event.content_id}` }}</strong>
                <span>{{ platformLabel(event.platform) }} · {{ statusLabel(event.status) }}</span>
              </div>
              <small>#{{ event.content_id }}</small>
            </article>
          </div>
          <el-empty v-else description="当天没有发布计划" />
        </section>

        <section class="side-section">
          <div class="panel-head compact">
            <div>
              <h2>近期计划</h2>
            </div>
            <span class="range-pill">{{ upcomingEvents.length }}</span>
          </div>

          <div v-if="upcomingEvents.length" class="queue-list">
            <article v-for="event in upcomingEvents" :key="event.event_id" class="queue-row">
              <div class="queue-date">
                <strong>{{ dayNumber(event.scheduled_date) }}</strong>
                <span>{{ monthLabel(event.scheduled_date) }}</span>
              </div>
              <div class="queue-copy">
                <strong>{{ event.content_title || `内容 #${event.content_id}` }}</strong>
                <span>{{ platformLabel(event.platform) }} · {{ relativeDate(event.scheduled_date) }}</span>
              </div>
              <span class="queue-status">{{ statusLabel(event.status) }}</span>
            </article>
          </div>
          <el-empty v-else description="未来 60 天暂无计划" />
        </section>
      </aside>
    </section>

    <el-dialog v-model="dialog" title="添加发布计划" width="min(460px, calc(100vw - 32px))" class="calendar-dialog">
      <el-form label-position="top">
        <el-form-item label="内容 ID">
          <el-input-number v-model="form.content_id" :min="1" controls-position="right" />
        </el-form-item>
        <el-form-item label="平台">
          <el-select v-model="form.platform" filterable allow-create default-first-option>
            <el-option v-for="item in platformOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="form.scheduled_date" value-format="YYYY-MM-DD" type="date" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElCalendar } from 'element-plus/es/components/calendar/index'
import { ElDatePicker } from 'element-plus/es/components/date-picker/index'
import { ElDialog } from 'element-plus/es/components/dialog/index'
import { ElEmpty } from 'element-plus/es/components/empty/index'
import { ElForm, ElFormItem } from 'element-plus/es/components/form/index'
import { ElInputNumber } from 'element-plus/es/components/input-number/index'
import { ElMessage } from 'element-plus/es/components/message/index'
import 'element-plus/es/components/calendar/style/css'
import 'element-plus/es/components/date-picker/style/css'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/es/components/empty/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/input-number/style/css'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { createEvent, getEvents, type CalendarEvent } from '../api/calendar'
import { CONTENT_TYPE_OPTIONS, getContentTypeLabel } from '../constants/content'

const platformOptions = CONTENT_TYPE_OPTIONS
const events = ref<CalendarEvent[]>([])
const loading = ref(false)
const saving = ref(false)
const dialog = ref(false)
const todayKey = formatDateKey(new Date())
const selectedDay = ref(todayKey)
const form = reactive({ content_id: 1, platform: 'xiaohongshu', scheduled_date: todayKey })

const eventsByDate = computed(() => {
  const grouped: Record<string, CalendarEvent[]> = {}
  for (const event of events.value) {
    grouped[event.scheduled_date] ||= []
    grouped[event.scheduled_date].push(event)
  }
  for (const date of Object.keys(grouped)) {
    grouped[date].sort((a, b) => a.platform.localeCompare(b.platform))
  }
  return grouped
})

const todayEvents = computed(() => eventsByDate.value[todayKey] || [])
const selectedDayEvents = computed(() => eventsByDate.value[selectedDay.value] || [])
const activeDayCount = computed(() => Object.keys(eventsByDate.value).length)
const platformCount = computed(() => new Set(events.value.map(event => event.platform)).size)
const upcomingEvents = computed(() =>
  [...events.value]
    .sort((a, b) => a.scheduled_date.localeCompare(b.scheduled_date))
    .slice(0, 8)
)

const busiestDay = computed(() => {
  let candidate = { date: '', count: 0 }
  for (const [date, items] of Object.entries(eventsByDate.value)) {
    if (items.length > candidate.count) candidate = { date, count: items.length }
  }
  return {
    count: candidate.count,
    label: candidate.date ? formatShortDate(candidate.date) : '暂无排期'
  }
})

const dominantPlatformLabel = computed(() => {
  if (!events.value.length) return '暂无平台'
  const counts = new Map<string, number>()
  for (const event of events.value) counts.set(event.platform, (counts.get(event.platform) || 0) + 1)
  const [platform, count] = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]
  return `${platformLabel(platform)} ${count} 条`
})

const selectedDayTitle = computed(() => formatFullDate(selectedDay.value))
const todayLabel = computed(() => formatFullDate(todayKey))
const calendarRangeLabel = computed(() => `未来 60 天 · ${formatFullDate(todayKey)} 起`)

function selectDay(day: string) {
  selectedDay.value = day
}

function openDialog(day = selectedDay.value) {
  form.scheduled_date = day || todayKey
  dialog.value = true
}

function visibleCellEvents(day: string) {
  return (eventsByDate.value[day] || []).slice(0, 3)
}

function overflowCount(day: string) {
  return Math.max(0, (eventsByDate.value[day]?.length || 0) - 3)
}

async function load() {
  loading.value = true
  try {
    events.value = await getEvents(60)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!form.scheduled_date) {
    ElMessage.warning('请选择发布日期')
    return
  }
  saving.value = true
  try {
    await createEvent(form)
    ElMessage.success('发布计划已保存')
    dialog.value = false
    selectedDay.value = form.scheduled_date
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    saving.value = false
  }
}

function platformLabel(platform: string) {
  return getContentTypeLabel(platform)
}

function platformClass(platform: string) {
  const key = platform.toLowerCase().replace(/[^a-z0-9_-]/g, '-')
  if (['xiaohongshu', 'weibo', 'blog', 'video_script', 'twitter'].includes(key)) return `platform-${key}`
  return 'platform-other'
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    planned: '已计划',
    scheduled: '已定时',
    published: '已发布',
    completed: '已完成',
    failed: '失败'
  }
  return labels[status] || status || '未知'
}

function dayNumber(dateKey: string) {
  return dateKey.split('-')[2] || dateKey
}

function monthLabel(dateKey: string) {
  const [, month] = dateKey.split('-')
  return `${Number(month)}月`
}

function formatDateKey(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function parseDateKey(dateKey: string) {
  const [year, month, day] = dateKey.split('-').map(Number)
  return new Date(year, month - 1, day)
}

function formatFullDate(dateKey: string) {
  const date = parseDateKey(dateKey)
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'long',
    day: 'numeric',
    weekday: 'short'
  }).format(date)
}

function formatShortDate(dateKey: string) {
  const date = parseDateKey(dateKey)
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    weekday: 'short'
  }).format(date)
}

function relativeDate(dateKey: string) {
  const msPerDay = 24 * 60 * 60 * 1000
  const diff = Math.round((parseDateKey(dateKey).getTime() - parseDateKey(todayKey).getTime()) / msPerDay)
  if (diff === 0) return '今天'
  if (diff === 1) return '明天'
  if (diff < 0) return `${Math.abs(diff)} 天前`
  return `${diff} 天后`
}

onMounted(load)
</script>

<style scoped>
.calendar-page {
  min-width: 0;
  padding: 32px;
  color: var(--c-text);
}

.calendar-hero,
.signal-grid,
.calendar-shell {
  max-width: 1536px;
  margin-inline: auto;
}

.calendar-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 28px;
}

.hero-copy { min-width: 0; }
.hero-copy h1 {
  margin: 0 0 10px;
  font: 650 var(--fs-h1)/1.25 var(--font-display);
  letter-spacing: -0.035em;
}
.hero-copy p {
  margin: 0;
  color: var(--c-text-secondary);
  font-size: 13px;
  line-height: 1.7;
}
.hero-copy p span { margin-left: 12px; color: var(--c-text-tertiary); }
.hero-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.hero-actions :deep(.el-button + .el-button) { margin-left: 0; }

.signal-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: 24px;
  padding: 22px 8px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-card);
  background: var(--c-surface);
}
.signal-card { min-width: 0; padding: 0 24px; }
.signal-card + .signal-card { border-left: 1px solid var(--c-border-soft); }
.signal-card span,
.signal-card small { display: block; color: var(--c-text-tertiary); font-size: 12px; }
.signal-card strong {
  display: block;
  margin: 7px 0 4px;
  color: var(--c-text);
  font: 600 30px/1.2 var(--font-display);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.04em;
}

.calendar-shell {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(290px, 330px);
  gap: 20px;
  align-items: start;
}
.calendar-panel,
.side-section {
  min-width: 0;
  padding: 24px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-card);
  background: var(--c-surface);
  box-shadow: var(--shadow-panel);
}
.side-panel { display: grid; gap: 20px; min-width: 0; }
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 22px;
}
.panel-head.compact { margin-bottom: 18px; }
.panel-head h2 { margin: 0; font-size: 16px; font-weight: 600; line-height: 1.5; }
.panel-kicker { display: block; margin-bottom: 5px; color: var(--c-text-tertiary); font-size: 12px; }
.range-pill {
  display: inline-flex;
  align-items: center;
  min-height: 25px;
  padding: 2px 9px;
  border-radius: var(--r-pill);
  color: var(--c-accent);
  background: var(--c-accent-soft);
  font-size: 11px;
  white-space: nowrap;
}

.calendar-panel :deep(.el-calendar) { --el-calendar-border: 1px solid var(--c-border-soft); }
.calendar-panel :deep(.el-calendar__header) { align-items: center; gap: 12px; padding: 0 0 20px; border: 0; }
.calendar-panel :deep(.el-calendar__title) { color: var(--c-text); font-size: 16px; font-weight: 600; }
.calendar-panel :deep(.el-calendar__body) { padding: 0; }
.calendar-panel :deep(.el-calendar-table) { width: 100%; table-layout: fixed; }
.calendar-panel :deep(.el-calendar-table thead th) { padding: 12px 0; color: var(--c-text-tertiary); font-size: 11px; font-weight: 500; }
.calendar-panel :deep(.el-calendar-table td) { border-color: var(--c-border-soft); }
.calendar-panel :deep(.el-calendar-table td.is-selected) { background: transparent; }
.calendar-panel :deep(.el-calendar-day) { height: 126px; padding: 0; }
.calendar-cell {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  grid-template-rows: auto 1fr;
  align-content: start;
  gap: 6px;
  width: 100%;
  height: 126px;
  padding: 9px 7px;
  border: 0;
  color: var(--c-text);
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background-color 150ms ease, box-shadow 150ms ease;
}
.calendar-cell:hover { background: var(--c-bg-soft); }
.calendar-cell.selected { background: var(--c-accent-soft); box-shadow: inset 0 0 0 1px var(--c-accent); }
.calendar-cell:focus-visible { outline: 2px solid var(--c-accent); outline-offset: -2px; }
.day-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 25px;
  height: 25px;
  border-radius: 50%;
  color: inherit;
  font-size: 12px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.calendar-panel :deep(.prev .day-number),
.calendar-panel :deep(.next .day-number) { color: var(--c-text-tertiary); opacity: 0.55; }
.calendar-cell.today .day-number { color: var(--c-text-inverse); background: var(--c-accent); }
.today-dot { grid-column: 2; grid-row: 1; justify-self: end; align-self: center; color: var(--c-accent); font-size: 10px; }
.event-stack { display: grid; align-content: start; grid-column: 1 / -1; gap: 4px; min-width: 0; }
.event-chip,
.more-chip {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 5px;
  min-width: 0;
  min-height: 20px;
  padding: 3px 5px;
  border-radius: 4px;
  color: var(--chip-fg);
  background: var(--chip-bg);
  font-size: 10px;
  line-height: 1.2;
}
.more-chip { display: inline-flex; justify-self: start; color: var(--c-text-tertiary); background: var(--c-bg-soft); }
.chip-platform { overflow: hidden; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.chip-title { overflow: hidden; opacity: 0.85; text-overflow: ellipsis; white-space: nowrap; }
.platform-xiaohongshu { --chip-bg: var(--c-fail-soft); --chip-fg: var(--c-fail); }
.platform-weibo { --chip-bg: var(--c-warn-soft); --chip-fg: var(--c-warn); }
.platform-blog,
.platform-video_script { --chip-bg: var(--c-accent-soft); --chip-fg: var(--c-accent); }
.platform-twitter,
.platform-other { --chip-bg: var(--c-bg-soft); --chip-fg: var(--c-text-secondary); }

.day-agenda,
.queue-list { display: grid; }
.agenda-row,
.queue-row { min-width: 0; padding: 15px 0; }
.agenda-row + .agenda-row,
.queue-row + .queue-row { border-top: 1px solid var(--c-border-soft); }
.agenda-row { display: grid; grid-template-columns: 4px minmax(0, 1fr) auto; align-items: center; gap: 12px; }
.agenda-marker { width: 4px; height: 32px; border-radius: 3px; background: var(--chip-fg); }
.agenda-row strong,
.queue-copy strong { display: block; overflow: hidden; color: var(--c-text); font-size: 13px; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.agenda-row div > span,
.queue-copy span,
.agenda-row small,
.queue-status { color: var(--c-text-tertiary); font-size: 11px; }
.agenda-row div > span,
.queue-copy span { display: block; margin-top: 5px; }
.queue-row { display: grid; grid-template-columns: 42px minmax(0, 1fr); align-items: center; gap: 10px; }
.queue-date { display: grid; place-items: center; grid-row: span 2; width: 42px; height: 48px; padding: 5px 0; border-radius: var(--r-control); background: var(--c-bg-soft); }
.queue-date strong { color: var(--c-text); font: 600 19px/1.2 var(--font-display); font-variant-numeric: tabular-nums; }
.queue-date span { color: var(--c-text-tertiary); font-size: 10px; }
.queue-status { grid-column: 2; justify-self: start; margin-top: -5px; padding: 2px 7px; border-radius: var(--r-pill); background: var(--c-bg-soft); white-space: nowrap; }
.side-section :deep(.el-empty) { padding: 16px 0; }
.side-section :deep(.el-empty__image) { width: 86px; }
.side-section :deep(.el-empty__description p) { font-size: 12px; }
.calendar-dialog :deep(.el-input-number),
.calendar-dialog :deep(.el-select),
.calendar-dialog :deep(.el-date-editor) { width: 100%; }

@media (max-width: 1240px) {
  .calendar-shell { grid-template-columns: 1fr; }
  .side-panel { grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; }
}
@media (max-width: 760px) {
  .calendar-page { padding: 20px 16px; }
  .calendar-hero { align-items: flex-start; flex-direction: column; gap: 16px; margin-bottom: 20px; }
  .hero-copy p span { display: block; margin-left: 0; }
  .signal-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px 0; padding: 20px 0; }
  .signal-card { padding: 0 18px; }
  .signal-card:nth-child(3) { border-left: 0; }
  .signal-card strong { font-size: 27px; }
  .side-panel { grid-template-columns: 1fr; }
  .calendar-panel,
  .side-section { padding: 16px; }
  .calendar-panel :deep(.el-calendar__header) { align-items: flex-start; flex-direction: column; }
  .calendar-panel :deep(.el-calendar-day),
  .calendar-cell { height: 100px; }
  .calendar-cell { padding: 6px 2px; gap: 5px; }
  .day-number { width: 23px; height: 23px; }
  .today-dot,
  .chip-title { display: none; }
  .event-chip { display: block; overflow: hidden; min-height: 17px; padding: 2px 3px; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
  .event-stack { gap: 2px; }
}
@media (prefers-reduced-motion: reduce) {
  .calendar-cell { transition: none; }
}
</style>
