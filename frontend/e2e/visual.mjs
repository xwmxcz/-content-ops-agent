/**
 * Visual + computed-style regression pass for the two extracted components.
 *
 * A screenshot only proves something is broken if a human looks at it. What this
 * script can actually ASSERT is computed style at the breakpoints — the same
 * invariants ChatLayout.spec.ts checks statically. Running it in a real browser
 * proves the rules still REACH the elements after the markup moved into a child
 * component, which is the failure mode a stylesheet-only check cannot catch:
 * scoped CSS tags only a child's root element, so a parent rule that targeted a
 * descendant would still parse and silently stop applying.
 */
import { chromium } from '@playwright/test'
import { mkdirSync } from 'node:fs'

const BASE = 'http://127.0.0.1:5173'
const OUT = 'e2e/shots'
mkdirSync(OUT, { recursive: true })

const user = `visual_${Date.now()}`
const browser = await chromium.launch()
const page = await browser.newPage()

const problems = []
page.on('console', m => {
  if (m.type() === 'error') problems.push(`console.error: ${m.text()}`)
})
page.on('pageerror', e => problems.push(`pageerror: ${e.message}`))

await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
const session = await page.evaluate(async u => {
  const r = await fetch('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: u, password: 'visual-regression-pass-1' })
  })
  const body = await r.json().catch(() => ({}))
  return { token: body.access_token ?? null, userId: body.user?.id ?? null }
}, user)
const { token, userId } = session
if (!token) {
  console.log('could not obtain a session; is the API running?')
  process.exit(1)
}
await page.evaluate(t => localStorage.setItem('content_ops_agent_auth_token', t), token)

// Seed one thread for THIS user. Registration creates an isolated workspace, so a
// row owned by another account would legitimately be invisible here.
//
// The container is addressed explicitly rather than via `-d content_ops` alone:
// `psql` inside the container defaults to its own localhost, which is not
// necessarily the database the API is pointed at.
if (userId && process.env.SEED_THREAD !== '0') {
  const { execFileSync } = await import('node:child_process')
  const db = process.env.SEED_DB || 'content_ops'
  const sql = `INSERT INTO agent_threads (id, user_id, title, pinned, archived, title_pinned, created_at, updated_at)
     VALUES ('visual-thread', '${userId}', '视觉回归测试会话', false, false, false, now(), now())
     ON CONFLICT (id) DO UPDATE SET user_id = EXCLUDED.user_id;`
  try {
    execFileSync('docker', ['exec', 'content-ops-test-pg', 'psql', '-U', 'content_ops', '-d', db, '-c', sql], { stdio: 'ignore' })
    console.log(`seeded one thread for ${userId} into ${db}`)
  } catch (e) {
    console.log('seed skipped:', String(e.message).split(String.fromCharCode(10))[0])
  }
}

