<template>
  <div class="calendar-page">
    <section class="calendar-hero">
      <div class="hero-copy">
        <span class="hero-kicker">Publishing Calendar</span>
        <h1>发布日历</h1>
        <p>{{ calendarRangeLabel }}</p>
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
            <span class="panel-kicker">Month View</span>
            <h2>排期总览</h2>
          </div>
          <span class="range-pill">{{ events.length ? '已同步' : '暂无计划' }}</span>
        </div>

        <el-calendar>
          <template #date-cell="{ data }">
            <button
              class="calendar-cell"
              :class="{ today: data.day === todayKey, selected: data.day === selectedDay }"
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
              <span class="panel-kicker">Selected Day</span>
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
              <span class="panel-kicker">Next Queue</span>
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

    <el-dialog v-model="dialog" title="添加发布计划" width="460px" class="calendar-dialog">
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
import { ElMessage } from 'element-plus/es/components/message/index'
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
  min-height: calc(100vh - 56px);
  padding: 24px 32px 32px;
  color: var(--c-text);
  background:
    linear-gradient(135deg, rgba(50, 132, 255, 0.08), transparent 34%),
    linear-gradient(315deg, rgba(23, 163, 74, 0.07), transparent 28%),
    var(--c-bg);
}

.calendar-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  max-width: 1520px;
  margin: 0 auto 16px;
}

.hero-copy {
  min-width: 0;
}

.hero-kicker,
.panel-kicker {
  display: inline-block;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.hero-copy h1 {
  margin: 6px 0 6px;
  font-size: 30px;
  font-weight: 650;
  line-height: 1.15;
}

.hero-copy p {
  margin: 0;
  color: var(--c-text-secondary);
  font-size: 14px;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.signal-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  max-width: 1520px;
  margin: 0 auto 16px;
}

.signal-card {
  min-width: 0;
  padding: 15px 16px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: color-mix(in srgb, var(--c-bg) 92%, white);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.04);
}

.signal-card span,
.signal-card small {
  display: block;
  color: var(--c-text-tertiary);
  font-size: 12px;
}

.signal-card strong {
  display: block;
  margin: 6px 0 3px;
  color: var(--c-text);
  font-family: var(--font-mono);
  font-size: 25px;
  font-weight: 650;
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
}

.calendar-shell {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 390px);
  gap: 16px;
  max-width: 1520px;
  margin: 0 auto;
  align-items: start;
}

.calendar-panel,
.side-section {
  min-width: 0;
  padding: 20px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg);
}

.side-panel {
  display: grid;
  gap: 16px;
  min-width: 0;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.panel-head.compact {
  margin-bottom: 12px;
}

.panel-head h2 {
  margin: 4px 0 0;
  font-size: 18px;
  font-weight: 650;
  line-height: 1.25;
}

.range-pill {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border: 1px solid var(--c-border);
  border-radius: 999px;
  color: var(--c-text-secondary);
  background: var(--c-bg-soft);
  font-family: var(--font-mono);
  font-size: 11px;
  white-space: nowrap;
}

.calendar-panel :deep(.el-calendar) {
  border: 1px solid var(--c-border);
  border-radius: 6px;
  overflow: hidden;
}

.calendar-panel :deep(.el-calendar__header) {
  padding: 12px 14px;
  background: var(--c-bg-soft);
}

.calendar-panel :deep(.el-calendar__title) {
  color: var(--c-text);
  font-size: 15px;
  font-weight: 650;
}

.calendar-panel :deep(.el-calendar-table thead th) {
  padding: 10px 0;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 650;
  text-transform: uppercase;
}

.calendar-panel :deep(.el-calendar-day) {
  height: 122px;
  padding: 0;
}

.calendar-panel :deep(.el-calendar-table td) {
  border-color: var(--c-border);
}

.calendar-cell {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  grid-template-rows: auto 1fr;
  align-content: start;
  gap: 7px;
  width: 100%;
  min-height: 122px;
  padding: 10px;
  border: 0;
  color: var(--c-text);
  background: transparent;
  cursor: pointer;
  text-align: left;
  font-family: var(--font-ui);
  transition: background-color 120ms ease, box-shadow 120ms ease;
}

.calendar-cell:hover,
.calendar-cell.selected {
  background: rgba(50, 132, 255, 0.08);
  box-shadow: inset 0 0 0 1px rgba(50, 132, 255, 0.32);
}

.calendar-cell.today {
  background: rgba(23, 163, 74, 0.07);
}

.day-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  color: var(--c-text);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 650;
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
}

