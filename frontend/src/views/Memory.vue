<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { vLoading } from 'element-plus/es/components/loading/index'
import { ElMessage } from 'element-plus/es/components/message/index'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ElTabPane, ElTabs } from 'element-plus/es/components/tabs/index'
import { ElTag } from 'element-plus/es/components/tag/index'
import 'element-plus/es/components/loading/style/css'
import 'element-plus/es/components/tabs/style/css'
import 'element-plus/es/components/tag/style/css'
import 'element-plus/es/components/message-box/style/css'
import { useMemoryEditor } from '../composables/useMemoryEditor'
import { workspaceSessionId } from '../workspaceSession'
import { Search, Refresh, DocumentCopy } from '@element-plus/icons-vue'
import {
  getAgentMemory,
  saveAgentMemory,
  getUserMemory,
  saveUserMemory,
  searchSessions,
  refreshSnapshot,
  type SessionSearchHit,
} from '../api/memory'

const activeTab = ref<'edit' | 'search'>('edit')

const agent = useMemoryEditor('MEMORY.md', 2200, getAgentMemory, saveAgentMemory)
const user = useMemoryEditor('USER.md', 1375, getUserMemory, saveUserMemory)

const searchQuery = ref('')
const searchThread = ref('')
const searchResults = ref<SessionSearchHit[]>([])
const searching = ref(false)
const searchTouched = ref(false)
const searchError = ref('')
const refreshing = ref(false)
let searchVersion = 0
let disposed = false

async function invalidateAllSnapshots() {
  if (refreshing.value) return
  const session = workspaceSessionId.value
  refreshing.value = true
  try {
    await refreshSnapshot()
    if (!disposed && session === workspaceSessionId.value) ElMessage.success('已有会话将在下一条消息加载最新记忆')
  } catch (error) {
    if (!disposed && session === workspaceSessionId.value) ElMessage.error((error as Error).message || '更新会话记忆失败')
  } finally {
    if (session === workspaceSessionId.value) refreshing.value = false
  }
}

async function runSearch() {
  const version = ++searchVersion
  const session = workspaceSessionId.value
  const query = searchQuery.value.trim()
  searchResults.value = []
  searchError.value = ''
  searchTouched.value = !!query
  searching.value = false
  if (!query) return
  searching.value = true
  try {
    const r = await searchSessions(query, 30, searchThread.value.trim() || undefined)
    if (!disposed && version === searchVersion && session === workspaceSessionId.value) searchResults.value = r.messages
  } catch (error) {
    if (!disposed && version === searchVersion && session === workspaceSessionId.value) searchError.value = (error as Error).message || '搜索失败，请重试'
  } finally {
    if (version === searchVersion) searching.value = false
  }
}

function clearSearch() {
  searchVersion++
  searchResults.value = []
  searching.value = searchTouched.value = false
  searchError.value = ''
}
watch([searchQuery, searchThread], clearSearch, { flush: 'sync' })
watch(workspaceSessionId, () => {
  searchQuery.value = searchThread.value = ''
  refreshing.value = false
  clearSearch()
}, { flush: 'sync' })

