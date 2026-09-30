import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    // Component styles import CSS from package entry points; Vite must process
    // those imports instead of passing them to Node's ESM loader.
    server: { deps: { inline: ['element-plus'] } },
    globals: true,
    include: ['src/**/*.spec.ts', 'tests/**/*.spec.ts'],
    // Timers are faked per-suite, not globally: the SSE tests drive backoff with
    // vi.advanceTimersByTime, while component tests need real microtask flushing.
    restoreMocks: true,
    clearMocks: true
  }
})