const results = []
function check(label, actual, expected) {
  const ok = actual === expected
  results.push(ok)
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}: ${JSON.stringify(actual)}${ok ? '' : `  (expected ${JSON.stringify(expected)})`}`)
}

// ---------------------------------------------------------------- Chat, desktop
await page.setViewportSize({ width: 1440, height: 900 })
await page.goto(`${BASE}/chat`, { waitUntil: 'networkidle' })
await page.waitForTimeout(500)

const panel = await page.evaluate(() => {
  const p = document.querySelector('.thread-panel')
  if (!p) return null
  const cs = getComputedStyle(p)
  return {
    display: cs.display,
    tracks: cs.gridTemplateRows.trim().split(/\s+/).length,
    padding: cs.padding,
    background: cs.backgroundColor,
    borderRadius: cs.borderTopLeftRadius,
    borderWidth: cs.borderTopWidth
  }
})
console.log('\n-- .thread-panel (desktop) --')
console.log(JSON.stringify(panel, null, 2))
check('thread-panel renders as a grid', panel?.display, 'grid')
check('thread-panel keeps its 4-track grid', panel?.tracks, 4)
check('thread-panel has its border', panel?.borderWidth, '1px')
check('thread-panel keeps its background', panel?.background, 'rgb(237, 242, 238)')

// .panel-head now lives inside the child component. If the extracted rule did not
// survive the move, this would come back as `block`.
const head = await page.evaluate(() => {
  const h = document.querySelector('.thread-panel .panel-head')
  if (!h) return null
  const cs = getComputedStyle(h)
  return { display: cs.display, justifyContent: cs.justifyContent, margin: cs.margin }
})
console.log('\n-- .panel-head (now inside the child component) --')
console.log(JSON.stringify(head, null, 2))
check('panel-head is still flex', head?.display, 'flex')
check('panel-head is still space-between', head?.justifyContent, 'space-between')
check('panel-head kept its margin', head?.margin, '0px 6px')

const pill = await page.evaluate(() => {
  const b = document.querySelector('.panel-head strong')
  return b ? { radius: getComputedStyle(b).borderRadius, padding: getComputedStyle(b).padding } : null
})
console.log('\n-- .panel-head strong --')
console.log(JSON.stringify(pill))
check('count badge kept its pill radius', pill?.radius !== '0px', true)

// ------------------------------------------------- the hover invariant, in a browser
const rows = await page.evaluate(() => document.querySelectorAll('.thread-item').length)
check('a thread row is rendered', rows > 0, true)

const beforeHover = await page.evaluate(() => {
  const a = document.querySelector('.thread-actions')
  const t = document.querySelector('.thread-item-body')
  if (!a || !t) return null
  const acs = getComputedStyle(a)
  return {
    visibility: acs.visibility,
    display: acs.display,
    rowHeight: t.getBoundingClientRect().height,
    titleWidth: t.getBoundingClientRect().width
  }
})
console.log('\n-- .thread-actions before hover --')
console.log(JSON.stringify(beforeHover, null, 2))
check('actions are reserved but hidden before hover', beforeHover?.visibility, 'hidden')
check('actions keep display:flex while hidden', beforeHover?.display, 'flex')

await page.locator('.thread-item').first().hover()
await page.waitForTimeout(300)

const afterHover = await page.evaluate(() => {
  const a = document.querySelector('.thread-actions')
  const t = document.querySelector('.thread-item-body')
  if (!a || !t) return null
  return {
    visibility: getComputedStyle(a).visibility,
    rowHeight: t.getBoundingClientRect().height,
    titleWidth: t.getBoundingClientRect().width
  }
})
console.log('\n-- .thread-actions on hover --')
console.log(JSON.stringify(afterHover, null, 2))
check('actions become visible on hover', afterHover?.visibility, 'visible')
check(
  'title target width does not shift on hover',
  Math.abs((afterHover?.titleWidth ?? 0) - (beforeHover?.titleWidth ?? 0)) < 1,
  true
)
check(
  'row height does not shift on hover',
  Math.abs((afterHover?.rowHeight ?? 0) - (beforeHover?.rowHeight ?? 0)) < 1,
  true
)

const labels = await page.evaluate(() =>
  Array.from(document.querySelectorAll('.thread-actions button')).map(b => b.getAttribute('aria-label'))
)
console.log('\n-- thread action buttons --')
console.log(JSON.stringify(labels))
check('all four thread actions render', labels.length, 4)

await page.screenshot({ path: `${OUT}/chat-desktop.png`, fullPage: true })

// -------------------------------------------------------------------- Chat, mobile
await page.setViewportSize({ width: 390, height: 844 })
await page.goto(`${BASE}/chat`, { waitUntil: 'networkidle' })
await page.waitForTimeout(500)

const mobile = await page.evaluate(() => {
  const p = document.querySelector('.thread-panel')
  const a = document.querySelector('.thread-actions')
  return {
    order: p ? getComputedStyle(p).order : null,
    maxHeight: p ? getComputedStyle(p).maxHeight : null,
    actionsVisibility: a ? getComputedStyle(a).visibility : null
  }
})
console.log('\n-- .thread-panel (mobile) --')
console.log(JSON.stringify(mobile, null, 2))
check('panel stacks second on mobile', mobile?.order, '2')
check('panel keeps its mobile height cap', mobile?.maxHeight, '350px')
check('actions stay visible without hover on touch', mobile?.actionsVisibility, 'visible')

await page.screenshot({ path: `${OUT}/chat-mobile.png`, fullPage: true })

// ------------------------------------------------------------------ Studio, both
for (const [name, width, height] of [['desktop', 1440, 900], ['mobile', 390, 844]]) {
  await page.setViewportSize({ width, height })
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(500)
  const probe = await page.evaluate(() => ({
    studioPage: !!document.querySelector('.studio-page'),
    banner: !!document.querySelector('.studio-banner'),
    h1: document.querySelector('h1')?.textContent?.trim() ?? null,
    // The step dialog is teleported to body and closed; its stylesheet only needs
    // to be present, which the build already guarantees. Confirm the page itself.
    prose: document.querySelector('.studio-surface') ? true : false
  }))
  console.log(`\n-- studio (${name}) --`)
  console.log(JSON.stringify(probe))
  check(`studio renders at ${name}`, probe.studioPage, true)
  await page.screenshot({ path: `${OUT}/studio-${name}.png`, fullPage: true })
}

const passed = results.filter(Boolean).length
console.log(`\n${passed}/${results.length} checks passed`)
console.log('console/page errors:', problems.length ? problems.slice(0, 10) : 'none')
console.log(`screenshots written to ${OUT}/`)
await browser.close()
process.exit(passed === results.length && problems.length === 0 ? 0 : 1)
