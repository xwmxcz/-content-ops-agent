<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1 class="page-title">内容生成</h1>
        <p class="page-subtitle">选择平台、风格和模型，生成可保存的内容资产。</p>
      </div>
    </div>

    <div class="grid-2">
      <section class="section">
        <ModelSelector v-model="modelConfig" />
        <el-divider />
        <el-form label-position="top">
          <el-form-item label="目标平台">
            <el-select v-model="form.content_type">
              <el-option label="小红书" value="xiaohongshu" />
              <el-option label="微博" value="weibo" />
              <el-option label="博客文章" value="blog" />
              <el-option label="视频脚本" value="video_script" />
              <el-option label="Twitter/X" value="twitter" />
            </el-select>
          </el-form-item>
          <el-form-item label="内容风格">
            <el-segmented v-model="form.style" :options="styleOptions" />
          </el-form-item>
          <el-form-item label="长度">
            <el-radio-group v-model="form.length">
              <el-radio-button label="short">短</el-radio-button>
              <el-radio-button label="medium">中</el-radio-button>
              <el-radio-button label="long">长</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="关键词">
            <el-input v-model="keywords" placeholder="效率, 职场, 工具" />
          </el-form-item>
        </el-form>
      </section>

      <section class="section">
        <el-form label-position="top">
          <el-form-item label="内容主题">
            <el-input v-model="form.topic" type="textarea" :rows="5" placeholder="例如：如何用 AI 提升内容运营效率" />
          </el-form-item>
        </el-form>
        <div class="toolbar">
          <el-button type="primary" :icon="EditPen" :loading="loading" @click="submit">生成内容</el-button>
          <el-button :icon="Tickets" :disabled="!result" @click="$router.push('/history')">查看历史</el-button>
        </div>
        <el-divider />
        <el-empty v-if="!result" description="生成结果会显示在这里" />
        <div v-else>
          <h2>{{ result.title || '生成结果' }}</h2>
          <div class="content-preview">{{ result.content }}</div>
          <div class="toolbar result-tags">
            <el-tag v-for="tag in result.tags" :key="tag" effect="plain">{{ tag }}</el-tag>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { EditPen, Tickets } from '@element-plus/icons-vue'
import ModelSelector from '../components/ModelSelector.vue'
import { generateContent, type ContentItem } from '../api/content'

const styleOptions = [
  { label: '轻松', value: 'casual' },
  { label: '专业', value: 'professional' },
  { label: '营销', value: 'marketing' },
  { label: '故事', value: 'storytelling' }
]

const modelConfig = reactive({ provider: '', model: '', temperature: 0.7, max_tokens: 2048 })
const form = reactive({ topic: '', content_type: 'xiaohongshu', style: 'casual', length: 'medium' })
const keywords = ref('')
const loading = ref(false)
const result = ref<ContentItem>()

async function submit() {
  if (!form.topic.trim()) {
    ElMessage.warning('请输入内容主题')
    return
  }
  loading.value = true
  try {
    result.value = await generateContent({
      ...form,
      keywords: keywords.value ? keywords.value.split(',').map(item => item.trim()).filter(Boolean) : undefined,
      provider: modelConfig.provider,
      model: modelConfig.model,
      temperature: modelConfig.temperature,
      max_tokens: modelConfig.max_tokens
    })
    ElMessage.success(`内容已保存，ID: ${result.value.id}`)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.result-tags {
  margin-top: 16px;
}
</style>
