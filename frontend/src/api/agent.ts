import { api } from './index'

export async function chat(message: string, threadId = 'default') {
  const { data } = await api.post<{ thread_id: string; response: string }>('/agent/chat', {
    message,
    thread_id: threadId
  })
  return data
}
