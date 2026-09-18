<script setup lang="ts">
/**
 * The session list: search, archive toggle, and per-thread actions.
 *
 * Presentation only. It owns no data access — the parent passes the store's
 * reactive state in and handles the mutations, so the confirmation flow
 * (rename/delete prompts) stays in one place with the other dialogs.
 */
import { Edit, Delete, FolderOpened, FolderRemove, Search, Top } from '@element-plus/icons-vue'
import type { AgentSearchHit, AgentThread } from '../api/agent'
import { formatTime, snippet } from '../composables/useChatPresentation'

const props = defineProps<{
  threads: AgentThread[]
  threadsLoading: boolean
  includeArchived: boolean
  hasMoreThreads: boolean
  activeThreadId: string | undefined
  searchInput: string
  searchActive: boolean
  searching: boolean
  searchResults: AgentSearchHit[]
  /** Title lookup, owned by the parent because it resolves against the store. */
  threadLabel: (threadId: string) => string
}>()

const emit = defineEmits<{
  (e: 'update:searchInput', value: string): void
  (e: 'search-input', value: string): void
  (e: 'search-clear'): void
  (e: 'toggle-archived', event: Event): void
  (e: 'select', threadId: string): void
  (e: 'jump', threadId: string): void
  (e: 'rename', thread: AgentThread): void
  (e: 'toggle-pin', thread: AgentThread): void
  (e: 'toggle-archive', thread: AgentThread): void
  (e: 'remove', thread: AgentThread): void
  (e: 'load-more'): void
}>()
</script>

<template>
  <aside class="thread-panel">
    <div class="panel-head">
      <span>我的会话</span>
      <strong>{{ threads.length }}</strong>
    </div>

    <div class="thread-search">
      <el-input
        :model-value="searchInput"
        placeholder="搜索消息内容"
        size="small"
        clearable
        :prefix-icon="Search"
        @update:model-value="emit('update:searchInput', $event)"
        @input="emit('search-input', $event)"
        @clear="emit('search-clear')"
      />
    </div>

    <label class="thread-toggle">
      <input type="checkbox" :checked="includeArchived" @change="emit('toggle-archived', $event)" />
      <span>显示已归档</span>
    </label>

    <div class="thread-list">
      <!-- Search results override the thread list when a query is active. -->
      <div v-if="searchActive" class="search-results">
        <div v-if="searching" class="thread-empty">搜索中…</div>
        <div v-else-if="!searchResults.length" class="thread-empty">无匹配结果</div>
        <button
          v-for="hit in searchResults"
          :key="`${hit.thread_id}-${hit.message_id}`"
          type="button"
          class="thread-item"
          :class="{ active: hit.thread_id === activeThreadId }"
          @click="emit('jump', hit.thread_id)"
        >
          <span class="thread-title">{{ props.threadLabel(hit.thread_id) }}</span>
          <small class="search-snippet">{{ snippet(hit.content) }}</small>
          <small>{{ hit.role === 'user' ? '我' : '内容助手' }} · {{ formatTime(hit.created_at) }}</small>
        </button>
      </div>

      <template v-else>
        <div v-if="!threads.length && !threadsLoading" class="thread-empty">暂无会话</div>
        <div
          v-for="thread in threads"
          :key="thread.id"
          class="thread-item"
          :class="{ active: thread.id === activeThreadId, pinned: thread.pinned, archived: thread.archived }"
        >
          <button type="button" class="thread-item-body" @click="emit('select', thread.id)">
            <span class="thread-title">
              <span v-if="thread.pinned" class="pin-mark" title="已置顶">📌</span>
              <span v-if="thread.archived" class="archive-mark" title="已归档">🗄</span>
              {{ thread.title || thread.id }}
            </span>
            <small>{{ thread.message_count }} 条消息</small>
          </button>
          <div class="thread-actions" @click.stop>
            <el-button text size="small" :icon="Edit" aria-label="重命名" @click="emit('rename', thread)" />
            <el-button
              text
              size="small"
              :icon="Top"
              :class="{ 'is-active': thread.pinned }"
              :aria-label="thread.pinned ? '取消置顶' : '置顶'"
              @click="emit('toggle-pin', thread)"
            />
            <el-button
              text
              size="small"
              :icon="thread.archived ? FolderOpened : FolderRemove"
              :class="{ 'is-active': thread.archived }"
              :aria-label="thread.archived ? '取消归档' : '归档'"
              @click="emit('toggle-archive', thread)"
            />
            <el-button text size="small" type="danger" :icon="Delete" aria-label="删除" @click="emit('remove', thread)" />
          </div>
        </div>
        <button
          v-if="hasMoreThreads"
          type="button"
          class="thread-load-more"
          :disabled="threadsLoading"
          @click="emit('load-more')"
        >
          {{ threadsLoading ? '加载中…' : '加载更多' }}
        </button>
      </template>
    </div>
  </aside>
