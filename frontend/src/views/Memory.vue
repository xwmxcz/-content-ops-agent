<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { vLoading } from 'element-plus/es/components/loading/index'
import { ElMessage } from 'element-plus/es/components/message/index'
import { ElTabPane, ElTabs } from 'element-plus/es/components/tabs/index'
import { ElTag } from 'element-plus/es/components/tag/index'
import 'element-plus/es/components/loading/style/css'
import 'element-plus/es/components/tabs/style/css'
import 'element-plus/es/components/tag/style/css'
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
      <h1>让每次创作，更懂你。</h1>
      <p class="subtitle">记下品牌口径与写作偏好，让内容助手保持一致的表达。</p>
    </header>

    <el-tabs v-model="activeTab" class="mem-tabs">
      <el-tab-pane label="长期记忆" name="edit">
        <div class="edit-grid">
          <section v-loading="agentLoading" class="pane">
            <div class="pane-head">
              <div>
                <span class="file-label">MEMORY.md</span>
                <h3>工作笔记</h3>
                <p class="pane-subtitle">项目惯例、品牌口径，以及值得记住的经验。</p>
              </div>
              <span :class="['count', { over: agentOver }]">{{ agentCount }} / {{ agentMeta.char_limit }}</span>
            </div>
            <el-input
              v-model="agentDraft"
              type="textarea"
              :rows="18"
              resize="none"
              placeholder="# 品牌口径&#10;用简洁、自然的中文表达。&#10;&#10;# 项目约定&#10;在这里记录内容规范与工作经验…"
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
                <span class="file-label">USER.md</span>
                <h3>我的偏好</h3>
                <p class="pane-subtitle">如何称呼你，你喜欢的语言与写作风格。</p>
              </div>
              <span :class="['count', { over: userOver }]">{{ userCount }} / {{ userMeta.char_limit }}</span>
            </div>
            <el-input
              v-model="userDraft"
              type="textarea"
              :rows="18"
              resize="none"
              placeholder="# 关于我&#10;我负责的品牌是…&#10;&#10;# 写作偏好&#10;喜欢简洁口语化的表达，少用表情符号。"
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
            <strong>保存后，新会话会自动使用这些记忆。</strong>
            <span>若要更新已有会话，点击右侧按钮；下一条消息会重新加载。</span>
          </p>
          <el-button :icon="DocumentCopy" size="small" plain @click="invalidateAllSnapshots">
            更新已有会话记忆
          </el-button>
        </div>
      </el-tab-pane>

      <el-tab-pane label="会话搜索" name="search">
        <div class="search-form">
          <el-input
            v-model="searchQuery"
            placeholder="搜索曾经聊过的内容…"
            :prefix-icon="Search"
            clearable
            class="search-keyword"
            @keyup.enter="runSearch"
          />
          <el-input
            v-model="searchThread"
            placeholder="会话 ID（可选）"
            clearable
            class="search-thread"
            @keyup.enter="runSearch"
          />
          <el-button type="primary" :loading="searching" @click="runSearch">搜索</el-button>
        </div>

        <div v-loading="searching" class="search-results">
          <div v-if="!searchTouched && !searching" class="empty-state"><strong>让过去的想法，再次派上用场。</strong><span>输入关键词，找回聊过的选题、草稿与灵感。</span></div>
          <div v-else-if="searchResults.length === 0 && !searching" class="empty-state"><strong>还没有找到相关消息</strong><span>试试更短的关键词，或清除会话 ID 后搜索。</span></div>
          <div v-for="hit in searchResults" :key="hit.id" class="hit-card">
            <div class="hit-meta">
              <el-tag size="small" :type="hit.role === 'user' ? 'info' : 'success'">{{ hit.role === 'user' ? '我' : '内容助手' }}</el-tag>
              <span class="thread">会话 {{ hit.thread_id }}</span>
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
  width: min(100%, 1440px);
  margin: 0 auto;
  padding: 32px;
}

.page-header {
  display: block;
  margin-bottom: 28px;
}

.page-header h1 {
  margin: 0 0 10px;
  color: var(--c-text);
  font-family: var(--font-display);
  font-size: var(--fs-h1);
  line-height: 1.3;
  letter-spacing: -.04em;
}

.subtitle {
  color: var(--c-text-secondary);
  margin: 0;
  font-size: 13px;
  line-height: 1.8;
}

.mem-tabs :deep(.el-tabs__header) {
  margin-bottom: 24px;
}

