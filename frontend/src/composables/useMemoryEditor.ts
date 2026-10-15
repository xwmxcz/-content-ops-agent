import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import type { MemoryFile } from '../api/memory'
import { workspaceSessionId, workspaceSessionReady } from '../workspaceSession'

export function useMemoryEditor(
  name: string,
  limit: number,
  read: () => Promise<MemoryFile>,
  write: (content: string, expectedEtag?: string) => Promise<MemoryFile>
) {
  const draft = ref('')
  const meta = ref<MemoryFile>({ content: '', char_count: 0, char_limit: limit })
  const loading = ref(false)
  const saving = ref(false)
  const loaded = ref(false)
  const error = ref('')
  let generation = 0
  // Python counts Unicode code points; JS string.length counts UTF-16 units.
  const count = computed(() => [...draft.value].length)
  const over = computed(() => count.value > meta.value.char_limit)
  const dirty = computed(() => loaded.value && draft.value !== meta.value.content)

  async function load() {
    if (loading.value || saving.value || !workspaceSessionReady.value) return
    const session = workspaceSessionId.value
    const started = generation
    if (dirty.value) {
      try {
        await ElMessageBox.confirm('重新加载会放弃尚未保存的记忆修改。', '重新加载记忆', {
          confirmButtonText: '重新加载', cancelButtonText: '继续编辑', type: 'warning'
        })
      } catch { return }
    }
    if (session !== workspaceSessionId.value || started !== generation || loading.value || saving.value) return
    const current = ++generation
    const previousDraft = draft.value
    loading.value = true
    error.value = ''
    try {
      const result = await read()
      if (current !== generation || session !== workspaceSessionId.value) return
      meta.value = result
      if (draft.value === previousDraft) draft.value = result.content
      loaded.value = true
    } catch (cause) {
      if (current === generation && session === workspaceSessionId.value) error.value = (cause as Error).message || `加载 ${name} 失败`
    } finally {
      if (current === generation) loading.value = false
    }
  }

  async function save() {
    if (!loaded.value || loading.value || saving.value || over.value || !dirty.value) return
    const session = workspaceSessionId.value
    const current = ++generation
    const submitted = draft.value
    const expectedEtag = meta.value.etag
    saving.value = true
    error.value = ''
    try {
      const result = expectedEtag !== undefined ? await write(submitted, expectedEtag) : await write(submitted)
      if (current !== generation || session !== workspaceSessionId.value) return
      meta.value = result
      // Edits typed while the save was in flight remain unsaved in the editor.
      if (draft.value === submitted) draft.value = result.content
      ElMessage.success(`${name} 已保存（新会话生效）`)
    } catch (cause) {
      if (current === generation && session === workspaceSessionId.value) error.value = (cause as Error).message || '保存失败，请重试'
    } finally {
      if (current === generation) saving.value = false
    }
  }

  watch([workspaceSessionId, workspaceSessionReady], ([, ready]) => {
    generation++
    draft.value = ''
    meta.value = { content: '', char_count: 0, char_limit: limit }
    loaded.value = loading.value = saving.value = false
    error.value = ''
    if (ready) void load()
  }, { immediate: true, flush: 'sync' })
  onBeforeUnmount(() => { generation++ })
  return reactive({ draft, meta, loading, saving, loaded, error, count, over, dirty, load, save })
}
