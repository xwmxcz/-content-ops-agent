<template>
  <div class="shell">
    <aside class="shell-sidebar">
      <div class="brand-block">
        <WorkspaceMark />
        <div class="brand-copy">
          <strong>Content Ops</strong>
          <span>内容创作工作台</span>
        </div>
      </div>

      <nav class="sidebar-nav" aria-label="Primary">
        <div class="nav-section">
          <span class="nav-caption">工作区</span>
          <router-link
            v-for="item in workspaceNav"
            :key="item.to"
            :to="item.to"
            class="nav-link"
            :class="{ active: isActive(item.to, item.exact) }"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </router-link>
        </div>

        <div class="nav-section">
          <span class="nav-caption">运营</span>
          <router-link
            v-for="item in operationsNav"
            :key="item.to"
            :to="item.to"
            class="nav-link"
            :class="{ active: isActive(item.to, item.exact) }"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </router-link>
        </div>
      </nav>

      <div class="sidebar-foot">
        <span class="workspace-avatar" aria-hidden="true">{{ user?.username.charAt(0).toUpperCase() || '·' }}</span>
        <div>
          <strong>{{ user?.username || '个人工作区' }}</strong>
          <p>你的专属内容与对话空间</p>
        </div>
      </div>
    </aside>

    <div class="shell-main">
      <header class="shell-topbar">
        <div class="topbar-copy">
          <span class="topbar-kicker">工作区</span>
          <span class="breadcrumb-divider" aria-hidden="true">/</span>
          <strong>{{ currentPage.label }}</strong>
        </div>
        <div class="topbar-pills">
          <span class="workspace-label">{{ user?.username }}</span>
          <el-button class="logout-button" text :loading="loggingOut" @click="handleLogout">
            <el-icon><SwitchButton /></el-icon>
            退出
          </el-button>
        </div>
      </header>

      <nav class="mobile-nav" aria-label="Mobile">
        <router-link
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="mobile-link"
          :class="{ active: isActive(item.to, item.exact) }"
        >
          {{ item.label }}
        </router-link>
      </nav>

      <main class="shell-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
// Displays workspace navigation and server-confirmed account identity.
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  Calendar,
  ChatDotRound,
  Collection,
  House,
  MagicStick,
  SwitchButton,
  Tickets,
  TrendCharts
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus/es/components/message/index'
import { getAuthStatus, logout, type AuthUser } from '../api/auth'
import WorkspaceMark from './WorkspaceMark.vue'

interface NavItem {
  to: string
  label: string
  icon: unknown
  exact?: boolean
}

const route = useRoute()

const workspaceNav: NavItem[] = [
  { to: '/', label: '内容工作台', icon: House, exact: true },
  { to: '/refine', label: '内容打磨', icon: MagicStick },
  { to: '/chat', label: 'Agent 对话', icon: ChatDotRound },
  { to: '/memory', label: '记忆管理', icon: Collection }
]

const operationsNav: NavItem[] = [
  { to: '/dashboard', label: '数据概览', icon: TrendCharts },
  { to: '/history', label: '历史内容', icon: Tickets },
  { to: '/calendar', label: '发布日历', icon: Calendar },
  { to: '/stats', label: '统计分析', icon: TrendCharts }
]

const navItems = [...workspaceNav, ...operationsNav]

const currentPage = computed(() => {
  return navItems.find(item => isActive(item.to, item.exact)) ?? workspaceNav[0]
})

const user = ref<AuthUser | null>(null)
const loggingOut = ref(false)

onMounted(async () => {
  try {
    const status = await getAuthStatus()
    user.value = status.authenticated ? status.user : null
  } catch {
    ElMessage.error('账号信息加载失败，请刷新重试')
  }
})

function isActive(path: string, exact = false) {
  return exact ? route.path === path : route.path === path || route.path.startsWith(`${path}/`)
}

async function handleLogout() {
  if (loggingOut.value) return
  loggingOut.value = true
  try {
    await logout()
  } catch {
    ElMessage.warning('已退出本机登录，服务端会话撤销未确认')
  } finally {
    loggingOut.value = false
  }
}
</script>

