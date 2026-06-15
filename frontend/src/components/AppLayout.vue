<template>
  <div class="shell">
    <aside class="shell-sidebar">
      <div class="brand-block">
        <div class="brand-mark">CO</div>
        <div class="brand-copy">
          <strong>Content Ops Agent</strong>
          <span>Content command center</span>
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
        <span class="foot-kicker">运行状态</span>
        <strong>Workspace Ready</strong>
        <p>API、内容库、排期流程已连接</p>
      </div>
    </aside>

    <div class="shell-main">
      <header class="shell-topbar">
        <div class="topbar-copy">
          <span class="topbar-kicker">Workspace</span>
          <strong>{{ currentPage.label }}</strong>
        </div>
        <div class="topbar-pills">
          <span class="topbar-pill live">就绪</span>
          <span class="topbar-pill">Production UI</span>
          <el-button v-if="canLogout" class="logout-button" text @click="handleLogout">
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
import { computed } from 'vue'
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
import { hasAuthToken, logout } from '../api/auth'

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

const canLogout = computed(() => hasAuthToken())

function isActive(path: string, exact = false) {
  return exact ? route.path === path : route.path === path || route.path.startsWith(`${path}/`)
}

function handleLogout() {
  logout()
}
</script>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr);
  min-height: 100vh;
  background: var(--c-bg);
}

.shell-sidebar {
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 20px 16px;
  color: var(--c-sidebar-text);
  background: var(--c-sidebar);
  border-right: 1px solid var(--c-sidebar-border);
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 8px 18px;
  border-bottom: 1px solid var(--c-sidebar-border);
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  color: #ffffff;
  font-weight: 600;
  font-size: 12px;
  letter-spacing: 0;
  background: linear-gradient(135deg, #2563eb, #38bdf8);
}

.brand-copy {
  min-width: 0;
}

.brand-copy strong {
  display: block;
  color: var(--c-sidebar-text);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0;
}

.brand-copy span {
  display: block;
  margin-top: 2px;
  color: var(--c-sidebar-muted);
  font-size: 11px;
  line-height: 1.4;
}

.sidebar-foot strong {
  display: block;
  color: var(--c-sidebar-text);
  font-size: 12px;
  font-weight: 500;
}

.sidebar-foot p {
  display: block;
  margin: 4px 0 0;
  color: var(--c-sidebar-muted);
  font-size: 11px;
  line-height: 1.5;
}

.sidebar-nav {
  display: grid;
  gap: 20px;
}

.nav-section {
  display: grid;
  gap: 2px;
}

.nav-caption,
.foot-kicker,
.topbar-kicker {
  padding: 0 8px;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--c-sidebar-muted);
  margin-bottom: 4px;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 30px;
  padding: 0 8px;
  border-radius: 4px;
  color: #d1d5db;
  text-decoration: none;
  font-size: 13px;
  font-weight: 500;
  position: relative;
  transition:
    background-color 80ms ease,
    color 80ms ease;
}

.nav-link :deep(.el-icon) {
  font-size: 15px;
  color: var(--c-sidebar-muted);
}

.nav-link:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--c-sidebar-text);
}

.nav-link:hover :deep(.el-icon) {
  color: var(--c-sidebar-text);
}

.nav-link.active {
  color: #ffffff;
  background: rgba(37, 99, 235, 0.26);
}

.nav-link.active :deep(.el-icon) {
  color: var(--c-accent);
}

.nav-link.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 7px;
  bottom: 7px;
  width: 2px;
  border-radius: 999px;
  background: var(--c-accent);
}

.sidebar-foot {
  margin-top: auto;
  padding: 12px;
  border: 1px solid var(--c-sidebar-border);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
}

.foot-kicker {
  padding: 0;
  margin-bottom: 6px;
  color: var(--c-sidebar-muted);
}

.shell-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.shell-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 32px;
  border-bottom: 1px solid var(--c-border);
  background: #ffffff;
  min-height: 60px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}

.topbar-copy {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.topbar-copy strong {
  display: inline;
  color: var(--c-text);
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0;
}

.topbar-kicker {
  padding: 0;
  margin: 0;
  color: var(--c-text-tertiary);
}

.topbar-pills {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.topbar-pill {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border: 1px solid var(--c-border);
  border-radius: 999px;
  color: var(--c-text-secondary);
  background: var(--c-surface);
  font-size: 11px;
  font-weight: 500;
  font-family: var(--font-mono);
  letter-spacing: 0;
}

.topbar-pill.live {
  color: var(--c-ok);
  border-color: var(--c-ok);
  background: var(--c-ok-soft);
  position: relative;
  padding-left: 18px;
}

.topbar-pill.live::before {
  content: '';
  position: absolute;
  left: 8px;
  top: 50%;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--c-ok);
  transform: translateY(-50%);
}

.logout-button {
  margin-left: 2px;
  color: var(--c-text-secondary);
}

.logout-button :deep(.el-icon) {
  margin-right: 4px;
}

.mobile-nav {
  display: none;
}

.shell-content {
  position: relative;
  min-width: 0;
  padding: 0;
  background: var(--c-bg);
}

@media (max-width: 980px) {
  .shell {
    grid-template-columns: 1fr;
  }

  .shell-sidebar {
    display: none;
  }

  .shell-topbar {
    align-items: flex-start;
    flex-direction: column;
    padding: 12px 16px;
  }

  .mobile-nav {
    display: flex;
    gap: 4px;
    padding: 8px 16px 12px;
    border-bottom: 1px solid var(--c-border);
    overflow: auto;
  }

  .mobile-link {
    flex: 0 0 auto;
    height: 28px;
    padding: 0 10px;
    border: 1px solid var(--c-border);
    border-radius: 999px;
    color: var(--c-text-secondary);
    background: var(--c-surface);
    text-decoration: none;
    font-size: 12px;
    font-weight: 500;
    line-height: 26px;
    white-space: nowrap;
  }

  .mobile-link.active {
    color: var(--c-accent);
    border-color: var(--c-accent);
    background: var(--c-accent-soft);
  }
}
</style>
