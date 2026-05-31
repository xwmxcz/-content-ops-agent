<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Refresh, DocumentCopy } from '@element-plus/icons-vue'
import {
  getAgentMemory,
  saveAgentMemory,
  getUserMemory,
  saveUserMemory,
  searchSessions,
  refreshSnapshot,
  type MemoryFile,
  type SessionSearchHit,
} from '../api/memory'

const activeTab = ref<'edit' | 'search'>('edit')

const agentDraft = ref('')
const agentMeta = ref<MemoryFile>({ content: '', char_count: 0, char_limit: 2200 })
const agentSaving = ref(false)
const agentLoading = ref(false)

const userDraft = ref('')
const userMeta = ref<MemoryFile>({ content: '', char_count: 0, char_limit: 1375 })
const userSaving = ref(false)
const userLoading = ref(false)

const searchQuery = ref('')
const searchThread = ref('')
const searchResults = ref<SessionSearchHit[]>([])
const searching = ref(false)
const searchTouched = ref(false)

const agentCount = computed(() => agentDraft.value.length)
const agentOver = computed(() => agentCount.value > agentMeta.value.char_limit)
const userCount = computed(() => userDraft.value.length)
const userOver = computed(() => userCount.value > userMeta.value.char_limit)

async function loadAgent() {
  agentLoading.value = true
  try {
    agentMeta.value = await getAgentMemory()
    agentDraft.value = agentMeta.value.content
  } catch {
    ElMessage.error('加载 MEMORY.md 失败')
  } finally {
    agentLoading.value = false
  }
}

async function loadUser() {
  userLoading.value = true
  try {
    userMeta.value = await getUserMemory()
    userDraft.value = userMeta.value.content
  } catch {
    ElMessage.error('加载 USER.md 失败')
  } finally {
    userLoading.value = false
  }
}

async function persistAgent() {
  if (agentOver.value) {
    ElMessage.warning('MEMORY.md 超过字符上限')
    return
  }
  agentSaving.value = true
  try {
    agentMeta.value = await saveAgentMemory(agentDraft.value)
    agentDraft.value = agentMeta.value.content
    ElMessage.success('MEMORY.md 已保存(新会话生效)')
  } catch (err: any) {
    const detail = err?.response?.data?.detail || '保存失败'
    ElMessage.error(detail)
  } finally {
    agentSaving.value = false
  }
}

async function persistUser() {
  if (userOver.value) {
    ElMessage.warning('USER.md 超过字符上限')
    return
  }
  userSaving.value = true
  try {
    userMeta.value = await saveUserMemory(userDraft.value)
    userDraft.value = userMeta.value.content
    ElMessage.success('USER.md 已保存(新会话生效)')
  } catch (err: any) {
    const detail = err?.response?.data?.detail || '保存失败'
    ElMessage.error(detail)
  } finally {
    userSaving.value = false
  }
}

async function invalidateAllSnapshots() {
  try {
    await refreshSnapshot()
    ElMessage.success('已清空冻结快照,下一条消息会重新加载')
  } catch {
    ElMessage.error('清空快照失败')
  }
}

async function runSearch() {
  if (!searchQuery.value.trim()) {
    searchResults.value = []
    return
  }
  searching.value = true
  searchTouched.value = true
  try {
    const r = await searchSessions(searchQuery.value, 30, searchThread.value || undefined)
    searchResults.value = r.messages
  } catch {
    ElMessage.error('搜索失败')
  } finally {
    searching.value = false
  }
}

onMounted(() => {
  loadAgent()
  loadUser()
})
</script>

