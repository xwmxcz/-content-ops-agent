<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1 class="page-title">Agent 对话</h1>
        <p class="page-subtitle">用于内容运营策略、选题和改写建议的对话入口。</p>
      </div>
      <el-button :icon="Delete" @click="messages = []">清空</el-button>
    </div>

    <div class="chat-log">
      <div v-for="(message, index) in messages" :key="index" class="message" :class="message.role">
        {{ message.content }}
      </div>
      <el-empty v-if="!messages.length" description="输入问题开始对话" />
    </div>
    <div class="toolbar chat-input">
      <el-input v-model="input" type="textarea" :rows="3" placeholder="例如：帮我规划一周的小红书选题" @keydown.ctrl.enter="send" />
      <el-button type="primary" :icon="Position" :loading="loading" @click="send">发送</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete, Position } from '@element-plus/icons-vue'
import { chat } from '../api/agent'

const input = ref('')
const loading = ref(false)
const messages = ref<Array<{ role: 'user' | 'assistant'; content: string }>>([])

async function send() {
  const text = input.value.trim()
  if (!text) return
  messages.value.push({ role: 'user', content: text })
  input.value = ''
  loading.value = true
  try {
    const result = await chat(text)
    messages.value.push({ role: 'assistant', content: result.response })
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.chat-input {
  align-items: stretch;
  margin-top: 12px;
}

.chat-input .el-input {
  flex: 1;
}
</style>
