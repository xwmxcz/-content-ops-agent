import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import type { App } from 'vue'

const startup = vi.hoisted(() => ({
  path: '/register',
  navigation: Promise.resolve(),
  workspaceMounted: vi.fn()
}))

vi.mock('../src/components/AppLayout.vue', () => ({
  default: {
    mounted: startup.workspaceMounted,
    template: '<div data-workspace>Workspace</div>'
  }
}))
vi.mock('../src/api', () => ({ watchAccountChanges: vi.fn() }))
// Styles are handled by Vite in the browser; jsdom tests only exercise startup rendering.
vi.mock('element-plus/es/components/button/style/css', () => ({}))
vi.mock('element-plus/es/components/icon/style/css', () => ({}))
vi.mock('element-plus/es/components/input/style/css', () => ({}))
vi.mock('element-plus/es/components/message/style/css', () => ({}))
vi.mock('element-plus/es/components/select/style/css', () => ({}))
vi.mock('element-plus/es/components/radio-button/style/css', () => ({}))
vi.mock('element-plus/es/components/radio-group/style/css', () => ({}))

beforeEach(() => {
  vi.resetModules()
  document.body.innerHTML = '<div id="app"></div>'
  vi.doMock('../src/router', async () => {
    const { createMemoryHistory, createRouter } = await vi.importActual<typeof import('vue-router')>('vue-router')
    const history = createMemoryHistory()
    history.push(startup.path)
    const router = createRouter({
      history,
      routes: [
        { path: '/login', component: { template: '<div data-account-page>Login</div>' }, meta: { public: true } },
        { path: '/register', component: { template: '<div data-account-page>Register</div>' }, meta: { public: true } }
      ]
    })
    router.beforeEach(() => startup.navigation)
    return { default: router }
  })
})

afterEach(() => {
  const container = document.getElementById('app') as (HTMLElement & { __vue_app__?: App }) | null
  container?.__vue_app__?.unmount()
  document.body.innerHTML = ''
})

describe('initial application navigation', () => {
  it.each(['/register', '/login'])('waits for the initial %s route without mounting the private workspace', async path => {
    startup.path = path
    let finishNavigation!: () => void
    startup.navigation = new Promise<void>(resolve => { finishNavigation = resolve })

    await import('../src/main')
    await flushPromises()

    expect(document.getElementById('app')!.innerHTML).toBe('')
    expect(startup.workspaceMounted).not.toHaveBeenCalled()

    finishNavigation()
    const { default: router } = await import('../src/router')
    await router.isReady()
    await flushPromises()

    expect(router.currentRoute.value.path).toBe(path)
    expect(document.querySelector('[data-account-page]')?.textContent).toBe(path === '/register' ? 'Register' : 'Login')
    expect(startup.workspaceMounted).not.toHaveBeenCalled()
  })
})
