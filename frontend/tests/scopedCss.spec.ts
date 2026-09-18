/**
 * Guards against scoped-CSS rules declared in the wrong component.
 *
 * Vue's `scoped` styles compile to attribute selectors carrying that component's
 * own id (`.foo[data-v-abc123]`). A rule whose class belongs to ANOTHER
 * component's markup therefore matches nothing at all: it still parses, still
 * builds, still passes every declaration-level comparison — it simply never
 * applies. That is exactly how a set of Chat.vue rules ended up stranded in
 * ChatThreadPanel.vue during the component extraction, silently dropping the
 * empty-state, tool-trace, and composer styling.
 *
 * This test compares where each class is USED against where its rules are
 * DECLARED, and fails when a rule can never reach its element.
 *
 * Deliberate exceptions are listed below with the reason, so a new violation has
 * to be added here consciously rather than folding into the noise.
 */
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parse } from 'vue/compiler-sfc'

/** Rules that intentionally name another component's class. */
const ALLOWED = [
  // `:deep()` pierces the child's scope on purpose.
  { file: 'History.vue', cls: 'content-card', why: 'used with :deep() to restyle ContentCard' },
  { file: 'History.vue', cls: 'card-topline', why: 'used with :deep() to restyle ContentCard' },
  // The parent and the extracted child both define these; the parent styles its
  // own inline uses and the child styles its own.
  { file: 'Studio.vue', cls: 'surface-kicker', why: 'the page has its own .surface-kicker elements' },
  { file: 'Studio.vue', cls: 'surface-pill', why: 'the page has its own .surface-pill elements' },
  { file: 'Studio.vue', cls: 'research-tag', why: 'the page has its own .research-tag elements' },
  { file: 'Calendar.vue', cls: 'panel-kicker', why: 'Calendar defines its own .panel-kicker' },
  // Not a class of its own: `.surface-head.compact` / `.selector-grid.compact`.
  { file: 'Studio.vue', cls: 'compact', why: "compound selector on the page's own element" },
  { file: 'Calendar.vue', cls: 'compact', why: "compound selector on the page's own element" },
  // State classes added ALONGSIDE a base class the page does own, e.g.
  // `.tool-event.failed` and `.plan-board li.failed`. The detector sees only the
  // state class, but those elements live in this file and carry the base class too.
  { file: 'Chat.vue', cls: 'failed', why: 'state class on local .tool-event / .plan-board li' },
  { file: 'Studio.vue', cls: 'failed', why: 'state class on local .surface-* elements' },
]

function vueFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) return vueFiles(full)
    return entry.name.endsWith('.vue') ? [full] : []
  })
}

/** Classes appearing in a component's own <template>. */
function usedClasses(source: string): Set<string> {
  const { descriptor } = parse(source)
  const template = descriptor.template?.content ?? ''
  const out = new Set<string>()
  for (const m of template.matchAll(/class="([^"]*)"/g)) {
    for (const token of m[1].split(/\s+/)) {
      if (/^[a-zA-Z][\w-]*$/.test(token)) out.add(token)
    }
  }
  for (const m of template.matchAll(/:class="\{([^}]*)\}"/g)) {
    for (const q of m[1].matchAll(/['"]([a-zA-Z][\w-]*)['"]/g)) out.add(q[1])
  }
  return out
}

/** Classes named by a component's scoped <style> selectors. */
function declaredClasses(source: string): Set<string> {
  const { descriptor } = parse(source)
  const css = descriptor.styles.filter(s => s.scoped).map(s => s.content).join('\n')
  const out = new Set<string>()
  for (const m of css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/\.([a-zA-Z][\w-]*)/g)) {
    out.add(m[1])
  }
  return out
}

describe('scoped CSS ownership', () => {
  const files = vueFiles('src')
  const parsed = files.map(f => ({ path: f, name: f.replace(/\\/g, '/').split('/').pop()!, src: readFileSync(f, 'utf8') }))
  const used = new Map(parsed.map(p => [p.path, usedClasses(p.src)]))

  it('never declares a scoped rule for a class only another component uses', () => {
    const violations: string[] = []
    for (const file of parsed) {
      const declared = declaredClasses(file.src)
      const own = used.get(file.path)!
      for (const cls of declared) {
        if (own.has(cls)) continue
        const usedElsewhere = parsed.filter(o => o.path !== file.path && used.get(o.path)!.has(cls))
        if (!usedElsewhere.length) continue
        if (ALLOWED.some(a => a.file === file.name && a.cls === cls)) continue
        violations.push(
          `${file.name}: .${cls} is only used by ${usedElsewhere.map(o => o.name).join(', ')}, ` +
          `so this scoped rule can never match. Move it, or add an ALLOWED entry with a reason.`
        )
      }
    }
    expect(violations).toEqual([])
  })

  it('keeps every ALLOWED entry honest (the rule must still exist)', () => {
    // Stops the allow-list rotting into a list of entries nothing references.
    const stale = ALLOWED.filter(a => {
      const file = parsed.find(p => p.name === a.file)
      return !file || !declaredClasses(file.src).has(a.cls)
    })
    expect(stale.map(s => `${s.file}: .${s.cls}`)).toEqual([])
  })
})
