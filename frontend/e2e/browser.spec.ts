import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, test, type Page } from '@playwright/test'
import { build } from 'vite'

const cookieName = 'content_ops_resource_session'
const fixturePath = process.env.E2E_FIXTURES
if (!fixturePath || !process.env.E2E_PASSWORD || !process.env.E2E_BASE_URL) {
  throw new Error('Run python3 scripts/verify_browser.py to create the isolated test stack')
}
const fixtures = JSON.parse(readFileSync(fixturePath, 'utf8'))
let streamBundle: string

test.beforeAll(async () => {
  // Exercise the repository's real composable with native EventSource; no fake
  // transport or production test endpoints. Login itself uses the built Vue UI.
  const result = await build({
    configFile: false,
    logLevel: 'error',
    build: {
      write: false,
      lib: {
        entry: resolve('src/composables/usePipelineStream.ts'),
        name: 'ContentOpsSSE', formats: ['iife'],
      },
    },
  })
  const output = Array.isArray(result) ? result[0] : result
  if (!('output' in output) || output.output[0].type !== 'chunk') throw new Error('Missing stream bundle')
  streamBundle = output.output[0].code
})

async function login(page: Page) {
  await page.goto('/login')
  await page.getByPlaceholder('请输入管理员密码').fill(process.env.E2E_PASSWORD!)
  await page.getByRole('button', { name: '进入工作台' }).click()
  await expect(page).toHaveURL(new URL('/', process.env.E2E_BASE_URL!).href)
}

async function status(page: Page, path: string, headers: Record<string, string> = {}) {
  return page.evaluate(async ({ path, headers }) =>
    (await fetch(path, { headers, cache: 'no-store' })).status, { path, headers })
}

async function startStream(page: Page, runId: string, staleAfterMs = 2500) {
  await page.addScriptTag({ content: streamBundle })
  await page.evaluate(({ runId, staleAfterMs }) => {
    const w = window as any
    w.probe = { text: '', states: [] as string[], completed: 0 }
    const noop = () => {}
    w.stream = w.ContentOpsSSE.usePipelineStream({
      onPlanReady: noop, onStepStart: noop, onToolCallStart: noop,
      onToolCallResult: noop, onStepComplete: noop, onStepFailed: noop,
      onPlanRevised: noop, onRunFailed: noop,
      onStepToken: (_index: number, delta: string) => { w.probe.text += delta },
      onRunComplete: () => { w.probe.completed++ },
      onStateChange: ({ state }: { state: string }) => { w.probe.states.push(state) },
    }, { staleAfterMs, initialDelayMs: 100, maxDelayMs: 500 })
    w.stream.subscribe(runId)
  }, { runId, staleAfterMs })
  await expect.poll(() => page.evaluate(() => (window as any).probe.text)).toBe('A')
}

function compose(...args: string[]) {
  return execFileSync('docker', ['compose', '-p', process.env.E2E_PROJECT!,
    '-f', process.env.E2E_COMPOSE!, ...args], { encoding: 'utf8' })
}

test('Vue login sets a restricted HttpOnly cookie; browser images and Range work over TLS', async ({ page, context }) => {
  await login(page)
  const cookie = (await context.cookies()).find(item => item.name === cookieName)
  expect(cookie).toMatchObject({ httpOnly: true, secure: true, sameSite: 'Strict', path: '/api' })
  // Read document.cookie on /api, where path scoping cannot hide a non-HttpOnly cookie.
  await page.goto('/api/health')
  expect(await page.evaluate(() => document.cookie.includes('content_ops_resource_session'))).toBe(false)
  expect(await status(page, '/api/content')).toBe(401) // Cookie never authorizes general APIs.
  const result = await page.evaluate(async ({ media_id, media_size }) => {
    const path = `/api/media/${media_id}/file`
    const image = new Image()
    const loaded = new Promise<boolean>(resolve => {
      image.onload = () => resolve(image.naturalWidth === 1)
      image.onerror = () => resolve(false)
    })
    image.src = path
    document.body.append(image)
    const range = await fetch(path, { headers: { Range: 'bytes=0-7' } })
    const invalid = await fetch(path, { headers: { Range: `bytes=${media_size + 10}-` } })
    return { loaded: await loaded, status: range.status, range: range.headers.get('content-range'),
      bytes: [...new Uint8Array(await range.arrayBuffer())], invalid: invalid.status }
  }, fixtures)
  expect(result).toEqual({ loaded: true, status: 206, range: `bytes 0-7/${fixtures.media_size}`,
    bytes: [137, 80, 78, 71, 13, 10, 26, 10], invalid: 416 })
})

