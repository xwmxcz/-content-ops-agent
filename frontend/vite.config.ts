import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiProxyTarget = env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

  return {
    plugins: [vue()],
    build: {
      chunkSizeWarningLimit: 600,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) return undefined
            if (
              id.includes('vue-router') ||
              id.includes('/pinia/') ||
              id.includes('/vue/') ||
              id.includes('/@vue/')
            ) {
              return 'framework'
            }
            if (id.includes('echarts') || id.includes('vue-echarts') || id.includes('zrender')) {
              return 'charts'
            }
            if (id.includes('axios')) return 'http'
            return undefined
          },
        },
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: apiProxyTarget,
          changeOrigin: true
        }
      }
    }
  }
})