</template>

<style scoped>
.thread-panel {
  /* The border/radius/background that the original rule shared with
     .dialog-panel are repeated here: the two panels are now separate
     components, and a shared parent rule would not reach into a child's
     scoped slot. The later `background` intentionally overrides the earlier
     one, exactly as the original two-rule pair did. */
  min-width: 0;
  border: 1px solid var(--c-border);
  border-radius: var(--r-card);
  background: var(--c-surface);
  display: grid;
  grid-template-rows: auto auto auto minmax(0, 1fr);
  align-self: stretch;
  gap: 16px;
  padding: 20px 12px 12px;
  min-height: 0;
  overflow: hidden;
  background: var(--c-bg-soft);
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: space-between;
}

.panel-head,
.thread-search,
.thread-toggle {
  margin: 0 6px;
}

.panel-head span {
  color: var(--c-text-secondary);
  font-weight: 600;
  font-size: 13px;
}

.panel-head strong {
  padding: 1px 8px;
  border-radius: var(--r-pill);
  background: var(--c-surface);
  color: var(--c-text-tertiary);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.thread-toggle {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--c-text-tertiary);
  font-size: 12px;
  cursor: pointer;
}

.thread-toggle input {
  margin: 0;
  accent-color: var(--c-accent);
}

.thread-list, .search-results {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.thread-list {
  min-height: 0;
  overflow-y: auto;
}

.thread-empty {
  padding: 42px 12px;
  color: var(--c-text-tertiary);
  text-align: center;
  font-size: 13px;
}

.thread-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 4px;
  flex-shrink: 0;
  width: 100%;
  padding: 12px 12px 6px;
  border: 1px solid transparent;
  border-radius: var(--r-control);
  background: transparent;
  color: var(--c-text);
  text-align: left;
  transition: background-color 120ms ease, border-color 120ms ease;
}

.thread-item:hover {
  background: var(--c-surface);
}

.thread-item.active {
  background: var(--c-surface);
  border-color: var(--c-border);
  box-shadow: inset 3px 0 var(--c-accent);
}

.thread-item.archived {
  opacity: .65;
}

