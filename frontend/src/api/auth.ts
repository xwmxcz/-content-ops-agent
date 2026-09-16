// Owns account API contracts; identity always comes from the server, not browser storage.
import { api, clearAuthToken, setAuthToken } from './index'

export interface AuthUser {
  id: string
  username: string
}

export interface AuthStatus {
  authenticated: boolean
  user: AuthUser | null
}

export interface AuthResponse {
  access_token: string
  token_type: 'bearer'
  expires_at: number
  user: AuthUser
}

export async function getAuthStatus() {
  const { data } = await api.get<AuthStatus>('/auth/status')
  return data
}

export async function login(username: string, password: string) {
  const { data } = await api.post<AuthResponse>('/auth/login', { username, password })
  setAuthToken(data.access_token)
  return data
}

export async function register(username: string, password: string) {
  const { data } = await api.post<AuthResponse>('/auth/register', { username, password })
  setAuthToken(data.access_token)
  return data
}

export async function logout() {
  try {
    await api.post('/auth/logout')
  } finally {
    clearAuthToken()
    window.location.assign('/login')
  }
}
