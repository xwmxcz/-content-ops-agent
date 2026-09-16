import { beforeEach, describe, expect, it, vi } from 'vitest'
import router from '../src/router'
import { getAuthStatus } from '../src/api/auth'

vi.mock('../src/api/auth', () => ({ getAuthStatus: vi.fn() }))
vi.mock('../src/views/History.vue', () => ({ default: { template: '<div>History</div>' } }))
vi.mock('../src/views/Login.vue', () => ({ default: { template: '<div>Account</div>' } }))

beforeEach(() => vi.spyOn(window, 'scrollTo').mockImplementation(() => {}))

describe('workspace navigation scroll', () => {
  const to = router.resolve('/history')
  const from = router.resolve('/calendar')

  it('starts a newly opened page at its heading', () => {
    expect(router.options.scrollBehavior!(to, from, null)).toEqual({ top: 0, left: 0 })
  })

  it('preserves the reading position during back and forward navigation', () => {
    const saved = { top: 360, left: 0 }
    expect(router.options.scrollBehavior!(to, from, saved)).toEqual(saved)
  })
})

describe('workspace account gating', () => {
  it('keeps registration public', async () => {
    await router.push('/register')
    expect(router.currentRoute.value.name).toBe('register')
    expect(router.currentRoute.value.meta.public).toBe(true)
    expect(getAuthStatus).not.toHaveBeenCalled()
  })

  it('redirects anonymous users to login and preserves the requested workspace path', async () => {
    vi.mocked(getAuthStatus).mockResolvedValue({ authenticated: false, user: null })
    await router.push('/history?view=draft')
    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.next).toBe('/history?view=draft')
  })

  it('accepts the authenticated status contract without old enabled/configured fields', async () => {
    vi.mocked(getAuthStatus).mockResolvedValue({ authenticated: true, user: { id: 'user-id', username: 'writer' } })
    await router.push('/history')
    expect(router.currentRoute.value.path).toBe('/history')
  })

  it('requires authentication even if a stale disabled flag appears in the response', async () => {
    const staleStatus = { authenticated: false, user: null, enabled: false }
    vi.mocked(getAuthStatus).mockResolvedValue(staleStatus)
    await router.push('/calendar')
    expect(router.currentRoute.value.path).toBe('/login')
  })
})
