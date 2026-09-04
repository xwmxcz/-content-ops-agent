import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.spec.ts', 'tests/**/*.spec.ts'],
    // Timers are faked per-suite, not globally: the SSE tests drive backoff with
    // vi.advanceTimersByTime, while component tests need real microtask flushing.
    restoreMocks: true,
    clearMocks: true
  }
})
