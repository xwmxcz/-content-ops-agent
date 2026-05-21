<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1 class="page-title">发布日历</h1>
        <p class="page-subtitle">管理内容发布日期和平台计划。</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="dialog = true">添加计划</el-button>
    </div>

    <section class="section">
      <el-calendar>
        <template #date-cell="{ data }">
          <div class="calendar-cell">
            <span>{{ data.day.split('-').slice(2).join('') }}</span>
            <el-tag v-for="event in eventsByDate[data.day]" :key="event.event_id" size="small" effect="plain">
              {{ event.platform }}
            </el-tag>
          </div>
        </template>
      </el-calendar>
    </section>

    <el-dialog v-model="dialog" title="添加发布计划" width="420px">
      <el-form label-position="top">
        <el-form-item label="内容 ID">
          <el-input-number v-model="form.content_id" :min="1" />
        </el-form-item>
        <el-form-item label="平台">
          <el-input v-model="form.platform" placeholder="xiaohongshu / weibo / blog" />
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="form.scheduled_date" value-format="YYYY-MM-DD" type="date" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index'
import { Plus } from '@element-plus/icons-vue'
import { createEvent, getEvents, type CalendarEvent } from '../api/calendar'

const events = ref<CalendarEvent[]>([])
const dialog = ref(false)
const form = reactive({ content_id: 1, platform: 'xiaohongshu', scheduled_date: '' })

const eventsByDate = computed(() => {
  const grouped: Record<string, CalendarEvent[]> = {}
  for (const event of events.value) {
    grouped[event.scheduled_date] ||= []
    grouped[event.scheduled_date].push(event)
  }
  return grouped
})

async function load() {
  events.value = await getEvents(60)
}

async function save() {
  try {
    await createEvent(form)
    ElMessage.success('发布计划已保存')
    dialog.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(load)
</script>

<style scoped>
.calendar-cell {
  min-height: 72px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

.calendar-cell span {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--c-text);
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
}
</style>
