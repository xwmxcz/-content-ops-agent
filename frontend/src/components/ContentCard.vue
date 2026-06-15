<template>
  <article class="content-card">
    <div class="card-topline">
      <span class="card-type">{{ contentTypeLabel }}</span>
      <span class="card-status">{{ statusLabel }}</span>
    </div>

    <strong class="card-title">{{ title }}</strong>
    <p class="card-body">{{ item.content }}</p>

    <div class="card-tags">
      <span class="card-chip">{{ styleLabel }}</span>
      <span class="card-chip">#{{ item.id }}</span>
    </div>

    <footer class="card-footer">
      <span>{{ item.created_at?.slice(0, 10) || '-' }}</span>
      <span>{{ item.updated_at ? '已更新' : '新内容' }}</span>
    </footer>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ContentItem } from '../api/content'
import { getContentTypeLabel, getContentTypeLabel as getTypeLabel, getStatusLabel, getStyleLabel } from '../constants/content'

const props = defineProps<{ item: ContentItem }>()

const title = computed(() => props.item.title || '未命名内容')
const contentTypeLabel = computed(() => getTypeLabel(props.item.content_type))
const statusLabel = computed(() => getStatusLabel(props.item.status))
const styleLabel = computed(() => getStyleLabel(props.item.style))
</script>

<style scoped>
.content-card {
  display: grid;
  gap: 10px;
  padding: 16px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-surface);
  box-shadow: none;
  backdrop-filter: none;
  transition: border-color 100ms ease;
}

.content-card:hover {
  border-color: var(--c-border-strong);
}

.card-topline,
.card-footer,
.card-tags {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.card-type,
.card-status,
.card-chip {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid var(--c-border);
  background: var(--c-surface);
  font-size: 11px;
  font-weight: 500;
  font-family: var(--font-mono);
  letter-spacing: 0;
}

.card-type {
  color: var(--c-accent);
  border-color: var(--c-accent);
  background: var(--c-accent-soft);
}

.card-status {
  color: var(--c-text-secondary);
}

.card-chip {
  color: var(--c-text-tertiary);
}

.card-title {
  color: var(--c-text);
  font-size: 14.5px;
  font-weight: 600;
  line-height: 1.4;
  letter-spacing: 0;
}

.card-body {
  min-height: 60px;
  margin: 0;
  color: var(--c-text-secondary);
  font-size: 13px;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-footer {
  color: var(--c-text-tertiary);
  font-size: 11.5px;
  font-family: var(--font-mono);
}
</style>
