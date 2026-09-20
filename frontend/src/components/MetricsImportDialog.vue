<!-- Bulk-records platform numbers from a pasted or uploaded CSV; nothing is sent until every line parses. -->
<template>
  <el-dialog
    :model-value="open"
    title="导入效果数据"
    width="min(620px, calc(100vw - 32px))"
    @update:model-value="emit('update:open', $event)"
    @closed="reset"
  >
    <p class="import-hint">
      从表格粘贴或上传 CSV。首行是表头，必须包含 <code>content_id</code>、<code>platform</code>、<code>views</code>，
      <code>likes</code>、<code>comments</code>、<code>shares</code> 可选。同一内容同一平台的旧记录会被覆盖。
    </p>

    <div class="import-tools">
      <label class="import-upload">
        <input class="hidden-input" type="file" accept=".csv,.tsv,.txt,text/csv" @change="onFileSelected" />
        <span>选择 CSV 文件</span>
      </label>
      <el-button text @click="text = METRICS_CSV_TEMPLATE">填入示例</el-button>
    </div>

    <el-input
      v-model="text"
      type="textarea"
      :rows="9"
      resize="none"
      class="import-text"
      placeholder="content_id,platform,views,likes,comments,shares"
    />

    <ul v-if="parsed.errors.length" class="import-errors" role="alert">
      <li v-for="message in visibleErrors" :key="message">{{ message }}</li>
      <li v-if="parsed.errors.length > visibleErrors.length">……另有 {{ parsed.errors.length - visibleErrors.length }} 处问题</li>
    </ul>
    <p v-else-if="parsed.rows.length" class="import-ready">已识别 {{ parsed.rows.length }} 行，可以导入。</p>

    <template #footer>
      <el-button @click="emit('update:open', false)">取消</el-button>
      <el-button type="primary" :loading="importing" :disabled="!canImport" @click="submit">导入</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElDialog } from 'element-plus/es/components/dialog/index'
import { ElMessage } from 'element-plus/es/components/message/index'
import 'element-plus/es/components/dialog/style/css'
import { importContentMetrics } from '../api/metrics'
import { METRICS_CSV_TEMPLATE, parseMetricsCsv } from '../utils/metricsCsv'

const MAX_VISIBLE_ERRORS = 5

defineProps<{ open: boolean }>()
const emit = defineEmits<{ 'update:open': [value: boolean]; imported: [contentIds: number[]] }>()

const text = ref('')
const importing = ref(false)

const parsed = computed(() => (text.value.trim() ? parseMetricsCsv(text.value) : { rows: [], errors: [] }))
const visibleErrors = computed(() => parsed.value.errors.slice(0, MAX_VISIBLE_ERRORS))
// All-or-nothing on the client: importing the good half of a sheet would leave
// the user guessing which rows still need fixing.
const canImport = computed(() => parsed.value.rows.length > 0 && !parsed.value.errors.length)

async function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (file) text.value = await file.text()
}

async function submit() {
  if (!canImport.value) return
  importing.value = true
  try {
    const rows = parsed.value.rows
    const result = await importContentMetrics(rows)
    if (result.missing_content_ids.length) {
      ElMessage.warning(`已导入 ${result.recorded} 行；内容 ${result.missing_content_ids.join('、')} 不存在，已跳过。`)
    } else {
      ElMessage.success(`已导入 ${result.recorded} 行效果数据`)
    }
    emit('imported', [...new Set(rows.map(row => row.content_id))])
    emit('update:open', false)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    importing.value = false
  }
}

function reset() {
  text.value = ''
}
</script>

<style scoped>
.import-hint { margin: 0 0 14px; color: var(--c-text-secondary); font-size: 13px; line-height: 1.7; }
.import-hint code { padding: 1px 5px; border-radius: 4px; background: var(--c-bg-code); font-size: 12px; }
.import-tools { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.import-upload { padding: 6px 12px; border: 1px solid var(--c-border); border-radius: 6px; color: var(--c-text-secondary); font-size: 13px; cursor: pointer; }
.import-upload:hover { border-color: var(--c-border-strong); }
.import-upload:focus-within { border-color: var(--c-border-focus); box-shadow: 0 0 0 3px var(--c-accent-ring); }
.hidden-input { position: absolute; width: 1px; height: 1px; opacity: 0; }
.import-text :deep(textarea) { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
.import-errors { margin: 12px 0 0; padding-left: 18px; color: var(--c-fail); font-size: 12px; line-height: 1.7; }
.import-ready { margin: 12px 0 0; color: var(--c-ok); font-size: 12px; }
</style>
