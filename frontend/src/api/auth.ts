import { api, clearAuthToken, getAuthToken, setAuthToken } from './index'

export interface AuthStatus {
  enabled: boolean
  configured: boolean
  authenticated: boolean
  username?: string | null
}

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_at?: number | null
  username: string
  enabled: boolean
}

export async function getAuthStatus() {
  const { data } = await api.get<AuthStatus>('/auth/status')
  return data
}

export async function login(username: string, password: string) {
  const { data } = await api.post<LoginResponse>('/auth/login', { username, password })
  if (data.access_token) {
    setAuthToken(data.access_token)
  }
  return data
}

export function logout() {
  clearAuthToken()
  window.location.assign('/login')
}

export function hasAuthToken() {
  return Boolean(getAuthToken())
}
