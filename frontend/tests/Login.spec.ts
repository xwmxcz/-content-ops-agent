import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ElButton } from 'element-plus/es/components/button/index'
import { ElIcon } from 'element-plus/es/components/icon/index'
import { ElInput } from 'element-plus/es/components/input/index'
import Login from '../src/views/Login.vue'
import { ApiError } from '../src/api'
import { getAuthStatus, login, register } from '../src/api/auth'

vi.mock('../src/api/auth', () => ({
  getAuthStatus: vi.fn(), login: vi.fn(), register: vi.fn()
}))
vi.mock('element-plus/es/components/message/index', () => ({
  ElMessage: { success: vi.fn() }
}))

const account = {
  access_token: 'session-token', token_type: 'bearer' as const,
  expires_at: 2_000_000_000, user: { id: 'user-id', username: 'writer' }
}
const navigate = vi.fn()
let wrapper: VueWrapper | undefined

beforeEach(() => {
  vi.mocked(getAuthStatus).mockResolvedValue({ authenticated: false, user: null })
  vi.mocked(login).mockResolvedValue(account)
  vi.mocked(register).mockResolvedValue(account)
  const location = { ...window.location, replace: navigate }
  vi.stubGlobal('window', new Proxy(window, {
    get: (target, key) => key === 'location' ? location : Reflect.get(target, key, target)
  }))
})

afterEach(() => {
  wrapper?.unmount()
  vi.unstubAllGlobals()
})

async function open(path = '/register') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', name: 'login', component: Login, meta: { public: true } },
      { path: '/register', name: 'register', component: Login, meta: { public: true } },
      { path: '/', component: { template: '<div>Workspace</div>' } },
      { path: '/history', component: { template: '<div>History</div>' } }
    ]
  })
  await router.push(path)
  wrapper = mount(Login, { global: { plugins: [router], components: { ElButton, ElIcon, ElInput } } })
  await flushPromises()
  return { wrapper, router }
}

async function fillForm(view: VueWrapper, username = 'writer', password = 'a long passphrase', confirm = password) {
  const inputs = view.findAll('input')
  await inputs[0].setValue(username)
  await inputs[1].setValue(password)
  if (inputs[2]) await inputs[2].setValue(confirm)
}

describe('account entry', () => {
  it('registers an independent workspace, preserves password whitespace, and reloads to the requested page', async () => {
    const { wrapper } = await open('/register?next=%2Fhistory%3Fview%3Ddraft')
    expect(wrapper.text()).toContain('每个账号有独立的内容与对话空间')
    expect(wrapper.find('input[autocomplete="new-password"]').exists()).toBe(true)
    await fillForm(wrapper, ' Writer ', '  a long passphrase  ')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(register).toHaveBeenCalledWith('Writer', '  a long passphrase  ')
    expect(login).not.toHaveBeenCalled()
    expect(navigate).toHaveBeenCalledWith('/history?view=draft')
  })

  it('requires matching password confirmation without calling the registration API', async () => {
    const { wrapper } = await open()
    await fillForm(wrapper, 'writer', 'a long passphrase', 'a different passphrase')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.get('[role="alert"]').text()).toContain('两次输入的密码不一致')
    expect(register).not.toHaveBeenCalled()
  })

  it.each([
    ['ab', 'a long passphrase', '用户名需要'],
    ['中文用户', 'a long passphrase', '用户名需要'],
    ['a'.repeat(33), 'a long passphrase', '用户名需要'],
    ['writer', 'short', '密码长度需要'],
    ['writer', 'a'.repeat(129), '密码长度需要']
  ])('validates registration input for %s', async (username, password, error) => {
    const { wrapper } = await open()
    await fillForm(wrapper, username, password)
    await wrapper.find('form').trigger('submit')
    expect(wrapper.get('[role="alert"]').text()).toContain(error)
    expect(register).not.toHaveBeenCalled()
  })

  it('counts password Unicode characters rather than UTF-16 code units', async () => {
    const { wrapper } = await open()
    await fillForm(wrapper, 'writer', '🔐'.repeat(6))
    await wrapper.find('form').trigger('submit')
    expect(wrapper.get('[role="alert"]').text()).toContain('密码长度需要')
    expect(register).not.toHaveBeenCalled()
  })

  it('links registration and login while preserving the destination and clearing password fields', async () => {
    const { wrapper, router } = await open('/register?next=%2Fhistory')
    await fillForm(wrapper)
    expect(wrapper.get('.account-link a').attributes('href')).toBe('/login?next=/history')
    await wrapper.get('.account-link a').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('login')
    expect(wrapper.findAll('input')).toHaveLength(2)
    expect((wrapper.findAll('input')[1].element as HTMLInputElement).value).toBe('')
    expect(wrapper.get('.account-link a').attributes('href')).toBe('/register?next=/history')
  })

  it('logs in without sending a confirmation field', async () => {
    const { wrapper } = await open('/login')
    expect(wrapper.text()).toContain('欢迎回来')
    await fillForm(wrapper)
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(login).toHaveBeenCalledWith('writer', 'a long passphrase')
    expect(register).not.toHaveBeenCalled()
    expect(navigate).toHaveBeenCalledWith('/')
  })

  it.each(['//external.test', '/\\external.test', 'https://external.test', '/login', '/register', '/missing', '/\n/external.test'])(
    'discards an unsafe or non-workspace destination %s', async next => {
      const { wrapper } = await open(`/login?next=${encodeURIComponent(next)}`)
      await fillForm(wrapper)
      await wrapper.find('form').trigger('submit')
      await flushPromises()
      expect(navigate).toHaveBeenCalledWith('/')
    }
  )

  it.each([
    [401, '用户名或密码不正确'], [409, '该用户名已被使用'],
    [422, '请检查用户名格式及密码长度'], [429, '操作过于频繁']
  ])('shows a readable %s error', async (status, message) => {
    vi.mocked(register).mockRejectedValue(new ApiError('technical details', Number(status)))
    const { wrapper } = await open()
    await fillForm(wrapper)
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain(message)
    expect(navigate).not.toHaveBeenCalled()
  })

  it('redirects an already authenticated user based only on server status', async () => {
    vi.mocked(getAuthStatus).mockResolvedValue({ authenticated: true, user: account.user })
    const { router } = await open('/login?next=%2Fhistory')
    expect(router.currentRoute.value.path).toBe('/history')
    expect(login).not.toHaveBeenCalled()
  })
})
