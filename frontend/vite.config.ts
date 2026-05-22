import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// element-plus is cherry-picked in src/main.ts but still produces a single ~900KB
// chunk because the default object-form manualChunks rule routes every
// `element-plus/es/components/*` import into one bucket. Heavy components
// (calendar, date-picker, dialog, etc.) carry day.js + transitions and dominate
// the bundle, so we peel them into a separate chunk that loads alongside the
// initial app and lets the rest of element-plus stay smaller.
const ELEMENT_HEAVY_COMPONENTS = [
  'calendar',
  'date-picker',
  'dialog',
  'slider',
  'tabs',
  'segmented',
]

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
            if (id.includes('element-plus')) {
              const heavy = ELEMENT_HEAVY_COMPONENTS.find((name) =>
                id.includes(`element-plus/es/components/${name}/`)
              )
              if (heavy) return 'element-heavy'
              return 'element'
            }
            if (id.includes('@element-plus/icons-vue')) return 'element-icons'
            if (id.includes('echarts') || id.includes('vue-echarts') || id.includes('zrender')) {
              return 'charts'
            }
            if (id.includes('vue-router') || id.includes('/pinia/') || id.match(/\/vue\//)) {
              return 'vue'
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
