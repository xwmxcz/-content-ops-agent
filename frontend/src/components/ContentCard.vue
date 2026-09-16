<template>
  <article class="content-card">
    <div class="card-topline">
      <span class="card-type">{{ contentTypeLabel }}</span>
      <span class="card-status">{{ statusLabel }}</span>
    </div>

    <strong class="card-title">{{ title }}</strong>
    <p class="card-body">{{ excerpt }}</p>

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

const excerpt = computed(() => props.item.content.replace(/^#{1,6}\s+.+\r?\n+/, '').replace(/(\*\*|__)/g, '').trim())
const title = computed(() => props.item.title || '未命名内容')
const contentTypeLabel = computed(() => getTypeLabel(props.item.content_type))
const statusLabel = computed(() => getStatusLabel(props.item.status))
const styleLabel = computed(() => getStyleLabel(props.item.style))
</script>

<style scoped>
.content-card { display: grid; gap: 12px; min-width: 0; padding: 18px; border: 1px solid var(--c-border); border-radius: 12px; background: var(--c-surface); transition: border-color .15s, background-color .15s; }
.content-card:hover { border-color: var(--c-border-strong); background: var(--c-accent-soft); }
.card-topline, .card-footer, .card-tags { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.card-type { color: var(--c-accent); font-size: 11px; font-weight: 500; }
.card-type::before { content: ''; display: inline-block; width: 5px; height: 5px; margin: 0 6px 2px 0; background: currentColor; border-radius: 50%; }
.card-status { color: var(--c-text-tertiary); font-size: 10px; padding: 2px 7px; background: var(--c-bg-soft); border-radius: 5px; }
.card-title { display: -webkit-box; overflow: hidden; -webkit-line-clamp: 2; -webkit-box-orient: vertical; font-size: 14px; font-weight: 600; line-height: 1.65; }
.card-body { margin: 0; color: var(--c-text-tertiary); font-size: 12px; line-height: 1.8; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.card-tags { justify-content: flex-start; gap: 10px; }
.card-chip { color: var(--c-text-tertiary); font-size: 10px; }
.card-chip + .card-chip { padding-left: 10px; border-left: 1px solid var(--c-border); }
.card-footer { padding-top: 10px; border-top: 1px solid var(--c-border-soft); color: var(--c-text-tertiary); font-size: 10px; }
</style>
