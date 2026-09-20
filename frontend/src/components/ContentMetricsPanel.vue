<!-- Records one platform's current numbers for a piece of content, and lists what is already on file. -->
<template>
  <details class="detail-block metrics-disclosure">
    <summary class="block-head">
      <div>
        <h3>效果数据</h3>
      </div>
      <span class="metrics-badge" :class="{ empty: !metrics.length }">{{ summaryLabel }}</span>
    </summary>

    <p class="metrics-hint">填写平台后台显示的累计数字。同一平台再次保存会覆盖上一次的记录，统计页和对话助手的效果分析都基于这里的数据。</p>

    <div v-if="metrics.length" class="metrics-list">
      <article v-for="row in metrics" :key="row.id" class="metrics-row">
        <button type="button" class="metrics-platform" :title="`载入 ${row.platform} 的数字进行修改`" @click="edit(row)">
          {{ row.platform }}
        </button>
        <span><b>{{ formatCount(row.views) }}</b> 浏览</span>
        <span><b>{{ formatCount(row.likes) }}</b> 点赞</span>
        <span><b>{{ formatCount(row.comments) }}</b> 评论</span>
        <span><b>{{ formatCount(row.shares) }}</b> 分享</span>
        <span class="metrics-rate">互动率 {{ formatRate(row.engagement_rate) }}</span>
      </article>
    </div>

    <form class="metrics-form" @submit.prevent="save">
      <label class="metrics-field metrics-field-wide">
        <span>平台</span>
        <el-input v-model="form.platform" placeholder="例如 xiaohongshu" maxlength="50" />
      </label>
      <label v-for="field in COUNT_FIELDS" :key="field.key" class="metrics-field">
        <span>{{ field.label }}</span>
        <el-input v-model="form[field.key]" type="number" min="0" step="1" inputmode="numeric" />
      </label>
      <p v-if="attempted && validationError" class="metrics-error" role="alert">{{ validationError }}</p>
      <div class="metrics-actions">
        <el-button type="primary" native-type="submit" :loading="saving">保存数据</el-button>
      </div>
    </form>
  </details>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index'
import { getContentMetrics, recordContentMetrics, type ContentMetrics } from '../api/metrics'

type CountKey = 'views' | 'likes' | 'comments' | 'shares'

const COUNT_FIELDS: Array<{ key: CountKey; label: string }> = [
  { key: 'views', label: '浏览' },
  { key: 'likes', label: '点赞' },
  { key: 'comments', label: '评论' },
  { key: 'shares', label: '分享' }
]
const METRIC_MAX = 2_000_000_000

// `refreshKey` changes when the numbers were written elsewhere (a CSV import), so
// the list reloads without remounting: a remount would collapse the open panel.
const props = defineProps<{ contentId: number; defaultPlatform?: string; refreshKey?: number }>()

const metrics = ref<ContentMetrics[]>([])
const saving = ref(false)
// A blank form is invalid by construction, so the message waits for a save
// attempt instead of greeting every newly opened piece of content with an error.
const attempted = ref(false)
// Inputs hold strings: an emptied number field is '' rather than 0, and that
// difference is what lets a blank field be reported instead of saved as zero.
const form = reactive<Record<CountKey | 'platform', string>>({
  platform: '',
  views: '',
  likes: '0',
  comments: '0',
  shares: '0'
})

const summaryLabel = computed(() => (metrics.value.length ? `已记录 ${metrics.value.length} 个平台` : '尚未记录'))

const validationError = computed(() => {
  if (!/^[\p{L}\p{N}_-]{1,50}$/u.test(form.platform.trim())) return '平台名称只能包含字母、数字、下划线或连字符。'
  for (const field of COUNT_FIELDS) {
    const raw = String(form[field.key]).trim()
    if (!/^\d+$/.test(raw) || Number(raw) > METRIC_MAX) return `${field.label}必须是非负整数。`
  }
  return ''
})

watch(
  () => [props.contentId, props.refreshKey] as const,
  async ([contentId], previous) => {
    // A half-typed form survives a reload of the same content.
    if (contentId !== previous?.[0]) {
      metrics.value = []
      reset()
    }
    try {
      const loaded = await getContentMetrics(contentId)
      // The user may have switched content while this was in flight.
      if (contentId === props.contentId) metrics.value = loaded
    } catch (error) {
      ElMessage.error((error as Error).message)
    }
  },
  { immediate: true }
)

function reset() {
  attempted.value = false
  form.platform = props.defaultPlatform ?? ''
  form.views = ''
  form.likes = '0'
  form.comments = '0'
  form.shares = '0'
}

function edit(row: ContentMetrics) {
  form.platform = row.platform ?? ''
  for (const field of COUNT_FIELDS) form[field.key] = String(row[field.key])
}

async function save() {
  attempted.value = true
  if (validationError.value) return
  saving.value = true
  try {
    const saved = await recordContentMetrics(props.contentId, {
      platform: form.platform.trim().toLowerCase(),
      views: Number(form.views),
      likes: Number(form.likes),
      comments: Number(form.comments),
      shares: Number(form.shares)
    })
    metrics.value = [...metrics.value.filter(row => row.platform !== saved.platform), saved].sort((a, b) =>
      (a.platform ?? '').localeCompare(b.platform ?? '')
    )
    ElMessage.success('效果数据已保存')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    saving.value = false
  }
}

function formatCount(value: number) {
  return value.toLocaleString('zh-CN')
}

function formatRate(rate: number) {
  return `${(rate * 100).toFixed(1)}%`
}
</script>

<style scoped>
.detail-block { padding: 24px 0; border-top: 1px solid var(--c-border-soft); }
.block-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.block-head h3 { margin: 0; font-size: 14px; font-weight: 600; }
/* Same disclosure affordance as the publish block it sits under. */
.metrics-disclosure > summary { cursor: pointer; list-style: none; margin: 0; }
.metrics-disclosure > summary::-webkit-details-marker { display: none; }
.metrics-disclosure > summary::after { content: '+'; color: var(--c-text-tertiary); font-size: 20px; }
.metrics-disclosure[open] > summary { margin-bottom: 20px; }
.metrics-disclosure[open] > summary::after { content: '−'; }
.metrics-badge { margin-left: auto; padding: 3px 10px; border-radius: 999px; background: var(--c-bg-soft); color: var(--c-text-secondary); font-size: 12px; }
.metrics-badge.empty { color: var(--c-text-tertiary); }
.metrics-hint { margin: 0 0 16px; color: var(--c-text-tertiary); font-size: 12px; line-height: 1.6; }
.metrics-list { display: grid; gap: 8px; margin-bottom: 18px; }
.metrics-row { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 16px; padding: 10px 12px; border: 1px solid var(--c-border-soft); border-radius: 8px; font-size: 12px; color: var(--c-text-secondary); }
.metrics-row b { color: var(--c-text); font-weight: 600; font-variant-numeric: tabular-nums; }
.metrics-platform { padding: 0; border: 0; background: none; color: var(--c-accent); font: inherit; font-weight: 600; cursor: pointer; }
.metrics-platform:hover { text-decoration: underline; }
.metrics-rate { margin-left: auto; }
.metrics-form { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px 16px; }
.metrics-field { display: grid; gap: 8px; min-width: 0; }
.metrics-field > span { color: var(--c-text-tertiary); font-size: 11px; }
.metrics-field-wide, .metrics-error, .metrics-actions { grid-column: 1 / -1; }
.metrics-error { margin: 0; color: var(--c-fail); font-size: 12px; }

@media (max-width: 640px) {
  .metrics-form { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .metrics-rate { margin-left: 0; }
}
</style>
