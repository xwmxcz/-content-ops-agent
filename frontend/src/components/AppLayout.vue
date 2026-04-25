<template>
  <el-container class="shell">
    <el-aside width="244px" class="sidebar">
      <div class="brand">
        <div class="brand-mark">CO</div>
        <div>
          <strong>Content Ops</strong>
          <span>AI 内容运营系统</span>
        </div>
      </div>
      <el-menu router :default-active="$route.path" class="nav">
        <el-menu-item index="/">
          <el-icon><House /></el-icon>
          <span>工作台</span>
        </el-menu-item>
        <el-menu-item index="/generate">
          <el-icon><EditPen /></el-icon>
          <span>内容生成</span>
        </el-menu-item>
        <el-menu-item index="/refine">
          <el-icon><MagicStick /></el-icon>
          <span>内容打磨</span>
        </el-menu-item>
        <el-menu-item index="/history">
          <el-icon><Tickets /></el-icon>
          <span>历史内容</span>
        </el-menu-item>
        <el-menu-item index="/calendar">
          <el-icon><Calendar /></el-icon>
          <span>发布日历</span>
        </el-menu-item>
        <el-menu-item index="/stats">
          <el-icon><TrendCharts /></el-icon>
          <span>统计分析</span>
        </el-menu-item>
        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>Agent 对话</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="topbar">
        <div class="toolbar">
          <el-tag type="success" effect="plain">FastAPI</el-tag>
          <el-tag type="info" effect="plain">Vue 3</el-tag>
          <el-tag type="warning" effect="plain">LiteLLM</el-tag>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import {
  Calendar,
  ChatDotRound,
  EditPen,
  House,
  MagicStick,
  Tickets,
  TrendCharts
} from '@element-plus/icons-vue'
</script>

<style scoped>
.shell {
  min-height: 100vh;
}

.sidebar {
  background: #20242a;
  color: #ffffff;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 72px;
  padding: 0 18px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 8px;
  background: #2f8f83;
  font-weight: 700;
}

.brand span {
  display: block;
  margin-top: 2px;
  color: #b7bec8;
  font-size: 12px;
}

.nav {
  border-right: 0;
  background: transparent;
}

.nav :deep(.el-menu-item) {
  color: #d7dce3;
}

.nav :deep(.el-menu-item.is-active) {
  color: #ffffff;
  background: rgba(47, 143, 131, 0.28);
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  background: #ffffff;
  border-bottom: 1px solid #e4e7ed;
}

.main {
  padding: 0;
  background: #f6f7f9;
}

@media (max-width: 760px) {
  .sidebar {
    display: none;
  }
}
</style>
