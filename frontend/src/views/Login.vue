<template>
  <div class="login-page">
    <section class="login-shell">
      <div class="login-story">
      <div class="login-brand">
        <WorkspaceMark />
        <div>
          <p class="eyebrow">内容创作工作台</p>
          <h1>Content Ops</h1>
        </div>
      </div>

      <div class="story-copy">
        <span>让创作，回到内容本身</span>
        <h2>给灵感一个<br /><em>成长的空间。</em></h2>
        <p>把零散的想法写成文章，<br />把每一次创作，留在自己的工作台。</p>
      </div>
      <div class="story-footer"><span>写作</span><i></i><span>打磨</span><i></i><span>沉淀</span></div>
      </div>
      <div class="login-access">
      <div class="login-card">
        <div class="card-header">
          <el-icon><Lock /></el-icon>
          <div>
            <h2>{{ isRegister ? '创建你的工作区' : '欢迎回来' }}</h2>
            <p>{{ isRegister ? '每个账号有独立的内容与对话空间。' : '登录你的工作区，接着上次的灵感继续。' }}</p>
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
              placeholder="请输入用户名"
            />
            <small v-if="isRegister">3–32 位英文字母、数字或下划线，不区分大小写</small>
          </label>

          <label class="field">
            <span>密码</span>
            <el-input
              v-model="password"
              :autocomplete="isRegister ? 'new-password' : 'current-password'"
              size="large"
              type="password"
              show-password
              :prefix-icon="Key"
              :placeholder="isRegister ? '设置你的密码' : '请输入密码'"
            />
            <small v-if="isRegister">12–128 个字符，建议使用较长且独有的密码</small>
          </label>

          <label v-if="isRegister" class="field">
            <span>确认密码</span>
            <el-input
              v-model="confirmPassword"
              autocomplete="new-password"
              size="large"
              type="password"
              show-password
              :prefix-icon="Key"
              placeholder="再次输入密码"
            />
          </label>

          <div v-if="errorMessage" role="alert" class="auth-note danger">{{ errorMessage }}</div>

          <el-button
            class="submit-button"
            type="primary"
            size="large"
            native-type="submit"
            :loading="submitting"
            :disabled="!canSubmit"
          >
            {{ isRegister ? '注册并进入工作台' : '进入工作台' }}
          </el-button>
        </form>
        <p class="account-link">
          {{ isRegister ? '已有账号？' : '还没有账号？' }}
          <router-link :to="{ name: isRegister ? 'login' : 'register', query: { next: nextTarget } }">
            {{ isRegister ? '立即登录' : '创建账号' }}
          </router-link>
        </p>
      </div>

      <div class="login-meta">
        <span>个人工作区</span>
        <strong>内容与对话，仅自己可见</strong>
      </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
// Shares account entry UI between login and registration; never retains identity locally.
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus/es/components/message/index'
import { Key, Lock, User } from '@element-plus/icons-vue'
import { getAuthStatus, login, register } from '../api/auth'
import { ApiError } from '../api'
import WorkspaceMark from '../components/WorkspaceMark.vue'

const router = useRouter()
const route = useRoute()

const isRegister = computed(() => route.name === 'register')
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const loadingStatus = ref(true)
const submitting = ref(false)
const errorMessage = ref('')

const nextTarget = computed(() => {
  const next = route.query.next
  if (typeof next !== 'string' || !next.startsWith('/') || next.startsWith('//') || /[\\\u0000-\u0020]/.test(next)) return '/'
  const destination = router.resolve(next)
  return destination.matched.length && !destination.meta.public ? destination.fullPath : '/'
})

const canSubmit = computed(() => {
  return Boolean(username.value.trim() && password.value && (!isRegister.value || confirmPassword.value) && !submitting.value && !loadingStatus.value)
})

watch(isRegister, () => {
  password.value = ''
  confirmPassword.value = ''
  errorMessage.value = ''
})

onMounted(async () => {
  try {
    const status = await getAuthStatus()
    if (status.authenticated) {
      router.replace(nextTarget.value)
    }
  } catch (error) {
    errorMessage.value = authErrorMessage(error)
  } finally {
    loadingStatus.value = false
  }
})