test('edge rejects URL credentials without writing their values to access logs', async ({ page }) => {
  await login(page)
  const marker = 'e2e-query-credential-must-not-be-logged'
  for (const key of ['access_token', 'access_ticket']) {
    expect(await status(page, `/api/media/${fixtures.media_id}/file?${key}=${marker}`)).toBe(400)
  }
  await page.evaluate(async marker => {
    await fetch('/api/health', { referrer: `${location.origin}/?access_ticket=${marker}` })
  }, marker)
  const logs = compose('logs', '--no-color', 'frontend')
  // Prove sanitization, not absence of logging. Each rejected request should
  // produce exactly one query-free record, with no inherited default log.
  expect(logs.split(`GET /api/media/${fixtures.media_id}/file HTTP/1.1" 400`).length - 1).toBe(2)
  expect(logs.includes(marker)).toBe(false)
})

test('logout clears resource cookie and blocks new media and stream requests', async ({ page, context }) => {
  await login(page)
  const result = await page.evaluate(async () => {
    const token = localStorage.getItem('content_ops_agent_auth_token')
    const response = await fetch('/api/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
    localStorage.removeItem('content_ops_agent_auth_token')
    return response.status
  })
  expect(result).toBe(204)
  expect((await context.cookies()).some(item => item.name === cookieName)).toBe(false)
  expect(await status(page, `/api/media/${fixtures.media_id}/file`)).toBe(401)
  expect(await status(page, '/api/agent/runs/e2e_auth/stream')).toBe(401)
})

test('heartbeat prevents false stale state after a sequenced event', async ({ page }) => {
  await login(page)
  await startStream(page, 'e2e_idle')
  // Observe beyond the client's silence budget but before the server's 8s
  // stream deadline. A comment-only heartbeat cannot reach EventSource listeners.
  await page.waitForTimeout(4500)
  const observed = await page.evaluate(() => {
    const w = window as any
    const result = { ...w.probe, status: w.stream.getStatus() }
    w.stream.close()
    return result
  })
  expect(observed.states).not.toContain('stale')
  expect(observed.status.state).toBe('open')
  expect(observed.status.lastSeq).toBe(1)
  expect(observed.text).toBe('A')
})

test('native stream reconnects through TLS with after_seq and applies missed events once', async ({ page }) => {
  await login(page)
  const urls: string[] = []
  page.on('request', request => {
    if (request.url().includes('/e2e_reconnect/stream')) urls.push(request.url())
  })
  await startStream(page, 'e2e_reconnect')
  // The real backend closes at its configured stream deadline; the composable
  // must open another native connection with its cursor, not fail the run.
  await expect.poll(() => urls.some(url => new URL(url).searchParams.get('after_seq') === '1'),
    { timeout: 15_000 }).toBe(true)
  compose('exec', '-T', 'api', 'python', 'e2e_seed.py', 'complete')
  await expect.poll(() => page.evaluate(() => (window as any).probe.completed)).toBe(1)
  const observed = await page.evaluate(() => ({ ...(window as any).probe,
    status: (window as any).stream.getStatus() }))
  expect(observed.text).toBe('AB')
  expect(observed.status).toMatchObject({ state: 'closed', lastSeq: 3 })
  expect(observed.states).toContain('reconnecting')
  expect(urls.every(url => !/access_token|access_ticket/.test(url))).toBe(true)
})

test('real token expiry rejects expired cookies and bearer tokens', async ({ page, context }) => {
  test.setTimeout(80_000)
  await login(page)
  const cookie = (await context.cookies()).find(item => item.name === cookieName)!
  expect(await status(page, `/api/media/${fixtures.media_id}/file`)).toBe(200)
  await page.waitForTimeout(Math.max(0, cookie.expires * 1000 - Date.now()) + 1500)
  expect((await context.cookies()).some(item => item.name === cookieName)).toBe(false)
  // Keep the already-expired token in a new browser cookie to independently
  // prove server validation, rather than just the browser's cookie expiry.
  await context.addCookies([{ ...cookie, expires: Math.floor(Date.now() / 1000) + 60 }])
  expect(await status(page, `/api/media/${fixtures.media_id}/file`)).toBe(401)
  expect(await status(page, '/api/agent/runs/e2e_auth/stream')).toBe(401)
  expect(await status(page, '/api/content', { Authorization: `Bearer ${cookie.value}` })).toBe(401)
})
