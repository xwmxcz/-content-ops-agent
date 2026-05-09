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
  border: 1px solid rgba(24, 33, 38, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 18px 50px rgba(21, 31, 39, 0.08);
  backdrop-filter: blur(14px);
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
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
}

.card-type {
  color: #1d6258;
  background: rgba(15, 133, 116, 0.1);
}

.card-status {
  color: #7e5923;
  background: rgba(196, 147, 63, 0.12);
}

.card-chip {
  color: #4c5860;
  background: rgba(24, 33, 38, 0.06);
}

.card-title {
  color: #182126;
  font-size: 16px;
  line-height: 1.45;
}

.card-body {
  min-height: 70px;
  margin: 0;
  color: #4e5b63;
  line-height: 1.7;
}

.card-footer {
  color: #748087;
  font-size: 12px;
}
</style>
