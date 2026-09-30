import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { CancelledError, QueryObserver, type QueryClient } from '@tanstack/vue-query'
import axios, { type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { api, clearAuthToken, getAuthToken, setAuthToken, watchAccountChanges, ApiError } from '../src/api'
import { logout } from '../src/api/auth'
import { getContents, archiveContent } from '../src/api/content'
import { recordContentMetrics } from '../src/api/metrics'
import { chatStream } from '../src/api/agent'
import {
  contentChanged, createWorkspaceQueryClient, disposeWorkspaceQueryClient,
  readWorkspace, retryRead, workspaceKeys
} from '../src/query/client'
import { workspaceSessionId, workspaceSessionReady } from '../src/workspaceSession'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}
let client: QueryClient
const tokenKey = 'content_ops_agent_auth_token'
beforeEach(() => {
  localStorage.clear()
  setAuthToken('secret-account-a')
  client = createWorkspaceQueryClient(false)
})
afterEach(() => {
  disposeWorkspaceQueryClient(client)
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('workspace query security and lifecycle', () => {
  it('keeps credentials out of keys, clears all cache on login, and never reuses same-ID data across accounts', () => {
    const old = workspaceKeys.content(1)
    client.setQueryData(old, { title: 'Account A private draft' })
    expect(JSON.stringify(old)).not.toContain('secret-account-a')
    setAuthToken('secret-account-b')
    expect(workspaceKeys.content(1)).not.toEqual(old)
    expect(client.getQueryCache().getAll()).toHaveLength(0)
    expect(client.getQueryData(workspaceKeys.content(1))).toBeUndefined()
    expect(localStorage.length).toBe(1)
  })

  it('aborts pending requests and rejects late results even when the transport ignores cancellation', async () => {
    const old = deferred<string>()
    const key = workspaceKeys.content(1)
    let signal!: AbortSignal
    const pending = client.fetchQuery({ queryKey: key, queryFn: context => {
      signal = context.signal
      return readWorkspace(key[1], signal, () => old.promise)
    } }).catch(error => error)
    setAuthToken('secret-account-b')
    expect(signal.aborted).toBe(true)
    old.resolve('private account A result')
    expect(await pending).toBeInstanceOf(CancelledError)
    await flushPromises()
    expect(client.getQueryCache().getAll()).toHaveLength(0)
  })

  it('passes TanStack cancellation through the content API into the Axios transport', async () => {
    let aborted = false
    const adapter = api.defaults.adapter
    api.defaults.adapter = config => new Promise((_resolve, reject) => {
      config.signal?.addEventListener?.('abort', () => {
        aborted = true
        reject(new axios.CanceledError('aborted', config))
      })
    })
    try {
      const key = workspaceKeys.lists()
      const pending = client.fetchQuery({ queryKey: key, queryFn: ({ signal }) => getContents({}, signal) }).catch(error => error)
      await client.cancelQueries({ queryKey: key })
      expect(aborted).toBe(true)
      expect(await pending).toBeInstanceOf(CancelledError)
    } finally { api.defaults.adapter = adapter }
  })

  it('freezes and clears cache as logout starts, without clearing a newer login when revocation finishes', async () => {
    client.setQueryData(workspaceKeys.counts(), { total_contents: 10 })
    const revoke = deferred<object>()
    vi.spyOn(api, 'post').mockReturnValueOnce(revoke.promise as never)
    const pending = logout()
    expect(workspaceSessionReady.value).toBe(false)
    expect(client.getQueryCache().getAll()).toHaveLength(0)
    setAuthToken('secret-account-b')
    revoke.resolve({})
    await pending
    expect(getAuthToken()).toBe('secret-account-b')
  })

  it.each([tokenKey, null])('clears and disables workspace queries after a cross-tab storage change (%s)', key => {
    const listeners = vi.spyOn(window, 'addEventListener').mockImplementation(() => {})
    const navigate = vi.fn()
    const location = { ...window.location, replace: navigate }
    vi.stubGlobal('window', new Proxy(window, { get: (target, property) => property === 'location' ? location : Reflect.get(target, property, target) }))
    watchAccountChanges()
    client.setQueryData(workspaceKeys.content(1), { title: 'private draft' })
    const callback = listeners.mock.calls.find(call => call[0] === 'storage')![1] as (event: StorageEvent) => void
    callback(new StorageEvent('storage', { key, oldValue: 'a', newValue: 'b', storageArea: localStorage }))
    expect(client.getQueryCache().getAll()).toHaveLength(0)
    expect(workspaceSessionReady.value).toBe(false)
    expect(navigate).toHaveBeenCalledWith('/login')
  })

  it.each([200, 401])('rejects a retired Axios response (%s) without signing out the new account', async status => {
    const response = deferred<AxiosResponse>()
    const adapter = api.defaults.adapter
    let request!: InternalAxiosRequestConfig
    api.defaults.adapter = config => {
      request = config
      return response.promise.then(result => {
        if (status === 401) throw new axios.AxiosError('expired', 'ERR_BAD_REQUEST', config, undefined, result)
        return result
      })
    }
    try {
      const pending = api.get('/content').catch(error => error)
      setAuthToken('secret-account-b')
      response.resolve({ data: { private: true }, status, statusText: '', headers: {}, config: request })
      expect(axios.isCancel(await pending)).toBe(true)
      expect(getAuthToken()).toBe('secret-account-b')
    } finally { api.defaults.adapter = adapter }
  })

  it('does not let a retired stream 401 sign out the newer account', async () => {
    const response = deferred<Response>()
    let signal!: AbortSignal
    vi.stubGlobal('fetch', vi.fn((_url, options) => { signal = options.signal; return response.promise }))
    const pending = chatStream({ message: 'hello', temperature: 0.7, max_tokens: 100 }).catch(error => error)
    setAuthToken('secret-account-b')
    expect(signal.aborted).toBe(true)
    response.resolve(new Response('{}', { status: 401 }))
    expect(await pending).toBeInstanceOf(CancelledError)
    expect(getAuthToken()).toBe('secret-account-b')
  })

  it('rejects old stream callbacks even if a fetch mock ignores abort', async () => {
    let controller!: ReadableStreamDefaultController<Uint8Array>
    const body = new ReadableStream<Uint8Array>({ start(value) { controller = value } })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body)))
    const onToken = vi.fn()
    const pending = chatStream({ message: 'hello', temperature: 0.7, max_tokens: 100 }, { onToken }).catch(error => error)
    await flushPromises()
    setAuthToken('secret-account-b')
    controller.enqueue(new TextEncoder().encode('event: token\ndata: {"delta":"private account A"}\n\n'))
    controller.close()
    expect(await pending).toBeInstanceOf(CancelledError)
    expect(onToken).not.toHaveBeenCalled()
  })
})

