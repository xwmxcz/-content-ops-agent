// Owns account API contracts; identity always comes from the server, not browser storage.
import { api, clearAuthToken, setAuthToken } from './index'
import { activateWorkspaceSession, clearWorkspaceSession, workspaceSessionId } from '../workspaceSession'

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
  const session = workspaceSessionId.value
  const { data } = await api.get<AuthStatus>('/auth/status')
  if (session === workspaceSessionId.value) {
    if (data.authenticated) activateWorkspaceSession()
    else clearWorkspaceSession()
  }
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
  // Stop account reads immediately, even if server-side token revocation is slow.
  clearWorkspaceSession()
  const session = workspaceSessionId.value
  try {
    await api.post('/auth/logout')
  } finally {
    if (session === workspaceSessionId.value) {
      clearAuthToken()
      window.location.assign('/login')
    }
  }
}
