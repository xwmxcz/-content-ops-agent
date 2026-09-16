// Owns account-scoped browser persistence; clear it whenever the authenticated account changes.
const ACTIVE_THREAD_STORAGE_KEY = 'chat:activeThreadId'

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
  writeActiveThreadToStorage(undefined)
}
