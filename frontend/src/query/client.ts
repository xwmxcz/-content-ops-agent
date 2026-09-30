import { CancelledError, QueryClient, type QueryKey } from '@tanstack/vue-query'
import { isCancel } from 'axios'
import { onWorkspaceSessionReset, workspaceSessionId } from '../workspaceSession'

const clients = new Set<QueryClient>()

export function retryRead(failureCount: number, error: unknown) {
  if (isCancel(error) || error instanceof CancelledError) return false
  const status = (error as { status?: number })?.status
  return failureCount < 2 && (!status || status === 408 || status === 429 || status >= 500)
}

export function createWorkspaceQueryClient(retry: false | typeof retryRead = retryRead) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { staleTime: 30_000, gcTime: 5 * 60_000, retry, retryDelay: attempt => Math.min(1000 * 2 ** attempt, 5000) },
      mutations: { retry: false }
    }
  })
  clients.add(client)
  return client
}

export function disposeWorkspaceQueryClient(client: QueryClient) {
  clients.delete(client)
  void client.cancelQueries()
  client.clear()
}

export const queryClient = createWorkspaceQueryClient()

onWorkspaceSessionReset(() => {
  // cancelQueries aborts transports synchronously; clear removes both queries and mutations.
  clients.forEach(client => { void client.cancelQueries(); client.clear() })
})

export const workspaceKeys = {
  root: (session = workspaceSessionId.value) => ['workspace', session] as const,
  lists: (session = workspaceSessionId.value) => ['workspace', session, 'contents'] as const,
  content: (id: number, session = workspaceSessionId.value) => ['workspace', session, 'content', id] as const,
  media: (id: number, session = workspaceSessionId.value) => ['workspace', session, 'media', id] as const,
  publications: (id: number, session = workspaceSessionId.value) => ['workspace', session, 'publications', id] as const,
  metrics: (id: number, session = workspaceSessionId.value) => ['workspace', session, 'metrics', id] as const,
  counts: (session = workspaceSessionId.value) => ['workspace', session, 'stats', 'counts'] as const,
  performance: (session = workspaceSessionId.value) => ['workspace', session, 'stats', 'performance'] as const
}

export function assertWorkspaceSession(session: string, signal?: AbortSignal) {
  if (session !== workspaceSessionId.value || signal?.aborted) throw new CancelledError({ silent: true })
}

export async function readWorkspace<T>(session: string, signal: AbortSignal, read: () => Promise<T>) {
  assertWorkspaceSession(session, signal)
  const result = await read()
  // Also defend against a transport/mock that ignores the AbortSignal.
  assertWorkspaceSession(session, signal)
  return result
}

function invalidate(session: string, keys: QueryKey[]) {
  if (session !== workspaceSessionId.value) return
  clients.forEach(client => keys.forEach(queryKey => {
    // A first read has no data yet: invalidateQueries alone reuses its old in-flight
    // snapshot. Abort it first so a successful write always starts a fresh read.
    void client.cancelQueries({ queryKey }).then(() => {
      if (session === workspaceSessionId.value && clients.has(client)) void client.invalidateQueries({ queryKey })
    })
  }))
}

export function contentChanged(session: string, id?: number) {
  invalidate(session, [workspaceKeys.lists(session), workspaceKeys.counts(session), workspaceKeys.performance(session), ...(id == null ? [] : [workspaceKeys.content(id, session)])])
}

export function contentDeleted(session: string, id: number) {
  if (session !== workspaceSessionId.value) return
  clients.forEach(client => {
    for (const key of [workspaceKeys.content(id, session), workspaceKeys.media(id, session), workspaceKeys.publications(id, session), workspaceKeys.metrics(id, session)]) {
      void client.cancelQueries({ queryKey: key })
      client.removeQueries({ queryKey: key })
    }
  })
  contentChanged(session)
}

export function mediaChanged(session: string, id: number) {
  invalidate(session, [workspaceKeys.media(id, session)])
}

export function publicationChanged(session: string, id: number) {
  invalidate(session, [workspaceKeys.publications(id, session)])
  contentChanged(session, id)
}

export function metricsChanged(session: string, ids: number[]) {
  invalidate(session, [workspaceKeys.performance(session), ...[...new Set(ids)].map(id => workspaceKeys.metrics(id, session))])
}
