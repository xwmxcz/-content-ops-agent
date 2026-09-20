/**
 * The fetch-based chat stream client and its SSE framing.
 *
 * EventSource cannot POST or send an Authorization header, so the framing it
 * would do for free is done by hand here, and network chunks do not respect
 * frame, line, or even character boundaries.
 *
 * The other thing pinned is which failures may fall back to the plain endpoint.
 * Re-sending is only safe when the server provably never started the turn;
 * after that, a resend is a second, duplicate message.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { chatStream, ChatStreamInterruptedError, ChatStreamUnavailableError } from '../src/api/agent'
import { ApiError } from '../src/api'
import { readSseStream, type SseFrame } from '../src/api/sse'

const encoder = new TextEncoder()

function streamOf(chunks: Array<string | Uint8Array>, options: { failAfter?: boolean } = {}) {
  const pending = [...chunks]
  return new ReadableStream<Uint8Array>({
    // One chunk per pull: erroring a stream discards whatever is still queued, and
    // a real connection drops after the earlier chunks were already read.
    pull(controller) {
      const chunk = pending.shift()
      if (chunk !== undefined) controller.enqueue(typeof chunk === 'string' ? encoder.encode(chunk) : chunk)
      else if (options.failAfter) controller.error(new TypeError('network error'))
      else controller.close()
    }
  })
}

async function frames(chunks: Array<string | Uint8Array>) {
  const out: SseFrame[] = []
  await readSseStream(streamOf(chunks), frame => out.push(frame))
  return out
}

function frame(event: string, data: unknown) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

describe('readSseStream', () => {
  it('reassembles frames split at arbitrary points, including inside the terminator', async () => {
    const wire = frame('token', { delta: 'a' }) + frame('token', { delta: 'b' })
    const pieces = [wire.slice(0, 9), wire.slice(9, wire.indexOf('\n\n') + 1), wire.slice(wire.indexOf('\n\n') + 1)]

    expect(await frames(pieces)).toEqual([
      { event: 'token', data: '{"delta":"a"}' },
      { event: 'token', data: '{"delta":"b"}' }
    ])
  })

  it('does not corrupt a multi-byte character cut in half by a chunk boundary', async () => {
    const bytes = encoder.encode(frame('token', { delta: '流式' }))
    const cut = bytes.indexOf(0xe6) + 1 // inside the first Chinese character

    const [only] = await frames([bytes.slice(0, cut), bytes.slice(cut)])

    expect(JSON.parse(only.data)).toEqual({ delta: '流式' })
  })

  it('ignores keepalive comments and accepts CRLF line endings', async () => {
    const wire = ': keepalive\n\n' + 'event: done\r\ndata: {"ok":true}\r\n\r\n'

    expect(await frames([wire])).toEqual([{ event: 'done', data: '{"ok":true}' }])
  })

  it('joins multi-line data and defaults the event name', async () => {
    expect(await frames(['data: one\ndata: two\n\n'])).toEqual([{ event: 'message', data: 'one\ntwo' }])
  })

  it('delivers a final frame that was not terminated before the stream closed', async () => {
    expect(await frames(['event: done\ndata: {}'])).toEqual([{ event: 'done', data: '{}' }])
  })
})

describe('chatStream', () => {
  const payload = { message: 'hello', temperature: 0.7, max_tokens: 100 }
  const done = { message_id: 7, thread_id: 't1', response: 'Hi there', provider: 'p', model: 'm', tool_events: [], plan: [] }
  let fetchMock: ReturnType<typeof vi.fn>

  function respond(body: BodyInit | null, init: ResponseInit = { status: 200 }) {
    fetchMock.mockResolvedValue(new Response(body, init))
  }

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    window.localStorage.setItem('content_ops_agent_auth_token', 'token-123')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
  })

  it('posts with the bearer token and resolves with the server response', async () => {
    respond(streamOf([frame('turn_start', { thread_id: 't1', provider: 'p', model: 'm' }), frame('done', done)]))

    await expect(chatStream(payload)).resolves.toEqual(done)

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/agent/chat/stream')
    expect(init.method).toBe('POST')
    expect(init.headers.Authorization).toBe('Bearer token-123')
    expect(JSON.parse(init.body)).toEqual(payload)
  })

  it('reports progress in order through the handlers', async () => {
    const tool = { name: 'search_history', args: {}, output: 'ok', status: 'completed' }
    respond(
      streamOf([
        frame('turn_start', { thread_id: 't1', provider: 'p', model: 'm' }),
        frame('intent', { intent: { name: 'content_search' } }),
        frame('plan', { plan: [{ index: 1, description: 'look', status: 'pending' }] }),
        frame('token', { delta: 'thinking' }),
        frame('draft_reset', {}),
        frame('tool_start', { name: 'search_history', args: {}, attempt: 1 }),
        frame('tool_end', { event: tool }),
        frame('token', { delta: 'Hi there' }),
        frame('done', done)
      ])
    )
    const calls: string[] = []

    await chatStream(payload, {
      onTurnStart: info => calls.push(`start:${info.thread_id}`),
      onIntent: intent => calls.push(`intent:${intent.name}`),
      onPlan: plan => calls.push(`plan:${plan.length}`),
      onToken: delta => calls.push(`token:${delta}`),
      onDraftReset: () => calls.push('reset'),
      onToolStart: call => calls.push(`tool_start:${call.name}`),
      onToolEnd: event => calls.push(`tool_end:${event.status}`)
    })

    expect(calls).toEqual([
      'start:t1',
      'intent:content_search',
      'plan:1',
      'token:thinking',
      'reset',
      'tool_start:search_history',
      'tool_end:completed',
      'token:Hi there'
    ])
  })

  it('turns an error event into an ApiError carrying the status', async () => {
    respond(streamOf([frame('turn_start', { thread_id: 't1' }), frame('error', { status: 502, detail: 'Agent execution failed' })]))

    const error = await chatStream(payload).catch(caught => caught)

    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(502)
    expect(error.message).toBe('Agent execution failed')
  })

  it.each([404, 405])('treats HTTP %i as "no turn was started", which allows a fallback', async status => {
    respond(JSON.stringify({ detail: 'Not Found' }), { status })

    await expect(chatStream(payload)).rejects.toBeInstanceOf(ChatStreamUnavailableError)
  })

  it('surfaces a rejected request as an ordinary API error, not as a fallback', async () => {
    respond(JSON.stringify({ detail: 'Rate limit exceeded' }), { status: 429, headers: { 'Content-Type': 'application/json' } })

    const error = await chatStream(payload).catch(caught => caught)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).not.toBeInstanceOf(ChatStreamUnavailableError)
    expect(error.message).toBe('Rate limit exceeded')
  })

  it('never offers a fallback for a network failure, whose request may have been received', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    const error = await chatStream(payload).catch(caught => caught)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).not.toBeInstanceOf(ChatStreamUnavailableError)
  })

  it('reports a connection lost mid-reply as interrupted, with the thread to reload', async () => {
    respond(streamOf([frame('turn_start', { thread_id: 't9' }), frame('token', { delta: 'Half' })], { failAfter: true }))

    const error = await chatStream(payload).catch(caught => caught)

    expect(error).toBeInstanceOf(ChatStreamInterruptedError)
    expect(error.threadId).toBe('t9')
  })

  it('does not leak a raw network error when the connection drops before the turn is announced', async () => {
    respond(streamOf([], { failAfter: true }))

    const error = await chatStream(payload).catch(caught => caught)

    expect(error).toBeInstanceOf(ApiError)
    // The request was sent, so this must not invite an automatic resend either.
    expect(error).not.toBeInstanceOf(ChatStreamUnavailableError)
  })

  it('reports a body that ends without a verdict as interrupted too', async () => {
    respond(streamOf([frame('turn_start', { thread_id: 't9' }), frame('token', { delta: 'Half' })]))

    await expect(chatStream(payload)).rejects.toBeInstanceOf(ChatStreamInterruptedError)
  })
})
