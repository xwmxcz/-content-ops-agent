import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  retries: 0,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['json', { outputFile: 'test-results/e2e-results.json' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL,
    browserName: 'chromium',
    // Only the isolated test proxy's ephemeral self-signed certificate.
    ignoreHTTPSErrors: true,
    launchOptions: {
      executablePath: process.env.E2E_CHROMIUM_EXECUTABLE,
      args: ['--host-resolver-rules=MAP content-ops.test 127.0.0.1', '--no-proxy-server'],
    },
    // Avoid storing passwords, bearer tokens or cookies in trace artifacts.
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
})
