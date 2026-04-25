<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1 class="page-title">内容打磨</h1>
        <p class="page-subtitle">基于已有内容进行改写、风格切换、标题优化和 SEO 分析。</p>
      </div>
    </div>

    <div class="grid-2">
      <section class="section">
        <ModelSelector v-model="modelConfig" />
        <el-divider />
        <el-form label-position="top">
          <el-form-item label="内容 ID">
            <el-input-number v-model="contentId" :min="1" />
            <el-button class="load-btn" :icon="Search" @click="loadContent">加载</el-button>
          </el-form-item>
        </el-form>
        <div v-if="source" class="source-box">
          <strong>{{ source.title || '无标题内容' }}</strong>
          <p>{{ source.content }}</p>
        </div>
      </section>

      <section class="section">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="改写" name="rewrite">
            <el-input v-model="instruction" type="textarea" :rows="4" placeholder="例如：语气更亲切，结构更清晰，加入行动建议" />
            <el-button type="primary" :loading="loading" class="action-btn" @click="rewrite">执行改写</el-button>
          </el-tab-pane>
          <el-tab-pane label="风格切换" name="style">
            <el-radio-group v-model="newStyle">
              <el-radio-button label="casual">轻松</el-radio-button>
              <el-radio-button label="professional">专业</el-radio-button>
              <el-radio-button label="marketing">营销</el-radio-button>
              <el-radio-button label="storytelling">故事</el-radio-button>
            </el-radio-group>
            <el-button type="primary" :loading="loading" class="action-btn" @click="switchStyle">切换风格</el-button>
          </el-tab-pane>
          <el-tab-pane label="标题优化" name="titles">
            <el-slider v-model="titleCount" :min="3" :max="10" show-input />
            <el-button type="primary" :loading="loading" class="action-btn" @click="titles">生成标题</el-button>
          </el-tab-pane>
          <el-tab-pane label="SEO" name="seo">
            <el-button type="primary" :loading="loading" @click="seo">分析 SEO</el-button>
          </el-tab-pane>
        </el-tabs>

        <el-divider />
        <el-empty v-if="!resultText" description="操作结果会显示在这里" />
        <div v-else class="content-preview">{{ resultText }}</div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import ModelSelector from '../components/ModelSelector.vue'
import { analyzeSeo, generateTitles, getContent, refineContent, type ContentItem } from '../api/content'

const modelConfig = reactive({ provider: '', model: '', temperature: 0.7, max_tokens: 2048 })
const contentId = ref(1)
const source = ref<ContentItem>()
const activeTab = ref('rewrite')
const instruction = ref('')
const newStyle = ref('professional')
const titleCount = ref(5)
const resultText = ref('')
const loading = ref(false)

async function loadContent() {
  try {
    source.value = await getContent(contentId.value)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function run(task: () => Promise<string>) {
  if (!source.value) {
    ElMessage.warning('请先加载内容')
    return
  }
  loading.value = true
  try {
    resultText.value = await task()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function rewrite() {
  run(async () => {
    const result = await refineContent({
      content_id: contentId.value,
      instruction: instruction.value,
      provider: modelConfig.provider,
      model: modelConfig.model,
      temperature: modelConfig.temperature,
      max_tokens: modelConfig.max_tokens
    })
    return result.content
  })
}

function switchStyle() {
  run(async () => {
    const result = await refineContent({
      content_id: contentId.value,
      new_style: newStyle.value,
      provider: modelConfig.provider,
      model: modelConfig.model,
      temperature: modelConfig.temperature,
      max_tokens: modelConfig.max_tokens
    })
    return result.content
  })
}

function titles() {
  run(() =>
    generateTitles({
      content_id: contentId.value,
      count: titleCount.value,
      provider: modelConfig.provider,
      model: modelConfig.model
    })
  )
}

function seo() {
  run(() =>
    analyzeSeo({
      content_id: contentId.value,
      provider: modelConfig.provider,
      model: modelConfig.model
    })
  )
}
</script>

<style scoped>
.load-btn,
.action-btn {
  margin-left: 10px;
}

.source-box {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 12px;
}

.source-box p {
  max-height: 240px;
  overflow: auto;
  color: #555d68;
  line-height: 1.6;
}
</style>
