<template>
  <div class="login-page">
    <section class="login-shell">
      <div class="login-brand">
        <div class="brand-mark">CO</div>
        <div>
          <p class="eyebrow">Private workspace</p>
          <h1>Content Ops Agent</h1>
        </div>
      </div>

      <div class="login-card">
        <div class="card-header">
          <el-icon><Lock /></el-icon>
          <div>
            <h2>管理员登录</h2>
            <p>进入内容生产、记忆管理和发布工作台</p>
          </div>
        </div>

        <form class="login-form" @submit.prevent="submit">
          <label class="field">
            <span>用户名</span>
            <el-input
              v-model="username"
              autocomplete="username"
              size="large"
              :prefix-icon="User"
              placeholder="admin"
            />
          </label>

          <label class="field">
            <span>密码</span>
            <el-input
              v-model="password"
              autocomplete="current-password"
              size="large"
              type="password"
              show-password
              :prefix-icon="Key"
              placeholder="请输入管理员密码"
            />
          </label>

          <div v-if="status && !status.configured" class="auth-note danger">
            后端已开启鉴权，但 AUTH_PASSWORD 或 AUTH_SECRET_KEY 还未配置。
          </div>
          <div v-else-if="errorMessage" class="auth-note danger">{{ errorMessage }}</div>

          <el-button
            class="submit-button"
            type="primary"
            size="large"
            native-type="submit"
            :loading="submitting"
            :disabled="!canSubmit"
          >
            进入工作台
          </el-button>
        </form>
      </div>

      <div class="login-meta">
        <span>API 鉴权</span>
        <strong>{{ statusLabel }}</strong>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus/es/components/message/index'
import { Key, Lock, User } from '@element-plus/icons-vue'
import { getAuthStatus, login } from '../api/auth'
import type { AuthStatus } from '../api/auth'

const router = useRouter()
const route = useRoute()

const username = ref('admin')
const password = ref('')
const status = ref<AuthStatus | null>(null)
const loadingStatus = ref(true)
const submitting = ref(false)
const errorMessage = ref('')

const nextTarget = computed(() => {
  const next = route.query.next
  return typeof next === 'string' && next.startsWith('/') ? next : '/'
})

const canSubmit = computed(() => {
  return Boolean(username.value.trim() && password.value && status.value?.configured !== false)
})

const statusLabel = computed(() => {
  if (loadingStatus.value) return '检测中'
  if (!status.value) return '不可用'
  if (!status.value?.enabled) return '未启用'
  return status.value.configured ? '已启用' : '配置不完整'
})

onMounted(async () => {
  try {
    status.value = await getAuthStatus()
    if (!status.value.enabled || status.value.authenticated) {
      router.replace(nextTarget.value)
    }
  } catch (error) {
    errorMessage.value = (error as Error).message
  } finally {
    loadingStatus.value = false
  }
})

async function submit() {
  if (!canSubmit.value) return
  submitting.value = true
  errorMessage.value = ''
  try {
    const result = await login(username.value.trim(), password.value)
    if (!result.enabled || result.access_token) {
      ElMessage.success('已登录')
      router.replace(nextTarget.value)
    }
  } catch (error) {
    errorMessage.value = (error as Error).message
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 32px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.7), rgba(247, 248, 251, 0.88)),
    var(--c-bg);
}

.login-shell {
  width: min(100%, 420px);
  display: grid;
  gap: 18px;
}

.login-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 8px;
  color: #ffffff;
  font-weight: 700;
  font-size: 14px;
  background: linear-gradient(135deg, #2563eb, #0f7a4f);
}

.eyebrow {
  margin: 0 0 2px;
  color: var(--c-text-tertiary);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

h1,
h2,
p {
  margin: 0;
}

h1 {
  color: var(--c-text);
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0;
  line-height: 1.2;
}

.login-card {
  padding: 24px;
  border: 1px solid var(--c-border);
  border-radius: 8px;
  background: var(--c-surface);
  box-shadow: var(--shadow-panel);
}

.card-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--c-border-soft);
}

.card-header :deep(.el-icon) {
  margin-top: 2px;
  color: var(--c-accent);
  font-size: 20px;
}

.card-header h2 {
  color: var(--c-text);
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0;
  line-height: 1.25;
}

.card-header p {
  margin-top: 5px;
  color: var(--c-text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.login-form {
  display: grid;
  gap: 16px;
  padding-top: 20px;
}

.field {
  display: grid;
  gap: 8px;
}

.field > span {
  color: var(--c-text-secondary);
  font-size: 13px;
  font-weight: 600;
}

.auth-note {
  padding: 10px 12px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.5;
}

.auth-note.danger {
  color: var(--c-fail);
  border-color: var(--c-fail);
  background: var(--c-fail-soft);
}

.submit-button {
  width: 100%;
  margin-top: 2px;
}

.login-meta {
  display: flex;
  justify-content: space-between;
  padding: 0 2px;
  color: var(--c-text-tertiary);
  font-size: 12px;
}

.login-meta strong {
  color: var(--c-text-secondary);
  font-weight: 600;
}

@media (max-width: 560px) {
  .login-page {
    align-items: start;
    padding: 20px;
  }

  .login-card {
    padding: 20px;
  }
}
</style>
