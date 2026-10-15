// The opaque, memory-only identity scopes caches without placing bearer tokens in query keys.
import { readonly, ref } from 'vue'

function newSessionId() {
  // getRandomValues also works on self-hosted HTTP origins where randomUUID is unavailable.
  return crypto.randomUUID?.() ?? Array.from(crypto.getRandomValues(new Uint32Array(4)), value => value.toString(16)).join('-')
}

const sessionId = ref<string>(newSessionId())
const sessionReady = ref(false)
const resetListeners = new Set<() => void>()
export const workspaceSessionId = readonly(sessionId)
export const workspaceSessionReady = readonly(sessionReady)

export function activateWorkspaceSession() {
  sessionReady.value = true
}

export function onWorkspaceSessionReset(listener: () => void) {
  resetListeners.add(listener)
  return () => { resetListeners.delete(listener) }
}

const ACTIVE_THREAD_STORAGE_KEY = 'chat:activeThreadId'
export const ACTIVE_STUDIO_SESSION_KEY = 'studio:activeSession'

export function readActiveThreadFromStorage(): string | undefined {
  try {
    return sessionStorage.getItem(ACTIVE_THREAD_STORAGE_KEY) || undefined
  } catch {
    return undefined
  }
}

export function writeActiveThreadToStorage(threadId: string | undefined) {
  try {
    if (threadId) sessionStorage.setItem(ACTIVE_THREAD_STORAGE_KEY, threadId)
    else sessionStorage.removeItem(ACTIVE_THREAD_STORAGE_KEY)
  } catch {
    // Browser storage may be disabled; the workspace still works without persistence.
  }
}

export function clearWorkspaceSession() {
  sessionReady.value = false
  sessionId.value = newSessionId()
  resetListeners.forEach(listener => listener())
  writeActiveThreadToStorage(undefined)
  try {
    sessionStorage.removeItem(ACTIVE_STUDIO_SESSION_KEY)
  } catch {
    // Ignore storage errors when disabled.
  }
}