describe('precise write invalidation', () => {
  it('invalidates only the edited content, lists and analytics after archiving succeeds', async () => {
    const keys = [workspaceKeys.content(1), workspaceKeys.content(2), workspaceKeys.lists(), workspaceKeys.counts(), workspaceKeys.performance(), workspaceKeys.media(1)]
    keys.forEach(key => client.setQueryData(key, { value: 1 }))
    vi.spyOn(api, 'post').mockResolvedValueOnce({ data: { archived: true } })
    await archiveContent(1)
    await flushPromises()
    expect(keys.map(key => client.getQueryState(key)?.isInvalidated)).toEqual([true, false, true, true, true, false])
  })

  it('invalidates effects and the matching readings after metrics save, preserving inventory counts and other content', async () => {
    const keys = [workspaceKeys.metrics(1), workspaceKeys.metrics(2), workspaceKeys.counts(), workspaceKeys.performance()]
    keys.forEach(key => client.setQueryData(key, { value: 1 }))
    vi.spyOn(api, 'put').mockResolvedValueOnce({ data: { id: 1 } })
    await recordContentMetrics(1, { platform: 'blog', views: 0, likes: 0, shares: 0, comments: 0 })
    await flushPromises()
    expect(keys.map(key => client.getQueryState(key)?.isInvalidated)).toEqual([true, false, false, true])
  })

  it('does not invalidate a new account cache when an old mutation finishes', async () => {
    const write = deferred<unknown>()
    vi.spyOn(api, 'post').mockReturnValueOnce(write.promise as never)
    const pending = archiveContent(1)
    setAuthToken('secret-account-b')
    client.setQueryData(workspaceKeys.content(1), { title: 'account B' })
    write.resolve({ data: { archived: true } })
    await pending
    await flushPromises()
    expect(client.getQueryState(workspaceKeys.content(1))?.isInvalidated).toBe(false)
    expect(client.getQueryCache().getAll()).toHaveLength(1)
  })

  it('restarts an initial pending read after a write instead of marking an older snapshot fresh', async () => {
    const old = deferred<number>()
    const key = workspaceKeys.counts()
    let oldSignal!: AbortSignal
    const read = vi.fn().mockImplementationOnce(({ signal }) => { oldSignal = signal; return old.promise }).mockResolvedValue(2)
    const observer = new QueryObserver(client, { queryKey: key, queryFn: read })
    const unsubscribe = observer.subscribe(() => {})
    contentChanged(workspaceSessionId.value, 1)
    await flushPromises()
    expect(oldSignal.aborted).toBe(true)
    expect(read).toHaveBeenCalledTimes(2)
    old.resolve(1)
    await flushPromises()
    expect(client.getQueryData(key)).toBe(2)
    unsubscribe()
  })

  it('bounds transient retries and never retries permission, validation or cancellation failures', () => {
    expect(retryRead(0, new ApiError('offline'))).toBe(true)
    expect(retryRead(1, new ApiError('unavailable', 503))).toBe(true)
    expect(retryRead(2, new ApiError('unavailable', 503))).toBe(false)
    for (const status of [400, 401, 403, 404, 409, 422]) expect(retryRead(0, new ApiError('rejected', status))).toBe(false)
    expect(retryRead(0, new axios.CanceledError())).toBe(false)
    expect(retryRead(0, new CancelledError())).toBe(false)
    expect(client.getDefaultOptions().mutations?.retry).toBe(false)
    clearAuthToken()
  })
})
