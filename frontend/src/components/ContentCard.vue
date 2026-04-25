<template>
  <article class="content-card">
    <header>
      <strong>{{ item.title || '无标题内容' }}</strong>
      <el-tag size="small" effect="plain">{{ item.status }}</el-tag>
    </header>
    <p>{{ item.content }}</p>
    <footer>
      <span>{{ item.content_type }}</span>
      <span>{{ item.created_at?.slice(0, 10) || '-' }}</span>
    </footer>
  </article>
</template>

<script setup lang="ts">
import type { ContentItem } from '../api/content'

defineProps<{ item: ContentItem }>()
</script>

<style scoped>
.content-card {
  background: #ffffff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 14px;
}

.content-card header,
.content-card footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.content-card p {
  min-height: 44px;
  margin: 10px 0;
  color: #4f5661;
  line-height: 1.6;
}

.content-card footer {
  color: #7a828d;
  font-size: 12px;
}
</style>
