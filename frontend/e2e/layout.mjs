/**
 * Baseline/after screenshots for the layout polish pass.
 *
 * Captures the same pages at the same viewports with a fixed seed so a before/after
 * comparison is meaningful, and reports the computed layout values the changes
 * target — otherwise "looks better" is the only available judgement.
 */
import { chromium } from '@playwright/test'
import { mkdirSync } from 'node:fs'

const BASE = process.env.BASE_URL || 'http://localhost:5173'
const OUT = process.env.SHOT_DIR || 'e2e/shots'
mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
const problems = []
page.on('console', m => { if (m.type() === 'error') problems.push(m.text()) })
page.on('pageerror', e => problems.push(e.message))

await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
const session = await page.evaluate(async u => {
  const r = await fetch('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: u, password: 'visual-regression-pass-1' })
  })
  const b = await r.json().catch(() => ({}))
  return { token: b.access_token ?? null, userId: b.user?.id ?? null }
}, `layout_${Date.now()}`)
if (!session.token) { console.log('no session'); process.exit(1) }
await page.evaluate(t => localStorage.setItem('content_ops_agent_auth_token', t), session.token)

// Seed content so the Refine page has something to show, plus a thread for Chat.
const { execFileSync } = await import('node:child_process')
const container = process.env.SEED_CONTAINER || 'content-ops-agent-postgres-1'
const seed = (sql) => {
  try {
    execFileSync('docker', ['exec', container, 'psql', '-U', 'content_ops', '-d', 'content_ops', '-c', sql], { stdio: 'ignore' })
  } catch (e) {
    console.log('seed skipped:', String(e.message).split(String.fromCharCode(10))[0])
  }
}
seed(`INSERT INTO agent_threads (id, user_id, title, pinned, archived, title_pinned, created_at, updated_at)
      VALUES ('layout-thread', '${session.userId}', '周末徒步路线推荐', false, false, false, now(), now())
      ON CONFLICT (id) DO UPDATE SET user_id = EXCLUDED.user_id;`)
seed(`INSERT INTO contents (user_id, title, content, content_type, style, status, created_at, updated_at)
      VALUES
      ('${session.userId}', '周末徒步路线推荐', '这条线路适合新手，全程约 8 公里，累计爬升 320 米。上午九点出发，午后即可返程。', 'xiaohongshu', 'casual', 'draft', now(), now()),
      ('${session.userId}', '露营装备清单', '帐篷、睡袋、防潮垫是三大件。此外建议带上头灯、驱蚊液和一套备用衣物。', 'blog', 'professional', 'draft', now(), now())
      ON CONFLICT DO NOTHING;`)

const viewports = [['desktop', 1600, 900], ['laptop', 1280, 800]]

for (const [name, width, height] of viewports) {
  await page.setViewportSize({ width, height })
  for (const [pageName, path] of [['chat', '/chat'], ['refine', '/refine']]) {
    await page.goto(BASE + path, { waitUntil: 'networkidle' })
    await page.waitForTimeout(700)
    await page.screenshot({ path: `${OUT}/${pageName}-${name}.png`, fullPage: false })
  }
}

// Report the layout facts the polish targets.
await page.setViewportSize({ width: 1600, height: 900 })
await page.goto(`${BASE}/refine`, { waitUntil: 'networkidle' })
await page.waitForTimeout(700)
const refine = await page.evaluate(() => {
  const box = sel => {
    const el = document.querySelector(sel)
    if (!el) return null
    const r = el.getBoundingClientRect()
    return { w: Math.round(r.width), h: Math.round(r.height) }
  }
  const section = document.querySelector('.result-section')
  const empty = document.querySelector('.result-empty')
  return {
    grid: getComputedStyle(document.querySelector('.refine-grid')).gridTemplateColumns,
    sourceBox: box('.source-section'),
    actionBox: box('.action-section'),
    resultBox: box('.result-section'),
    emptyBox: empty ? box('.result-empty') : null,
    emptyAlign: empty ? getComputedStyle(empty).alignItems : null,
    emptyJustify: empty ? getComputedStyle(empty).justifyContent : null,
    resultMinHeight: section ? getComputedStyle(section).minHeight : null
  }
})
console.log('REFINE:', JSON.stringify(refine, null, 2))

await page.goto(`${BASE}/chat`, { waitUntil: 'networkidle' })
await page.waitForTimeout(700)
const chat = await page.evaluate(() => {
  const box = sel => {
    const el = document.querySelector(sel)
    if (!el) return null
    const r = el.getBoundingClientRect()
    return { w: Math.round(r.width), h: Math.round(r.height) }
  }
  const log = document.querySelector('.chat-log')
  return {
    pageBox: box('.chat-page'),
    workbenchBox: box('.chat-workbench'),
    panelBox: box('.thread-panel'),
    dialogBox: box('.dialog-panel'),
    logBox: log ? box('.chat-log') : null,
    composerBox: box('.composer-actions') || box('.chat-composer') || null
  }
})
console.log('CHAT:', JSON.stringify(chat, null, 2))
console.log('errors:', problems.length ? problems.slice(0, 5) : 'none')
await browser.close()
