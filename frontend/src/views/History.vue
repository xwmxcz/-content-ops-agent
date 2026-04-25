<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1 class="page-title">历史内容</h1>
        <p class="page-subtitle">筛选、查看和复用已保存的内容。</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
    </div>

    <section class="section">
      <div class="toolbar">
        <el-select v-model="filters.content_type" clearable placeholder="内容类型" style="width: 180px">
          <el-option label="小红书" value="xiaohongshu" />
          <el-option label="微博" value="weibo" />
          <el-option label="博客" value="blog" />
          <el-option label="视频脚本" value="video_script" />
          <el-option label="Twitter/X" value="twitter" />
        </el-select>
        <el-select v-model="filters.status" clearable placeholder="状态" style="width: 160px">
          <el-option label="草稿" value="draft" />
          <el-option label="已打磨" value="refined" />
          <el-option label="已发布" value="published" />
        </el-select>
        <el-button type="primary" @click="load">筛选</el-button>
      </div>
      <el-table :data="items" v-loading="loading" class="history-table" @row-click="open">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="title" label="标题" min-width="180" />
        <el-table-column prop="content_type" label="类型" width="130" />
        <el-table-column prop="status" label="状态" width="120" />
        <el-table-column prop="created_at" label="创建时间" width="190" />
      </el-table>
    </section>

    <el-drawer v-model="drawer" title="内容详情" size="48%">
      <template v-if="selected">
        <h2>{{ selected.title || '无标题内容' }}</h2>
        <p class="muted">ID {{ selected.id }} · {{ selected.content_type }} · {{ selected.status }}</p>
        <div class="content-preview">{{ selected.content }}</div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { getContents, getContent, type ContentItem } from '../api/content'

const filters = reactive({ content_type: '', status: '' })
const items = ref<ContentItem[]>([])
const loading = ref(false)
const drawer = ref(false)
const selected = ref<ContentItem>()

async function load() {
  loading.value = true
  try {
    items.value = await getContents({
      limit: 100,
      content_type: filters.content_type || undefined,
      status: filters.status || undefined
    })
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function open(row: ContentItem) {
  selected.value = await getContent(row.id)
  drawer.value = true
}

onMounted(load)
</script>

<style scoped>
.history-table {
  margin-top: 16px;
}
</style>
