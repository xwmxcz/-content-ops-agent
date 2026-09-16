<template>
  <el-config-provider :locale="zhCn">
    <router-view v-if="route.meta.public" />
    <AppLayout v-else />
  </el-config-provider>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import { ElConfigProvider } from 'element-plus/es/components/config-provider/index'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import AppLayout from './components/AppLayout.vue'

const route = useRoute()
</script>
