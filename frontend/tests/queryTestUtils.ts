import { VueQueryPlugin, type QueryClient } from '@tanstack/vue-query'
import { createWorkspaceQueryClient, disposeWorkspaceQueryClient } from '../src/query/client'
import { activateWorkspaceSession, clearWorkspaceSession } from '../src/workspaceSession'

const clients: QueryClient[] = []
export function queryTestPlugin() {
  clearWorkspaceSession()
  activateWorkspaceSession()
  const queryClient = createWorkspaceQueryClient(false)
  clients.push(queryClient)
  return [VueQueryPlugin, { queryClient }] as const
}
export function disposeQueryTests() {
  clients.splice(0).forEach(disposeWorkspaceQueryClient)
}