<template>
  <div class="memory-page">
    <header class="page-header">
      <h2>记忆管理</h2>
      <p class="subtitle">Hermes 风格 4 层记忆:MEMORY.md(Agent 笔记) + USER.md(用户画像) + 会话全文检索 + 上下文压缩</p>
    </header>

    <el-tabs v-model="activeTab" class="mem-tabs">
      <el-tab-pane label="编辑" name="edit">
        <div class="edit-grid">
          <section v-loading="agentLoading" class="pane">
            <div class="pane-head">
              <div>
                <h3>MEMORY.md</h3>
                <p class="pane-subtitle">Agent 自己的笔记 — 项目惯例、工具坑、品牌口径</p>
              </div>
              <span :class="['count', { over: agentOver }]">{{ agentCount }} / {{ agentMeta.char_limit }}</span>
            </div>
            <el-input
              v-model="agentDraft"
              type="textarea"
              :rows="18"
              resize="none"
              placeholder="例如:&#10;# 品牌口径&#10;简洁口语化中文,不堆砌 emoji&#10;§&#10;# 工具坑&#10;refine_content 时务必先 view_content 确认 id"
            />
            <div class="pane-actions">
              <el-button :icon="Refresh" plain @click="loadAgent">重新加载</el-button>
              <el-button type="primary" :loading="agentSaving" :disabled="agentOver" @click="persistAgent">
                保存
              </el-button>
            </div>
          </section>

          <section v-loading="userLoading" class="pane">
            <div class="pane-head">
              <div>
                <h3>USER.md</h3>
                <p class="pane-subtitle">用户画像 — 称呼、语言、风格偏好</p>
              </div>
              <span :class="['count', { over: userOver }]">{{ userCount }} / {{ userMeta.char_limit }}</span>
            </div>
            <el-input
              v-model="userDraft"
              type="textarea"
              :rows="18"
              resize="none"
              placeholder="例如:&#10;偏好简洁口语化中文&#10;§&#10;不喜欢 emoji&#10;§&#10;主理品牌叫 TechFlow"
            />
            <div class="pane-actions">
              <el-button :icon="Refresh" plain @click="loadUser">重新加载</el-button>
              <el-button type="primary" :loading="userSaving" :disabled="userOver" @click="persistUser">
                保存
              </el-button>
            </div>
          </section>
        </div>

        <div class="freeze-banner">
          <p>
            两份文件在每个对话开始时被加载到 system prompt 后冻结。修改后,新开对话才会生效。
          </p>
          <el-button :icon="DocumentCopy" size="small" plain @click="invalidateAllSnapshots">
            立即清空所有冻结快照
          </el-button>
        </div>
      </el-tab-pane>

      <el-tab-pane label="会话搜索" name="search">
        <div class="search-form">
          <el-input
            v-model="searchQuery"
            placeholder="跨会话搜索消息(支持 ≥ 3 字中文,2 字走 LIKE)"
            :prefix-icon="Search"
            clearable
            style="flex: 1"
            @keyup.enter="runSearch"
          />
          <el-input
            v-model="searchThread"
            placeholder="限定 thread_id(可选)"
            clearable
            style="width: 220px"
            @keyup.enter="runSearch"
          />
          <el-button type="primary" :loading="searching" @click="runSearch">搜索</el-button>
        </div>

        <div v-loading="searching" class="search-results">
          <div v-if="!searchTouched && !searching" class="empty-state">输入关键词后按回车开始检索</div>
          <div v-else-if="searchResults.length === 0 && !searching" class="empty-state">没有命中任何消息</div>
          <div v-for="hit in searchResults" :key="hit.id" class="hit-card">
            <div class="hit-meta">
              <el-tag size="small" :type="hit.role === 'user' ? 'info' : 'success'">{{ hit.role }}</el-tag>
              <span class="thread">thread: {{ hit.thread_id }}</span>
              <span v-if="hit.created_at" class="date">{{ hit.created_at.slice(0, 16).replace('T', ' ') }}</span>
            </div>
            <div class="hit-content">{{ hit.content }}</div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.memory-page {
  padding: 24px 32px;
  max-width: 1200px;
}
.page-header h2 {
  margin: 0 0 4px;
  color: var(--c-text);
}
.subtitle {
  color: var(--c-text-secondary);
  margin: 0 0 20px;
  font-size: 13px;
}
.mem-tabs {
  margin-top: 12px;
}
.edit-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
@media (max-width: 1000px) {
  .edit-grid { grid-template-columns: 1fr; }
}
.pane {
  border: 1px solid var(--c-border);
  border-radius: 10px;
  padding: 16px;
  background: var(--c-bg);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.pane-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.pane-head h3 {
  margin: 0;
  font-size: 15px;
  color: var(--c-text);
}
.pane-subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--c-text-secondary);
}
.count {
  font-size: 12px;
  color: var(--c-text-secondary);
  font-variant-numeric: tabular-nums;
}
.count.over {
  color: #e54d4d;
  font-weight: 600;
}
.pane-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.freeze-banner {
  margin-top: 18px;
  padding: 12px 16px;
  border: 1px dashed var(--c-border);
  border-radius: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: var(--c-text-secondary);
}
.freeze-banner p {
  margin: 0;
}
.search-form {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.search-results {
  min-height: 200px;
}
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--c-text-secondary);
}
.hit-card {
  border: 1px solid var(--c-border);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 10px;
  background: var(--c-bg);
}
.hit-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.hit-meta {
  display: flex;
  gap: 12px;
  align-items: center;
  font-size: 12px;
  color: var(--c-text-secondary);
  margin-bottom: 6px;
}
.thread { font-family: 'JetBrains Mono', monospace; }
.hit-content {
  font-size: 14px;
  line-height: 1.6;
  color: var(--c-text);
  white-space: pre-wrap;
}
</style>
