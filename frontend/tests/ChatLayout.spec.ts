import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { parse } from 'vue/compiler-sfc'
// The thread list (and its stylesheet) now lives in its own component, so the
// layout invariants are asserted against that file rather than the page.
import threadPanelSource from '../src/components/ChatThreadPanel.vue?raw'

describe('chat thread action layout', () => {
  const stylesheet = document.createElement('style')

  beforeAll(() => {
    stylesheet.textContent = parse(threadPanelSource).descriptor.styles[0].content
    document.head.append(stylesheet)
  })

  afterAll(() => stylesheet.remove())

  function rule(selector: string, rules = stylesheet.sheet!.cssRules): CSSStyleRule {
    const match = Array.from(rules).find(rule =>
      rule instanceof CSSStyleRule && rule.selectorText.split(',').map(s => s.trim()).includes(selector)
    )
    expect(match, `Missing CSS rule for ${selector}`).toBeDefined()
    return match as CSSStyleRule
  }

  it('reserves action space before hover so the title click target does not move', () => {
    const actions = rule('.thread-actions').style
    expect(actions.display).toBe('flex')
    expect(actions.visibility).toBe('hidden')
  })

  it.each([':hover', ':focus-within', '.active'])('reveals actions without relayout for %s', state => {
    const actions = rule(`.thread-item${state} .thread-actions`).style
    expect(actions.visibility).toBe('visible')
    expect(actions.getPropertyValue('display')).toBe('')
  })

  it('keeps actions visible on touch layouts', () => {
    const mobile = Array.from(stylesheet.sheet!.cssRules).find(rule =>
      rule instanceof CSSMediaRule && rule.conditionText === '(max-width: 820px)'
    ) as CSSMediaRule
    expect(rule('.thread-actions', mobile.cssRules).style.visibility).toBe('visible')
  })
})