.mem-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background: var(--c-border);
}

.mem-tabs :deep(.el-tabs__item) {
  height: 46px;
  padding-inline: 24px;
  font-size: 14px;
}

.mem-tabs :deep(.el-tabs__active-bar) {
  height: 3px;
  border-radius: var(--r-pill);
}

.edit-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 24px;
}

.pane {
  min-width: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--c-border);
  border-radius: var(--r-card);
  background: var(--c-surface);
  box-shadow: var(--shadow-panel);
  overflow: hidden;
}
.pane-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 24px 26px 20px;
  border-bottom: 1px solid var(--c-border-soft);
}

.file-label {
  color: var(--c-text-tertiary);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: .06em;
}

.pane-head h3 {
  margin: 6px 0 8px;
  color: var(--c-text);
  font-family: var(--font-editorial);
  font-size: 23px;
  font-weight: 500;
}

.pane-subtitle {
  margin: 0;
  color: var(--c-text-secondary);
  font-size: 12px;
  line-height: 1.7;
}

.count {
  flex-shrink: 0;
  margin-top: 4px;
  padding: 4px 8px;
  border-radius: var(--r-pill);
  background: var(--c-bg-soft);
  color: var(--c-text-tertiary);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.count.over {
  background: var(--c-fail-soft);
  color: var(--c-fail);
  font-weight: 600;
}

.pane :deep(.el-textarea) {
  padding: 16px 12px 0;
}

.pane :deep(.el-textarea__inner) {
  padding: 10px 14px;
  border-radius: var(--r-control);
  box-shadow: none;
  color: var(--c-text-secondary);
  background: var(--c-surface);
  font-family: var(--font-ui);
  font-size: 13px;
  line-height: 1.9;
}
.pane :deep(.el-textarea__inner:focus) {
  box-shadow: 0 0 0 1px var(--c-accent) inset;
}

.pane-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 16px 24px 22px;
}

.pane-actions :deep(.el-button--primary) {
  min-width: 92px;
}

.freeze-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 24px;
  margin-top: 24px;
  padding: 18px 22px;
  border-radius: var(--r-control);
  background: var(--c-accent-soft);
  color: var(--c-text-secondary);
}

.freeze-banner p {
  display: grid;
  gap: 5px;
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
}

.freeze-banner strong {
  color: var(--c-accent);
  font-weight: 500;
}

.freeze-banner span {
  color: var(--c-text-secondary);
  font-size: 11px;
}

.freeze-banner :deep(.el-button) {
  flex-shrink: 0;
}

.search-form {
  display: flex;
  gap: 12px;
  padding: 20px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-card);
  background: var(--c-surface);
}

.search-keyword {
  flex: 1;
}

.search-thread {
  width: 220px;
}

.search-results {
  min-height: 320px;
  margin-top: 20px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 12px;
  min-height: 320px;
  padding: 40px 20px;
  color: var(--c-text-tertiary);
  text-align: center;
}

.empty-state strong {
  color: var(--c-text-secondary);
  font-family: var(--font-editorial);
  font-size: 22px;
  font-weight: 500;
}

.empty-state span {
  font-size: 13px;
}

.hit-card {
  padding: 22px 24px;
  margin-bottom: 14px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-card);
  background: var(--c-surface);
}

.hit-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 14px;
  margin-bottom: 14px;
  color: var(--c-text-tertiary);
  font-size: 11px;
}

.thread {
  overflow-wrap: anywhere;
}

.date {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}

.hit-content {
  color: var(--c-text);
  font-size: 14px;
  line-height: 1.85;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}


@media (max-width: 1100px) {
  .edit-grid {
    gap: 16px;
  }

  .pane-head {
    flex-wrap: wrap;
    padding: 20px;
  }

  .pane-actions {
    padding: 16px 20px 20px;
  }

}

@media (max-width: 820px) {
  .memory-page {
    padding: 20px 16px;
  }

  .edit-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .freeze-banner {
    align-items: flex-start;
    flex-direction: column;
    gap: 14px;
    padding: 18px;
  }

  .search-form {
    flex-wrap: wrap;
    padding: 16px;
    gap: 10px;
  }

  .search-keyword {
    flex-basis: 100%;
  }

  .search-thread {
    flex: 1;
    width: auto;
    min-width: 0;
  }

  .hit-card {
    padding: 18px;
  }

  .date {
    margin-left: 0;
  }

}
</style>
