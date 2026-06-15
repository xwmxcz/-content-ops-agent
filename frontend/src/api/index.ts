import axios from 'axios'

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
  window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token)
}

export function clearAuthToken() {
  window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY)
}

export function withAuthQuery(url: string) {
  const token = getAuthToken()
  if (!token) return url

  const parsed = new URL(url, window.location.origin)
  parsed.searchParams.set('access_token', token)
  return parsed.origin === window.location.origin
    ? `${parsed.pathname}${parsed.search}${parsed.hash}`
    : parsed.toString()
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
    if (status === 401 && !requestUrl.includes('/auth/login') && !requestUrl.includes('/auth/status')) {
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