.calendar-cell.today .day-number {
  color: #ffffff;
  background: #159947;
}

.today-dot {
  justify-self: end;
  grid-column: 2;
  grid-row: 1;
  color: #13843e;
  font-size: 11px;
  font-weight: 650;
}

.event-stack {
  display: grid;
  grid-column: 1 / -1;
  gap: 5px;
  min-width: 0;
}

.event-chip,
.more-chip {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 6px;
  min-height: 22px;
  padding: 3px 7px;
  border: 1px solid currentColor;
  border-radius: 4px;
  background: var(--chip-bg);
  color: var(--chip-fg);
  font-size: 11px;
  line-height: 1.25;
}

.more-chip {
  display: inline-flex;
  justify-self: start;
  color: var(--c-text-tertiary);
  background: var(--c-bg-soft);
}

.chip-platform {
  font-weight: 650;
  white-space: nowrap;
}

.chip-title {
  overflow: hidden;
  color: currentColor;
  opacity: 0.82;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.platform-xiaohongshu {
  --chip-bg: rgba(231, 68, 76, 0.1);
  --chip-fg: #b4232b;
}

.platform-weibo {
  --chip-bg: rgba(224, 133, 31, 0.12);
  --chip-fg: #a45b10;
}

.platform-blog {
  --chip-bg: rgba(34, 112, 219, 0.11);
  --chip-fg: #1f5daa;
}

.platform-video_script {
  --chip-bg: rgba(13, 148, 136, 0.12);
  --chip-fg: #087568;
}

.platform-twitter,
.platform-other {
  --chip-bg: rgba(71, 85, 105, 0.1);
  --chip-fg: #475569;
}

.day-agenda,
.queue-list {
  display: grid;
  gap: 8px;
}

.agenda-row,
.queue-row {
  min-width: 0;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg);
}

.agenda-row {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
}

.agenda-marker {
  width: 8px;
  height: 32px;
  border-radius: 999px;
  background: var(--chip-fg);
}

.agenda-row strong,
.queue-copy strong {
  display: block;
  overflow: hidden;
  color: var(--c-text);
  font-size: 13px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agenda-row span,
.queue-copy span,
.agenda-row small,
.queue-status {
  color: var(--c-text-tertiary);
  font-size: 12px;
}

.queue-row {
  display: grid;
  grid-template-columns: 50px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 10px;
}

.queue-date {
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  border: 1px solid var(--c-border);
  border-radius: 5px;
  background: var(--c-bg-soft);
}

.queue-date strong {
  color: var(--c-text);
  font-family: var(--font-mono);
  font-size: 16px;
  line-height: 1;
}

.queue-date span {
  color: var(--c-text-tertiary);
  font-size: 11px;
}

.queue-status {
  align-self: start;
  padding: 2px 7px;
  border: 1px solid var(--c-border);
  border-radius: 999px;
  background: var(--c-bg-soft);
  white-space: nowrap;
}

.calendar-dialog :deep(.el-input-number),
.calendar-dialog :deep(.el-select),
.calendar-dialog :deep(.el-date-editor) {
  width: 100%;
}

@media (max-width: 1240px) {
  .signal-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .calendar-shell {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .calendar-page {
    padding: 16px;
  }

  .calendar-hero {
    align-items: flex-start;
    flex-direction: column;
  }

  .signal-grid {
    grid-template-columns: 1fr;
  }

  .calendar-panel,
  .side-section {
    padding: 14px;
  }

  .calendar-panel :deep(.el-calendar-day),
  .calendar-cell {
    min-height: 96px;
    height: 96px;
  }

  .chip-title {
    display: none;
  }

  .queue-row {
    grid-template-columns: 44px minmax(0, 1fr);
  }

  .queue-status {
    grid-column: 2;
    justify-self: start;
  }
}
</style>