function beforeUnload(event: BeforeUnloadEvent) {
  if (agent.dirty || user.dirty) { event.preventDefault(); event.returnValue = '' }
}
window.addEventListener('beforeunload', beforeUnload)
onBeforeRouteLeave(async () => {
  if (!agent.dirty && !user.dirty) return true
  try {
    await ElMessageBox.confirm('记忆修改尚未保存，是否离开？', '未保存的记忆', {
      confirmButtonText: '离开', cancelButtonText: '继续编辑', type: 'warning'
    })
    return true
  } catch { return false }
})
onBeforeUnmount(() => {
  disposed = true
  searchVersion++
  window.removeEventListener('beforeunload', beforeUnload)
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
          <section v-loading="agent.loading" class="pane">
            <div class="pane-head">
              <div>
                <span class="file-label">MEMORY.md</span>
                <h3>工作笔记</h3>
                <p class="pane-subtitle">项目惯例、品牌口径，以及值得记住的经验。</p>
              </div>
              <span :class="['count', { over: agent.over }]">{{ agent.count }} / {{ agent.meta.char_limit }}</span>
            </div>
            <el-input
              v-model="agent.draft"
              aria-label="工作笔记"
              :disabled="agent.loading || !agent.loaded"
              type="textarea"
              :rows="18"
              resize="none"
              placeholder="# 品牌口径&#10;用简洁、自然的中文表达。&#10;&#10;# 项目约定&#10;在这里记录内容规范与工作经验…"
            />
            <p v-if="agent.error" role="alert" class="memory-error">{{ agent.error }}</p>
            <p v-if="agent.dirty" class="draft-notice">有未保存的修改</p>
            <div class="pane-actions">
              <el-button :icon="Refresh" plain :disabled="agent.loading || agent.saving" @click="agent.load">重新加载</el-button>
              <el-button type="primary" :loading="agent.saving" :disabled="agent.over || !agent.dirty || agent.loading" @click="agent.save">
                保存
              </el-button>
            </div>
          </section>

          <section v-loading="user.loading" class="pane">
            <div class="pane-head">
              <div>
                <span class="file-label">USER.md</span>
                <h3>我的偏好</h3>
                <p class="pane-subtitle">如何称呼你，你喜欢的语言与写作风格。</p>
              </div>
              <span :class="['count', { over: user.over }]">{{ user.count }} / {{ user.meta.char_limit }}</span>
            </div>
            <el-input
              v-model="user.draft"
              aria-label="我的偏好"
              :disabled="user.loading || !user.loaded"
              type="textarea"
              :rows="18"
              resize="none"
              placeholder="# 关于我&#10;我负责的品牌是…&#10;&#10;# 写作偏好&#10;喜欢简洁口语化的表达，少用表情符号。"
            />
            <p v-if="user.error" role="alert" class="memory-error">{{ user.error }}</p>
            <p v-if="user.dirty" class="draft-notice">有未保存的修改</p>
            <div class="pane-actions">
              <el-button :icon="Refresh" plain :disabled="user.loading || user.saving" @click="user.load">重新加载</el-button>
              <el-button type="primary" :loading="user.saving" :disabled="user.over || !user.dirty || user.loading" @click="user.save">
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
          <el-button :icon="DocumentCopy" size="small" plain :loading="refreshing" @click="invalidateAllSnapshots">
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
          <p v-if="searchError" role="alert" class="memory-error">{{ searchError }} <el-button text @click="runSearch">重试</el-button></p>
          <div v-else-if="!searchTouched && !searching" class="empty-state"><strong>让过去的想法，再次派上用场。</strong><span>输入关键词，找回聊过的选题、草稿与灵感。</span></div>
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
.memory-error { color: var(--c-fail); line-height: 1.6; }
.draft-notice { color: var(--c-text-secondary); font-size: 12px; }
.memory-page {
  width: min(100%, 1440px);
  margin: 0 auto;
  padding: 32px;
}

.page-header {
  display: block;
  margin-bottom: 24px;
  padding: 4px 0 22px;
  border-bottom: 1px solid var(--c-border);
}

.page-header h1 {
  margin: 0 0 6px;
  color: var(--c-text);
  font-family: var(--font-display);
  font-size: clamp(23px, 2.1vw, 29px);
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: -.025em;
}

.subtitle {
  color: var(--c-text-secondary);
  margin: 0;
  font-size: 13.5px;
  line-height: 1.75;
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
  background: #faf9f6;
}

.file-label {
  display: inline-flex;
  padding: 2px 8px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: #ffffff;
  color: var(--c-text-secondary);
  font-family: var(--font-mono);
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: .04em;
}

.pane-head h3 {
  margin: 8px 0 6px;
  color: var(--c-text);
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: 650;
}

.pane-subtitle {
  margin: 0;
  color: var(--c-text-secondary);
  font-size: 12.5px;
  line-height: 1.7;
}

.count {
  flex-shrink: 0;
  margin-top: 4px;
  padding: 4px 10px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-pill);
  background: #ffffff;
  color: var(--c-text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
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
  padding: 12px 16px;
  border-radius: var(--r-control);
  box-shadow: 0 0 0 1px var(--c-border) inset;
  color: var(--c-text);
  background: #faf9f6;
  font-family: var(--font-ui);
  font-size: 13.5px;
  line-height: 1.9;
}
.pane :deep(.el-textarea__inner:focus) {
  background: #ffffff;
  box-shadow: 0 0 0 1px var(--c-text) inset, 0 0 0 3px rgba(24, 24, 27, 0.06);
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
  padding: 18px 24px;
  border: 1px solid var(--c-border);
  border-radius: 12px;
  background: #faf9f6;
  color: var(--c-text-secondary);
}

.freeze-banner p {
  display: grid;
  gap: 5px;
  margin: 0;
  font-size: 12.5px;
  line-height: 1.6;
}

.freeze-banner strong {
  color: var(--c-text);
  font-weight: 650;
}

.freeze-banner span {
  color: var(--c-text-secondary);
  font-size: 12px;
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
