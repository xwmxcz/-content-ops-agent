<template>
  <div class="shell">
    <aside class="shell-sidebar">
      <div class="brand-block">
        <div class="brand-mark">CO</div>
        <div class="brand-copy">
          <strong>Content Ops</strong>
          <span>Strategy, drafting and review in one flow.</span>
        </div>
      </div>

      <nav class="sidebar-nav" aria-label="Primary">
        <div class="nav-section">
          <span class="nav-caption">Workspace</span>
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
          <span class="nav-caption">Operations</span>
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
        <span class="foot-kicker">Pipeline</span>
        <strong>4-stage content system</strong>
        <p>Strategy, Writer, Editor, Review</p>
      </div>
    </aside>

    <div class="shell-main">
      <header class="shell-topbar">
        <div class="topbar-copy">
          <span class="topbar-kicker">Content Operations Console</span>
          <strong>{{ currentPage.label }}</strong>
        </div>
        <div class="topbar-pills">
          <span class="topbar-pill live">Pipeline Ready</span>
          <span class="topbar-pill">FastAPI</span>
          <span class="topbar-pill">Vue 3</span>
          <span class="topbar-pill">LiteLLM</span>
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
  House,
  MagicStick,
  Tickets,
  TrendCharts
} from '@element-plus/icons-vue'

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
  { to: '/chat', label: 'Agent 对话', icon: ChatDotRound }
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

function isActive(path: string, exact = false) {
  return exact ? route.path === path : route.path === path || route.path.startsWith(`${path}/`)
}
</script>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 272px minmax(0, 1fr);
  min-height: 100vh;
  background:
    linear-gradient(180deg, rgba(196, 171, 132, 0.12) 0%, rgba(196, 171, 132, 0) 18%),
    linear-gradient(135deg, #f7f1e7 0%, #eef2f4 42%, #ebf0ee 100%);
}

.shell-sidebar {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 18px;
  color: #edf2ef;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0)),
    linear-gradient(180deg, #12222a 0%, #182a2f 48%, #20363a 100%);
  border-right: 1px solid rgba(255, 255, 255, 0.08);
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 2px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 8px;
  color: #102228;
  font-weight: 800;
  background: linear-gradient(135deg, #d8c08e, #7ad2c0);
}

.brand-copy {
  min-width: 0;
}

.brand-copy strong,
.sidebar-foot strong {
  display: block;
  font-size: 15px;
}

.brand-copy span,
.sidebar-foot p {
  display: block;
  margin-top: 4px;
  color: rgba(237, 242, 239, 0.66);
  font-size: 12px;
  line-height: 1.5;
}

.sidebar-nav {
  display: grid;
  gap: 18px;
}

.nav-section {
  display: grid;
  gap: 8px;
}

.nav-caption,
.foot-kicker,
.topbar-kicker {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.nav-caption,
.foot-kicker {
  color: rgba(216, 228, 224, 0.52);
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 42px;
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: 8px;
  color: rgba(237, 242, 239, 0.86);
  text-decoration: none;
  transition: background-color 120ms ease, border-color 120ms ease, transform 120ms ease;
}

.nav-link:hover {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.06);
}

.nav-link.active {
  color: #ffffff;
  background: linear-gradient(135deg, rgba(122, 210, 192, 0.14), rgba(216, 192, 142, 0.12));
  border-color: rgba(122, 210, 192, 0.22);
  transform: translateX(2px);
}

.sidebar-foot {
  margin-top: auto;
  padding: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
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
  padding: 16px 22px 0;
}

.topbar-copy strong {
  display: block;
  color: #162126;
  font-size: 20px;
}

.topbar-kicker {
  color: #6d756d;
}

.topbar-pills {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.topbar-pill {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 12px;
  border: 1px solid rgba(19, 34, 42, 0.1);
  border-radius: 999px;
  color: #49545a;
  background: rgba(255, 255, 255, 0.68);
  backdrop-filter: blur(8px);
  font-size: 12px;
}

.topbar-pill.live {
  color: #0f5d52;
  border-color: rgba(18, 128, 108, 0.16);
  background: rgba(122, 210, 192, 0.14);
}

.mobile-nav {
  display: none;
}

.shell-content {
  position: relative;
  min-width: 0;
  padding: 14px 0 22px;
}

.shell-content::before {
  content: '';
  position: absolute;
  inset: 0 22px auto;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(24, 42, 47, 0.1), transparent);
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
  }

  .mobile-nav {
    display: flex;
    gap: 8px;
    padding: 14px 16px 0;
    overflow: auto;
  }

  .mobile-link {
    flex: 0 0 auto;
    min-height: 34px;
    padding: 0 12px;
    border: 1px solid rgba(19, 34, 42, 0.1);
    border-radius: 999px;
    color: #405058;
    background: rgba(255, 255, 255, 0.72);
    text-decoration: none;
    font-size: 13px;
    line-height: 34px;
    white-space: nowrap;
  }

  .mobile-link.active {
    color: #102228;
    border-color: rgba(122, 210, 192, 0.34);
    background: rgba(122, 210, 192, 0.18);
  }

  .shell-content::before {
    inset: 0 16px auto;
  }
}
</style>
