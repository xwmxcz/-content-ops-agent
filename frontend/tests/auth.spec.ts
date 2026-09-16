import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, clearAuthToken, getAuthToken, setAuthToken, watchAccountChanges } from '../src/api'
import { getAuthStatus, login, logout, register } from '../src/api/auth'

const tokenKey = 'content_ops_agent_auth_token'
const navigate = vi.fn()
const reload = vi.fn()
const response = {
  access_token: 'new-session', token_type: 'bearer', expires_at: 2_000_000_000,
  user: { id: 'user-id', username: 'writer' }
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  localStorage.setItem('unrelated-preference', 'keep')
  sessionStorage.setItem('unrelated-session', 'keep')
  sessionStorage.setItem('chat:activeThreadId', 'previous-account-thread')
  const location = { ...window.location, assign: navigate, replace: navigate, reload }
  vi.stubGlobal('window', new Proxy(window, {
    get: (target, key) => key === 'location' ? location : Reflect.get(target, key, target)
  }))
})

afterEach(() => vi.unstubAllGlobals())

describe('account API contracts', () => {
  it.each([['login', login], ['register', register]] as const)('%s stores only the new bearer and discards the prior account thread', async (path, action) => {
    const post = vi.spyOn(api, 'post').mockResolvedValue({ data: response })
    expect(await action('writer', '  a long passphrase  ')).toEqual(response)
    expect(post).toHaveBeenCalledWith(`/auth/${path}`, { username: 'writer', password: '  a long passphrase  ' })
    expect(getAuthToken()).toBe('new-session')
    expect(sessionStorage.getItem('chat:activeThreadId')).toBeNull()
    expect(localStorage.length).toBe(2)
    expect(localStorage.getItem('unrelated-preference')).toBe('keep')
    expect(sessionStorage.getItem('unrelated-session')).toBe('keep')
  })

  it('reads authenticated identity from status without persisting another user cache', async () => {
    const status = { authenticated: true, user: response.user }
    const get = vi.spyOn(api, 'get').mockResolvedValue({ data: status })
    expect(await getAuthStatus()).toEqual(status)
    expect(get).toHaveBeenCalledWith('/auth/status')
    expect(localStorage.length).toBe(1)
  })

  it('revokes the server session before removing local credentials and navigating away', async () => {
    localStorage.setItem(tokenKey, 'old-session')
    const post = vi.spyOn(api, 'post').mockImplementation(async () => {
      expect(getAuthToken()).toBe('old-session')
      return { status: 204 }
    })
    await logout()
    expect(post).toHaveBeenCalledWith('/auth/logout')
    expect(getAuthToken()).toBeNull()
    expect(sessionStorage.getItem('chat:activeThreadId')).toBeNull()
    expect(navigate).toHaveBeenCalledWith('/login')
  })

  it('clears local account state even when server logout fails', async () => {
    localStorage.setItem(tokenKey, 'old-session')
    vi.spyOn(api, 'post').mockRejectedValue(new Error('offline'))
    await expect(logout()).rejects.toThrow('offline')
    expect(getAuthToken()).toBeNull()
    expect(sessionStorage.getItem('chat:activeThreadId')).toBeNull()
    expect(navigate).toHaveBeenCalledWith('/login')
  })

  it('does not retain a previous account active thread when the token is cleared', () => {
    setAuthToken('old-session')
    sessionStorage.setItem('chat:activeThreadId', 'old-thread')
    clearAuthToken()
    expect(sessionStorage.getItem('chat:activeThreadId')).toBeNull()
    expect(localStorage.getItem('unrelated-preference')).toBe('keep')
  })

  it('discards in-memory workspace state when another tab changes the account', () => {
    const listener = vi.spyOn(window, 'addEventListener').mockImplementation(() => {})
    watchAccountChanges()
    const callback = listener.mock.calls[0][1] as (event: StorageEvent) => void
    callback(new StorageEvent('storage', {
      key: tokenKey, oldValue: 'account-a', newValue: 'account-b', storageArea: localStorage
    }))
    expect(sessionStorage.getItem('chat:activeThreadId')).toBeNull()
    expect(navigate).toHaveBeenCalledWith('/login')
  })

  it('ignores unrelated cross-tab storage changes', () => {
    const listener = vi.spyOn(window, 'addEventListener').mockImplementation(() => {})
    watchAccountChanges()
    const callback = listener.mock.calls[0][1] as (event: StorageEvent) => void
    callback(new StorageEvent('storage', {
      key: 'unrelated-preference', oldValue: 'a', newValue: 'b', storageArea: localStorage
    }))
    expect(sessionStorage.getItem('chat:activeThreadId')).toBe('previous-account-thread')
    expect(navigate).not.toHaveBeenCalled()
  })

  it('rechecks authentication with a full reload when BFCache restores a prior workspace', () => {
    const listener = vi.spyOn(window, 'addEventListener').mockImplementation(() => {})
    watchAccountChanges()
    const callback = listener.mock.calls.find(([type]) => type === 'pageshow')?.[1] as (event: PageTransitionEvent) => void
    expect(callback).toBeTypeOf('function')
    callback(new PageTransitionEvent('pageshow', { persisted: true }))
    expect(reload).toHaveBeenCalledOnce()
    expect(localStorage.getItem('unrelated-preference')).toBe('keep')
    expect(sessionStorage.getItem('unrelated-session')).toBe('keep')
  })

  it('does not reload on a normal pageshow event', () => {
    const listener = vi.spyOn(window, 'addEventListener').mockImplementation(() => {})
    watchAccountChanges()
    const callback = listener.mock.calls.find(([type]) => type === 'pageshow')?.[1] as (event: PageTransitionEvent) => void
    expect(callback).toBeTypeOf('function')
    callback(new PageTransitionEvent('pageshow', { persisted: false }))
    expect(reload).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
  })
})
