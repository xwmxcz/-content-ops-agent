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
.content-card {
  position: relative;
  display: grid;
  gap: 12px;
  min-width: 0;
  padding: 20px;
  border: 1px solid var(--c-border);
  border-radius: 12px;
  background: #ffffff;
  box-shadow: var(--shadow-panel);
  transition: transform 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease;
}
.content-card:hover {
  transform: translateY(-2px);
  border-color: var(--c-border-strong);
  box-shadow: var(--shadow-hover);
}
.card-topline, .card-footer, .card-tags { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.card-type {
  display: inline-flex;
  align-items: center;
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--c-accent-soft);
  color: var(--c-accent);
  font-size: 11px;
  font-weight: 600;
}
.card-type::before { content: ''; display: inline-block; width: 5px; height: 5px; margin: 0 6px 0 0; background: currentColor; border-radius: 50%; }
.card-status { color: var(--c-text-secondary); font-size: 11px; font-weight: 500; padding: 2px 8px; background: var(--c-bg-soft); border-radius: 999px; }
.card-title { display: -webkit-box; overflow: hidden; -webkit-line-clamp: 2; -webkit-box-orient: vertical; color: var(--c-text); font-size: 15px; font-weight: 650; line-height: 1.5; letter-spacing: -0.01em; }
.card-body { margin: 0; color: var(--c-text-secondary); font-size: 13px; line-height: 1.75; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.card-tags { justify-content: flex-start; gap: 6px; }
.card-chip { color: var(--c-text-secondary); font-size: 11px; font-family: var(--font-mono); padding: 2px 8px; border: 1px solid var(--c-border-soft); border-radius: 6px; background: #faf9f6; }
.card-chip + .card-chip { border-left: 0; }
.card-footer { padding-top: 10px; border-top: 1px solid var(--c-border-soft); color: var(--c-text-tertiary); font-size: 11px; font-variant-numeric: tabular-nums; }
</style>
