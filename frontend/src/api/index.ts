// Owns API transport and bearer storage; account changes and BFCache restores discard stale workspace state.
import axios from 'axios'
import { clearWorkspaceSession } from '../workspaceSession'

const AUTH_TOKEN_STORAGE_KEY = 'content_ops_agent_auth_token'

export class ApiError extends Error {
  status?: number
  detail: unknown

  constructor(message: string, status?: number, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export const api = axios.create({
  baseURL: '/api',
  timeout: 120000
})

export function getAuthToken() {
  return window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)
}

export function setAuthToken(token: string) {
  clearWorkspaceSession()
  window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token)
}

export function clearAuthToken() {
  clearWorkspaceSession()
  window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY)
}

export function watchAccountChanges() {
  window.addEventListener('storage', event => {
    if (event.storageArea === window.localStorage && event.key === AUTH_TOKEN_STORAGE_KEY && event.oldValue !== event.newValue) {
      clearWorkspaceSession()
      // A full navigation also disposes in-memory content, chat, and running task state.
      window.location.replace('/login')
    }
  })
  window.addEventListener('pageshow', event => {
    // BFCache restores Vue memory without mounting again; re-run routing and server authentication.
    if (event.persisted) window.location.reload()
  })
}

api.interceptors.request.use(config => {
  const token = getAuthToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  response => response,
  error => {
    const detail = error.response?.data?.detail
    const status = error.response?.status
    const requestUrl = error.config?.url ?? ''
    if (status === 401 && !requestUrl.startsWith('/auth/')) {
      clearAuthToken()
      const next = `${window.location.pathname}${window.location.search}`
      if (!window.location.pathname.startsWith('/login')) {
        window.location.assign(`/login?next=${encodeURIComponent(next)}`)
      }
    }
    const message = typeof detail === 'string' ? detail : detail?.message ?? fallbackApiMessage(status, error.message)
    return Promise.reject(new ApiError(message, error.response?.status, detail))
  }
)

function fallbackApiMessage(status?: number, rawMessage = '请求失败') {
  if (status === 400) return '请求参数有误'
  if (status === 401) return '未授权，请重新登录'
  if (status === 403) return '没有权限执行该操作'
  if (status === 404) return '请求的资源不存在'
  if (status === 429) return '请求过于频繁，请稍后再试'
  if (status === 500) return '服务器内部错误，请查看后端日志'
  if (status === 502) return '上游模型或服务调用失败'
  if (status === 503) return '服务暂时不可用，请稍后再试'
  if (status) return `请求失败，状态码 ${status}`
  return rawMessage === 'Network Error' ? '网络连接失败，请确认后端服务已启动' : rawMessage
}