<style scoped>
.shell { display: grid; grid-template-columns: 224px minmax(0, 1fr); min-height: 100vh; background: var(--c-bg); }
.shell-sidebar { position: sticky; top: 0; height: 100vh; display: flex; flex-direction: column; gap: 36px; padding: 27px 16px 20px; color: var(--c-sidebar-text); background: var(--c-sidebar); border-right: 1px solid var(--c-sidebar-border); }
.brand-block { display: flex; align-items: center; gap: 9px; padding: 0 8px; }
.brand-copy { min-width: 0; }
.brand-copy strong { display: block; font-family: var(--font-display); color: var(--c-sidebar-text); font-size: 19px; font-weight: 600; letter-spacing: -.4px; line-height: 1.4; }
.brand-copy span { display: block; margin-top: 2px; color: var(--c-sidebar-muted); font-size: 10px; letter-spacing: 1.2px; }
.sidebar-nav { display: grid; gap: 30px; }
.nav-section { display: grid; gap: 5px; }
.nav-caption { padding: 0 14px; margin-bottom: 8px; font-size: 11px; letter-spacing: .8px; color: var(--c-sidebar-muted); }
.nav-link { display: flex; align-items: center; gap: 11px; min-height: 42px; padding: 0 14px; border-radius: 10px; color: var(--c-text-secondary); text-decoration: none; font-size: 13px; font-weight: 500; transition: background-color .15s, color .15s; }
.nav-link :deep(.el-icon) { font-size: 17px; color: var(--c-sidebar-muted); }
.nav-link:hover { background: var(--c-sidebar-soft); color: var(--c-accent); }
.nav-link.active { color: var(--c-accent); background: var(--c-surface); box-shadow: 0 2px 6px var(--c-accent-ring); }
.nav-link.active :deep(.el-icon) { color: var(--c-accent); }
.sidebar-foot { display: flex; align-items: center; gap: 10px; margin-top: auto; padding: 18px 8px 0; border-top: 1px solid var(--c-sidebar-border); }
.workspace-avatar { display: grid; place-items: center; flex: 0 0 32px; width: 32px; height: 32px; border: 1px solid var(--c-border-strong); border-radius: 50%; font-family: var(--font-editorial); font-size: 17px; color: var(--c-accent); }
.sidebar-foot > div { min-width: 0; }
.sidebar-foot strong { display: block; overflow: hidden; text-overflow: ellipsis; font-size: 12px; font-weight: 500; white-space: nowrap; }
.sidebar-foot p { margin: 3px 0 0; color: var(--c-sidebar-muted); font-size: 10px; }
.shell-main { min-width: 0; display: flex; flex-direction: column; }
.shell-topbar { position: sticky; top: 0; z-index: 20; display: flex; align-items: center; justify-content: space-between; gap: 16px; min-height: 68px; padding: 12px 32px; border-bottom: 1px solid var(--c-border); background: var(--c-surface); }
.topbar-copy { display: flex; align-items: center; gap: 14px; }
.topbar-copy strong { font-size: 12px; font-weight: 500; }
.topbar-kicker, .breadcrumb-divider { color: var(--c-text-tertiary); font-size: 12px; }
.breadcrumb-divider { color: var(--c-border-strong); }
.topbar-pills { display: flex; align-items: center; gap: 20px; }
.workspace-label { font-size: 11px; color: var(--c-text-tertiary); }
.logout-button { color: var(--c-text-secondary); }
.logout-button :deep(.el-icon) { margin-right: 5px; }
.mobile-nav { display: none; }
.shell-content { position: relative; flex: 1; min-width: 0; min-height: calc(100vh - 68px); }
@media (max-width: 980px) {
  .shell { grid-template-columns: 1fr; }
  .shell-sidebar { display: none; }
  .shell-topbar { padding: 12px 20px; min-height: 60px; }
  .mobile-nav { display: flex; gap: 6px; padding: 12px 16px; border-bottom: 1px solid var(--c-border); background: var(--c-surface); overflow: auto; }
  .mobile-link { flex: 0 0 auto; padding: 7px 12px; border-radius: var(--r-control); color: var(--c-text-secondary); text-decoration: none; font-size: 12px; white-space: nowrap; }
  .mobile-link.active { color: var(--c-accent); background: var(--c-accent-soft); }
}
@media (max-width: 540px) { .workspace-label { display: none; } .topbar-pills { gap: 8px; } }
</style>
