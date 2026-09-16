import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount, type VueWrapper } from '@vue/test-utils'
import AppLayout from '../src/components/AppLayout.vue'
import { getAuthStatus, logout } from '../src/api/auth'

vi.mock('vue-router', () => ({ useRoute: () => ({ path: '/chat' }) }))
vi.mock('../src/api/auth', () => ({ getAuthStatus: vi.fn(), logout: vi.fn() }))
vi.mock('element-plus/es/components/message/index', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn() }
}))

let wrapper: VueWrapper | undefined
const navigate = vi.fn()

beforeEach(() => {
  vi.mocked(getAuthStatus).mockResolvedValue({ authenticated: true, user: { id: 'user-id', username: 'writer' } })
  vi.mocked(logout).mockResolvedValue(undefined)
  const location = { ...window.location, replace: navigate }
  vi.stubGlobal('window', new Proxy(window, {
    get: (target, key) => key === 'location' ? location : Reflect.get(target, key, target)
  }))
})

afterEach(() => {
  wrapper?.unmount()
  vi.unstubAllGlobals()
})

async function open() {
  wrapper = shallowMount(AppLayout, {
    global: {
      stubs: {
        RouterLink: { template: '<a><slot /></a>' }, RouterView: true,
        ElIcon: { template: '<span><slot /></span>' },
        ElButton: { template: '<button><slot /></button>' }
      }
    }
  })
  await flushPromises()
  return wrapper
}

describe('workspace account identity', () => {
  it('shows the username and avatar initial returned by the status API', async () => {
    const view = await open()
    expect(getAuthStatus).toHaveBeenCalledOnce()
    expect(view.get('.sidebar-foot strong').text()).toBe('writer')
    expect(view.get('.workspace-label').text()).toBe('writer')
    expect(view.get('.workspace-avatar').text()).toBe('W')
  })

  it('leaves authentication navigation to the route guard when identity is absent', async () => {
    vi.mocked(getAuthStatus).mockResolvedValue({ authenticated: false, user: null })
    const view = await open()
    expect(navigate).not.toHaveBeenCalled()
    expect(view.get('.sidebar-foot strong').text()).toBe('个人工作区')
  })

  it('offers account logout from the workspace header', async () => {
    const view = await open()
    await view.get('.logout-button').trigger('click')
    await flushPromises()
    expect(logout).toHaveBeenCalledOnce()
  })
})
