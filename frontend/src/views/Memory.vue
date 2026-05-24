<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Delete, Refresh, Edit } from '@element-plus/icons-vue'
import { getMemories, createMemory, deleteMemory, updateMemory, searchMemories, type Memory } from '../api/memory'

const memories = ref<Memory[]>([])
const loading = ref(false)
const searchQuery = ref('')
const filterCategory = ref('')
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const editingMemory = ref<Memory | null>(null)

const form = reactive({
  content: '',
  category: 'fact',
  importance: 0.5,
})

const editForm = reactive({
  content: '',
  category: 'fact',
  importance: 0.5,
})

const categoryOptions = [
  { value: '', label: '全部' },
  { value: 'preference', label: '偏好' },
  { value: 'fact', label: '事实' },
  { value: 'context', label: '上下文' },
  { value: 'instruction', label: '指令' },
]

const categoryTagType = (cat: string) => {
  const map: Record<string, string> = {
    preference: 'success',
    fact: '',
    context: 'warning',
    instruction: 'danger',
  }
  return map[cat] || 'info'
}

const categoryLabel = (cat: string) => {
  const map: Record<string, string> = {
    preference: '偏好',
    fact: '事实',
    context: '上下文',
    instruction: '指令',
  }
  return map[cat] || cat
}

async function load() {
  loading.value = true
  try {
    const cat = filterCategory.value || undefined
    memories.value = await getMemories(cat)
  } catch (e: any) {
    ElMessage.error('加载记忆失败')
  } finally {
    loading.value = false
  }
}

async function handleSearch() {
  if (!searchQuery.value.trim()) {
    await load()
    return
  }
  loading.value = true
  try {
    const cat = filterCategory.value || undefined
    const result = await searchMemories(searchQuery.value, cat)
    memories.value = result.memories as Memory[]
  } catch (e: any) {
    ElMessage.error('搜索失败')
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  if (!form.content.trim()) {
    ElMessage.warning('请输入记忆内容')
    return
  }
  try {
    await createMemory({
      content: form.content,
      category: form.category,
      importance: form.importance,
    })
    ElMessage.success('记忆已保存')
    showCreateDialog.value = false
    form.content = ''
    form.category = 'fact'
    form.importance = 0.5
    await load()
  } catch (e: any) {
    ElMessage.error('保存失败')
  }
}

async function handleDelete(mem: Memory) {
  try {
    await ElMessageBox.confirm(
      `确定删除这条记忆？\n\n"${mem.content.slice(0, 50)}..."`,
      '删除确认',
      { type: 'warning' }
    )
    await deleteMemory(mem.id)
    ElMessage.success('已删除')
    await load()
  } catch {
    // cancelled
  }
}

function handleEdit(mem: Memory) {
  editingMemory.value = mem
  editForm.content = mem.content
  editForm.category = mem.category
  editForm.importance = mem.importance
  showEditDialog.value = true
}

async function handleUpdate() {
  if (!editingMemory.value) return
  if (!editForm.content.trim()) {
    ElMessage.warning('内容不能为空')
    return
  }
  try {
    await updateMemory(editingMemory.value.id, {
      content: editForm.content,
      category: editForm.category,
      importance: editForm.importance,
    })
    ElMessage.success('记忆已更新')
    showEditDialog.value = false
    editingMemory.value = null
    await load()
  } catch (e: any) {
    ElMessage.error('更新失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="memory-page">
    <header class="page-header">
      <h2>记忆管理</h2>
      <p class="subtitle">Agent 的长期记忆，跨会话自动召回</p>
    </header>

    <div class="toolbar">
      <div class="toolbar-left">
        <el-input
          v-model="searchQuery"
          placeholder="语义搜索记忆..."
          :prefix-icon="Search"
          clearable
          style="width: 280px"
          @keyup.enter="handleSearch"
          @clear="load"
        />
        <el-select v-model="filterCategory" placeholder="分类" style="width: 120px" @change="load">
          <el-option
            v-for="opt in categoryOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
      </div>
      <el-button type="primary" :icon="Plus" @click="showCreateDialog = true">添加记忆</el-button>
    </div>

    <div v-loading="loading" class="memory-list">
      <div v-if="memories.length === 0 && !loading" class="empty-state">
        <p>暂无记忆。在 Chat 中对 Agent 说"记住..."，或点击上方按钮手动添加。</p>
      </div>
      <div v-for="mem in memories" :key="mem.id" class="memory-card">
        <div class="memory-body">
          <div class="memory-content">{{ mem.content }}</div>
          <div class="memory-meta">
            <el-tag :type="categoryTagType(mem.category)" size="small">
              {{ categoryLabel(mem.category) }}
            </el-tag>
            <span class="importance">重要度: {{ (mem.importance * 100).toFixed(0) }}%</span>
            <span class="access">访问 {{ mem.access_count }} 次</span>
            <span v-if="mem.created_at" class="date">{{ mem.created_at.slice(0, 10) }}</span>
          </div>
        </div>
        <div class="memory-actions">
          <el-button
            type="primary"
            :icon="Edit"
            size="small"
            plain
            @click="handleEdit(mem)"
          >编辑</el-button>
          <el-button
            type="danger"
            :icon="Delete"
            size="small"
            plain
            @click="handleDelete(mem)"
          >删除</el-button>
        </div>
      </div>
    </div>

    <el-dialog v-model="showCreateDialog" title="添加记忆" width="500px">
      <el-form label-position="top">
        <el-form-item label="内容">
          <el-input
            v-model="form.content"
            type="textarea"
            :rows="3"
            placeholder="例如：用户喜欢简洁风格"
          />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" style="width: 100%">
            <el-option label="偏好" value="preference" />
            <el-option label="事实" value="fact" />
            <el-option label="上下文" value="context" />
            <el-option label="指令" value="instruction" />
          </el-select>
        </el-form-item>
        <el-form-item label="重要度">
          <el-slider v-model="form.importance" :min="0" :max="1" :step="0.1" show-stops />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showEditDialog" title="编辑记忆" width="500px">
      <el-form label-position="top">
        <el-form-item label="内容">
          <el-input
            v-model="editForm.content"
            type="textarea"
            :rows="3"
          />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="editForm.category" style="width: 100%">
            <el-option label="偏好" value="preference" />
            <el-option label="事实" value="fact" />
            <el-option label="上下文" value="context" />
            <el-option label="指令" value="instruction" />
          </el-select>
        </el-form-item>
        <el-form-item label="重要度">
          <el-slider v-model="editForm.importance" :min="0" :max="1" :step="0.1" show-stops />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="handleUpdate">更新</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.memory-page {
  padding: 24px 32px;
  max-width: 900px;
}
.page-header h2 {
  margin: 0 0 4px;
  color: var(--c-text);
}
.subtitle {
  color: var(--c-text-secondary);
  margin: 0 0 20px;
  font-size: 14px;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  gap: 12px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.memory-list {
  min-height: 200px;
}
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--c-text-secondary);
}
.memory-card {
  display: flex;
  align-items: center;
  padding: 16px;
  border: 1px solid var(--c-border);
  border-radius: 8px;
  margin-bottom: 12px;
  background: var(--c-bg);
  transition: box-shadow 0.2s;
}
.memory-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.memory-body {
  flex: 1;
  min-width: 0;
}
.memory-content {
  font-size: 14px;
  line-height: 1.6;
  color: var(--c-text);
  margin-bottom: 8px;
}
.memory-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: var(--c-text-secondary);
}
.memory-actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-left: 12px;
}
.memory-card:hover .memory-actions {
  opacity: 1;
}
</style>