.thread-item-body {
  display: grid;
  gap: 7px;
  min-width: 0;
  width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.thread-title {
  overflow: hidden;
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pin-mark, .archive-mark {
  font-size: 11px;
}

.thread-item small {
  overflow: hidden;
  color: var(--c-text-tertiary);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thread-actions {
  /* Keep this row reserved so revealing actions never moves the title target. */
  display: flex;
  visibility: hidden;
  justify-content: flex-end;
  align-items: center;
  gap: 2px;
}

.thread-item:hover .thread-actions,
.thread-item:focus-within .thread-actions,
.thread-item.active .thread-actions {
  visibility: visible;
}

.thread-actions :deep(.el-button) {
  padding: 4px 5px;
  height: 24px;
  margin: 0;
}

.thread-actions :deep(.is-active) {
  color: var(--c-accent);
}

.search-snippet {
  color: var(--c-text-secondary);
}

.settings-body {
  padding: 5px 0 20px;
}

.chat-log {
  min-height: 0;
  max-height: none;
  padding: 28px;
  overflow-y: auto;
  border: 0;
  border-radius: 0;
  box-shadow: none;
  scroll-behavior: smooth;
}

.chat-empty {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 100%;
  gap: 12px;
  padding: 24px 16px;
  text-align: center;
}

.empty-label {
  padding: 7px 13px;
  background: var(--c-accent-soft);
  color: var(--c-accent);
  border-radius: var(--r-pill);
  font-size: 11px;
}

.chat-empty strong {
  font-family: var(--font-editorial);
  font-size: clamp(25px, 2.5vw, 34px);
  font-weight: 500;
  letter-spacing: -.03em;
}

.chat-empty p {
  max-width: 330px;
  margin: 0;
  color: var(--c-text-secondary);
  font-size: 13px;
  line-height: 1.8;
}

.intent-chip {
  padding: 3px 9px;
  border-radius: var(--r-pill);
  background: var(--c-bg-soft);
  color: var(--c-text-secondary);
  font-size: 11px;
}

.plan-head, .tool-events-head {
  margin-bottom: 8px;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 600;
}

.tool-events {
  display: grid;
  gap: 6px;
  margin-top: 18px;
}

.tool-events-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 2px;
}

.tool-events-head strong {
  font-weight: 500;
}

.tool-event {
  border: 1px solid var(--c-border);
  border-radius: var(--r-control);
  overflow: hidden;
  background: var(--c-bg-soft);
}

.tool-event.failed {
  border-color: var(--c-fail);
}

.tool-event.proposed {
  border-color: var(--c-warn);
}

.tool-event > summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px 8px;
  padding: 10px 12px;
  cursor: pointer;
  list-style: none;
  font-size: 11px;
}

.tool-event > summary::-webkit-details-marker {
  display: none;
}

.tool-event > summary::before {
  content: '›';
  color: var(--c-text-tertiary);
  font-size: 14px;
}

.tool-event[open] > summary::before {
  transform: rotate(90deg);
}

.tool-event-name {
  color: var(--c-text-secondary);
  font-family: var(--font-mono);
  overflow-wrap: anywhere;
}

.tool-event-badge, .tool-event-attempt {
  padding: 2px 6px;
  border-radius: var(--r-pill);
  font-size: 10px;
}

.tool-event-badge.completed {
  color: var(--c-ok);
  background: var(--c-ok-soft);
}

.tool-event-badge.failed {
  color: var(--c-fail);
  background: var(--c-fail-soft);
}

.tool-event-badge.proposed, .tool-event-attempt {
  color: var(--c-warn);
  background: var(--c-warn-soft);
}

.tool-event-body {
  display: grid;
  gap: 12px;
  padding: 12px;
  border-top: 1px solid var(--c-border);
}

.tool-event-label {
  color: var(--c-text-tertiary);
  font-size: 10px;
}

.composer {
  display: grid;
  gap: 12px;
  min-width: 0;
  padding: 18px 24px 20px;
  border-top: 1px solid var(--c-border-soft);
}

.composer :deep(.el-textarea__inner) {
  padding: 14px 16px;
  line-height: 1.7;
  background: var(--c-bg-soft);
}

.thread-load-more {
  padding: 7px 14px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-control);
  background: var(--c-surface);
  color: var(--c-text-secondary);
  font-size: 12px;
  cursor: pointer;
}

.thread-load-more:hover:not(:disabled) {
  color: var(--c-accent);
  border-color: var(--c-accent);
}

.thread-load-more:disabled {
  opacity: .6;
  cursor: not-allowed;
}

.thread-item-body:focus-visible,
.thread-load-more:focus-visible {
  outline: 2px solid var(--c-accent);
  outline-offset: 3px;
  border-radius: var(--r-control);
}

/* Below the workbench breakpoint the panel stacks under the conversation, so it
   is capped rather than filling the column. Touch layouts have no hover, so the
   per-thread actions stay visible instead of revealing on hover. */
@media (max-width: 820px) {
  .thread-panel {
    order: 2;
    max-height: 350px;
  }

  .thread-actions {
    visibility: visible;
  }
}

@media (prefers-reduced-motion: reduce) {
  .thread-item {
    transition: none;
  }
}
</style>
