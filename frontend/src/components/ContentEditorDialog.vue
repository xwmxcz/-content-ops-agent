<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElDialog } from 'element-plus/es/components/dialog/index'
import { ElMessage } from 'element-plus/es/components/message/index'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/es/components/message-box/style/css'
import { editContent, getContent, type ContentItem } from '../api/content'
import { workspaceSessionId } from '../workspaceSession'

const props = defineProps<{ open: boolean; content: ContentItem | null }>()
const emit = defineEmits<{ 'update:open': [value: boolean]; saved: [content: ContentItem] }>()
const original = ref<ContentItem | null>(null)
const title = ref('')
const body = ref('')
const tags = ref('')
const saving = ref(false)
const reloading = ref(false)
const error = ref('')
const conflict = ref(false)
let generation = 0
const parsedTags = computed(() => [...new Set(tags.value.split(/[,，\n]/).map(tag => tag.trim()).filter(Boolean))])
const dirty = computed(() => !!original.value && (
  title.value !== (original.value.title || '') || body.value !== original.value.content ||
  JSON.stringify(parsedTags.value) !== JSON.stringify(original.value.tags || [])
))
const valid = computed(() => !!body.value.trim() && title.value.length <= 500 && body.value.length <= 200_000 &&
  parsedTags.value.length <= 30 && parsedTags.value.every(tag => [...tag].length <= 50))

function fill(content: ContentItem) {
  original.value = { ...content, tags: [...(content.tags || [])] }
  title.value = content.title || ''
  body.value = content.content
  tags.value = (content.tags || []).join('，')
  error.value = ''
  conflict.value = false
}

watch(() => props.open, open => {
  generation++
  saving.value = false
  reloading.value = false
  if (open && props.content) fill(props.content)
}, { immediate: true })

async function canDiscard() {
  if (saving.value || reloading.value) return false
  if (!props.open || !dirty.value) return true
  try {
    await ElMessageBox.confirm('尚有未保存的编辑，是否放弃？', '未保存的内容', {
      confirmButtonText: '放弃编辑', cancelButtonText: '继续编辑', type: 'warning'
    })
    return true
  } catch { return false }
}

async function close() {
  if (await canDiscard()) emit('update:open', false)
}

async function save() {
  if (!original.value || saving.value || reloading.value || !valid.value || !dirty.value || conflict.value) return
  const session = workspaceSessionId.value
  const current = ++generation
  const id = original.value.id
  saving.value = true
  error.value = ''
  try {
    const saved = await editContent(id, {
      title: title.value, content: body.value, tags: parsedTags.value,
      expected_updated_at: original.value.updated_at ?? null
    })
    if (current !== generation || session !== workspaceSessionId.value) return
    fill(saved)
    emit('saved', saved)
    emit('update:open', false)
    ElMessage.success('内容已保存')
  } catch (cause) {
    if (current !== generation || session !== workspaceSessionId.value) return
    error.value = (cause as Error).message || '保存失败，请重试'
    conflict.value = (cause as { status?: number }).status === 409
  } finally {
    if (current === generation) saving.value = false
  }
}

async function reload() {
  const session = workspaceSessionId.value
  const started = generation
  const id = original.value?.id
  if (!id || !await canDiscard() || started !== generation || session !== workspaceSessionId.value || !props.open) return
  const current = ++generation
  reloading.value = true
  try {
    const latest = await getContent(id)
    if (current === generation && session === workspaceSessionId.value) fill(latest)
  } catch (cause) {
    if (current === generation && session === workspaceSessionId.value) error.value = (cause as Error).message
  } finally {
    if (current === generation) reloading.value = false
  }
}

function beforeUnload(event: BeforeUnloadEvent) {
  if (props.open && dirty.value) { event.preventDefault(); event.returnValue = '' }
}
window.addEventListener('beforeunload', beforeUnload)
onBeforeRouteLeave(canDiscard)
watch(workspaceSessionId, () => {
  generation++
  original.value = null
  title.value = body.value = tags.value = error.value = ''
  emit('update:open', false)
}, { flush: 'sync' })
onBeforeUnmount(() => { generation++; window.removeEventListener('beforeunload', beforeUnload) })
</script>

<template>
  <el-dialog class="content-editor-dialog" :model-value="open" title="手动编辑内容" top="5vh" width="min(760px, 94vw)" :before-close="close" :close-on-click-modal="false">
    <p class="editor-hint">修改保存在本地内容库。已提交的平台帖子和定时发布仍使用提交时的内容。</p>
    <div class="editor-fields">
      <label>标题<el-input v-model="title" aria-label="编辑标题" maxlength="500" :disabled="saving || reloading" /></label>
      <label>正文<el-input v-model="body" aria-label="编辑正文" type="textarea" :rows="14" :disabled="saving || reloading" /></label>
      <label>标签<el-input v-model="tags" aria-label="编辑标签" placeholder="用逗号分隔，最多 30 个，每个不超过 50 字" :disabled="saving || reloading" /></label>
    </div>
    <p v-if="error" class="editor-error" role="alert">{{ error }}</p>
    <p v-if="!valid" class="editor-error">请输入非空正文（最多 20 万字），并检查标题和标签长度。</p>
    <template #footer>
      <el-button v-if="conflict" :loading="reloading" @click="reload">重新加载最新内容</el-button>
      <el-button :disabled="saving || reloading" @click="close">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="!valid || !dirty || reloading || conflict" @click="save">保存修改</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
:global(.content-editor-dialog) { display: flex; flex-direction: column; max-height: 90vh; }
:global(.content-editor-dialog .el-dialog__body) { overflow-y: auto; min-height: 0; }
:global(.content-editor-dialog .el-dialog__header), :global(.content-editor-dialog .el-dialog__footer) { flex-shrink: 0; }
.editor-hint { margin: 0 0 18px; color: var(--c-text-secondary); line-height: 1.7; }
.editor-fields { display: grid; gap: 16px; }
.editor-fields label { display: grid; gap: 8px; }
.editor-error { color: var(--c-fail); line-height: 1.6; }
</style>