async function submit() {
  if (!canSubmit.value) return
  errorMessage.value = ''
  if (isRegister.value) {
    if (!/^[a-zA-Z0-9_]{3,32}$/.test(username.value.trim())) {
      errorMessage.value = '用户名需要 3–32 位英文字母、数字或下划线'
      return
    }
    const passwordLength = Array.from(password.value).length
    if (passwordLength < 12 || passwordLength > 128) {
      errorMessage.value = '密码长度需要在 12–128 个字符之间'
      return
    }
    if (password.value !== confirmPassword.value) {
      errorMessage.value = '两次输入的密码不一致，请重新确认'
      return
    }
  }
  submitting.value = true
  try {
    await (isRegister.value ? register : login)(username.value.trim(), password.value)
    ElMessage.success(isRegister.value ? '账号已创建，欢迎来到你的工作区' : '已登录')
    // Recreate all stores and running task state before displaying the new account.
    window.location.replace(nextTarget.value)
  } catch (error) {
    errorMessage.value = authErrorMessage(error)
  } finally {
    submitting.value = false
  }
}

function authErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 401) return '用户名或密码不正确，请重新输入'
    if (error.status === 409) return '该用户名已被使用，请换一个用户名'
    if (error.status === 422) return '请检查用户名格式及密码长度后再试'
    if (error.status === 429) return '操作过于频繁，请稍后再试'
  }
  return error instanceof Error ? error.message : '请求失败，请稍后再试'
}
</script>

<style scoped>
.login-page { min-height: 100vh; display: grid; place-items: center; padding: 40px; background: var(--c-bg); }
.login-shell { display: grid; grid-template-columns: 1fr 1fr; width: min(100%, 1000px); min-height: 580px; border: 1px solid var(--c-border); border-radius: 24px; overflow: hidden; background: var(--c-surface); box-shadow: var(--shadow-panel); }
.login-story { display: flex; flex-direction: column; padding: 42px; background: var(--c-sidebar); border-right: 1px solid var(--c-border); }
.login-brand { display: flex; align-items: center; gap: 10px; }
.eyebrow { margin: 0 0 2px; color: var(--c-text-tertiary); font-size: 10px; letter-spacing: 1px; }
h1 { margin: 0; font-family: var(--font-display); font-size: 24px; font-weight: 600; letter-spacing: -.6px; line-height: 1.2; }
.story-copy { margin: auto 0; padding: 45px 0; }
.story-copy > span { color: var(--c-text-secondary); font-size: 11px; letter-spacing: 1.2px; }
.story-copy h2 { margin: 22px 0; font-family: var(--font-editorial); font-size: 40px; font-weight: 500; letter-spacing: 1px; line-height: 1.65; }
.story-copy em { font-style: normal; color: var(--c-accent); }
.story-copy p { color: var(--c-text-tertiary); font-size: 13px; line-height: 2; }
.story-footer { display: flex; align-items: center; gap: 16px; color: var(--c-text-tertiary); font-size: 11px; }
.story-footer i { width: 26px; height: 1px; background: var(--c-border-strong); }
.login-access { display: flex; flex-direction: column; justify-content: center; padding: 54px 44px 36px; }
.login-card { padding: 0; }
.card-header > :deep(.el-icon) { display: none; }
.card-header h2 { margin: 0; font-family: var(--font-display); font-size: 24px; font-weight: 600; }
.card-header p { margin: 10px 0 0; color: var(--c-text-tertiary); font-size: 12px; line-height: 1.8; }
.login-form { display: grid; gap: 22px; padding-top: 34px; }
.field { display: grid; gap: 9px; }
.field > span { color: var(--c-text-secondary); font-size: 12px; font-weight: 500; }
.field > small { color: var(--c-text-tertiary); font-size: 11px; line-height: 1.6; }
.field :deep(.el-input__wrapper) { min-height: 44px; }
.auth-note { padding: 12px 14px; border-radius: var(--r-control); font-size: 12px; line-height: 1.7; }
.auth-note.danger { color: var(--c-fail); background: var(--c-fail-soft); }
.submit-button { width: 100%; margin-top: 4px; }
.account-link { margin: 22px 0 0; color: var(--c-text-tertiary); font-size: 12px; text-align: center; }
.account-link a { margin-left: 4px; color: var(--c-accent); font-weight: 500; text-underline-offset: 3px; }
.login-meta { display: flex; justify-content: space-between; margin-top: 40px; padding-top: 18px; border-top: 1px solid var(--c-border-soft); color: var(--c-text-tertiary); font-size: 11px; }
.login-meta strong { color: var(--c-text-secondary); font-weight: 500; }
@media (max-width: 760px) {
 .login-page { padding: 20px; }
 .login-shell { max-width: 440px; grid-template-columns: 1fr; min-height: 0; }
 .login-story { padding: 26px 28px; border-right: 0; border-bottom: 1px solid var(--c-border); }
 .story-copy, .story-footer { display: none; }
 .login-access { padding: 32px 28px; }
}
</style>
