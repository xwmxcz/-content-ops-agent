import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FakeEventSource, installFakeEventSource } from './support/fakeEventSource'
import {
  usePipelineStream,
  type PipelineStreamHandlers,
  type StreamStatus
} from '../src/composables/usePipelineStream'

function makeHandlers(overrides: Partial<PipelineStreamHandlers> = {}) {
  const states: StreamStatus[] = []
  const handlers: PipelineStreamHandlers = {
    onPlanReady: vi.fn(),
    onStepStart: vi.fn(),
    onStepToken: vi.fn(),
    onToolCallStart: vi.fn(),
    onToolCallResult: vi.fn(),
    onStepComplete: vi.fn(),
    onStepFailed: vi.fn(),
    onPlanRevised: vi.fn(),
    onRunComplete: vi.fn(),
    onRunFailed: vi.fn(),
    onRunCancelled: vi.fn(),
    onConnectionLost: vi.fn(),
    onStateChange: (status: StreamStatus) => states.push(status),
    ...overrides
  }
  return { handlers, states }
}

describe('usePipelineStream', () => {
  beforeEach(() => {
    installFakeEventSource()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    FakeEventSource.reset()
  })

  describe('subscription and event dispatch', () => {
    it('refreshes liveness for pings that inherit the preceding run event id', async () => {
      const { handlers, states } = makeHandlers()
      const stream = usePipelineStream(handlers, { staleAfterMs: 1000 })
      await stream.subscribe('run-1')
      FakeEventSource.last.emit('step_token', { index: 1, delta: 'a' }, 7)
      for (let i = 0; i < 4; i++) {
        vi.advanceTimersByTime(750)
        FakeEventSource.last.emit('ping', {})
      }
      expect(states.map(s => s.state)).not.toContain('stale')
      expect(stream.getStatus()).toMatchObject({ state: 'open', lastSeq: 7 })
      expect(handlers.onStepToken).toHaveBeenCalledTimes(1)
      stream.close()
    })

    it('recovers from stale on a ping without changing the replay cursor', async () => {
      const { handlers } = makeHandlers()
      const stream = usePipelineStream(handlers, { staleAfterMs: 1000 })
      await stream.subscribe('run-1')
      FakeEventSource.last.emit('step_token', { index: 1, delta: 'a' }, 7)
      vi.advanceTimersByTime(1000)
      expect(stream.getStatus().state).toBe('stale')
      FakeEventSource.last.emit('ping', {})
      expect(stream.getStatus()).toMatchObject({ state: 'open', lastSeq: 7 })
      stream.close()
    })

    it('opens without a resume cursor on a fresh subscription', async () => {
      const { handlers } = makeHandlers()
      const stream = usePipelineStream(handlers)

      await stream.subscribe('run-1')

      expect(FakeEventSource.openCount).toBe(1)
      expect(FakeEventSource.last.url).toContain('/agent/runs/run-1/stream')
      expect(FakeEventSource.last.afterSeqParam).toBeNull()
      expect(FakeEventSource.last.withCredentials).toBe(true)
    })

    it('routes each run event to its handler', async () => {
      const { handlers } = makeHandlers()
      const stream = usePipelineStream(handlers)
      await stream.subscribe('run-1')
      const source = FakeEventSource.last

      source.emit('plan_ready', { plan: [{ index: 1 }] }, 1)
      source.emit('step_start', { index: 1 }, 2)
      source.emit('step_token', { index: 1, delta: 'ab' }, 3)
      source.emit('step_complete', { index: 1, output: 'done', prompt_tokens: 5 }, 4)

      expect(handlers.onPlanReady).toHaveBeenCalledWith([{ index: 1 }])
      expect(handlers.onStepStart).toHaveBeenCalledWith(1)
      expect(handlers.onStepToken).toHaveBeenCalledWith(1, 'ab')
      expect(handlers.onStepComplete).toHaveBeenCalledWith(
        expect.objectContaining({ index: 1, output: 'done' })
      )
    })

    it('reports open state once the first frame arrives', async () => {
      const { handlers, states } = makeHandlers()
      const stream = usePipelineStream(handlers)
      await stream.subscribe('run-1')

      expect(states.map(s => s.state)).toEqual(['connecting'])
      FakeEventSource.last.emit('hello', {})

      expect(states.map(s => s.state)).toEqual(['connecting', 'open'])
    })

    it('survives a malformed frame instead of dropping the subscription', async () => {
      const { handlers } = makeHandlers()
      const stream = usePipelineStream(handlers)
      await stream.subscribe('run-1')
      const source = FakeEventSource.last

      expect(() => source.emit('step_token', 'not json{', 1)).not.toThrow()
      expect(handlers.onStepToken).not.toHaveBeenCalled()

      source.emit('step_token', { index: 1, delta: 'ok' }, 2)
      expect(handlers.onStepToken).toHaveBeenCalledWith(1, 'ok')
    })
  })

  describe('reconnection', () => {
    it('reconnects with the resume cursor after a transport drop', async () => {
      const { handlers } = makeHandlers()
      const stream = usePipelineStream(handlers)
      await stream.subscribe('run-1')

      FakeEventSource.last.emit('step_token', { index: 1, delta: 'a' }, 7)
      FakeEventSource.last.fail()
      await vi.advanceTimersByTimeAsync(1000)

      expect(FakeEventSource.openCount).toBe(2)
      // Resume is strictly after the last applied seq, so the server never
      // replays an event the UI already counted.
      expect(FakeEventSource.last.afterSeqParam).toBe(7)
    })

    it('backs off exponentially between attempts', async () => {
      const { handlers } = makeHandlers()
      const stream = usePipelineStream(handlers, { initialDelayMs: 1000, maxRetries: 5 })
      await stream.subscribe('run-1')

      FakeEventSource.last.fail()
      await vi.advanceTimersByTimeAsync(999)
      expect(FakeEventSource.openCount).toBe(1)
      await vi.advanceTimersByTimeAsync(1)
      expect(FakeEventSource.openCount).toBe(2)

      FakeEventSource.last.fail()
      await vi.advanceTimersByTimeAsync(1999)
      expect(FakeEventSource.openCount).toBe(2)
      await vi.advanceTimersByTimeAsync(1)
      expect(FakeEventSource.openCount).toBe(3)

      FakeEventSource.last.fail()
      await vi.advanceTimersByTimeAsync(4000)
      expect(FakeEventSource.openCount).toBe(4)
    })

    it('caps the delay at maxDelayMs', async () => {
      const { handlers } = makeHandlers()
      const stream = usePipelineStream(handlers, {
        initialDelayMs: 1000,
        maxDelayMs: 2000,
        maxRetries: 10
      })
      await stream.subscribe('run-1')

      for (let i = 0; i < 4; i += 1) {
        FakeEventSource.last.fail()
        await vi.advanceTimersByTimeAsync(2000)
      }

      expect(FakeEventSource.openCount).toBe(5)
    })

    it('resets the attempt counter after a successful reopen', async () => {
      const { handlers, states } = makeHandlers()
      const stream = usePipelineStream(handlers, { initialDelayMs: 1000, maxRetries: 2 })
      await stream.subscribe('run-1')

      FakeEventSource.last.fail()
      await vi.advanceTimersByTimeAsync(1000)
      FakeEventSource.last.emit('hello', {})

      const reopened = states.filter(s => s.state === 'open')
      expect(reopened[reopened.length - 1].attempt).toBe(0)

      // With the budget reset, two further failures are retried rather than
      // treated as exhaustion.
      FakeEventSource.last.fail()
      await vi.advanceTimersByTimeAsync(1000)
      expect(handlers.onConnectionLost).not.toHaveBeenCalled()
      expect(FakeEventSource.openCount).toBe(3)
    })

    it('gives up after maxRetries and reports exhaustion once', async () => {
      const { handlers, states } = makeHandlers()
      const stream = usePipelineStream(handlers, { initialDelayMs: 100, maxRetries: 2 })
      await stream.subscribe('run-1')

      FakeEventSource.last.fail()
      await vi.advanceTimersByTimeAsync(100)
      FakeEventSource.last.fail()
      await vi.advanceTimersByTimeAsync(200)
      expect(FakeEventSource.openCount).toBe(3)

      FakeEventSource.last.fail()
      await vi.advanceTimersByTimeAsync(10000)

      expect(FakeEventSource.openCount).toBe(3)
      expect(handlers.onConnectionLost).toHaveBeenCalledTimes(1)
      expect(states[states.length - 1]).toMatchObject({ state: 'closed', exhausted: true })
    })

    it('preserves the cursor across a manual resume', async () => {
      const { handlers } = makeHandlers()
      const stream = usePipelineStream(handlers, { initialDelayMs: 100, maxRetries: 1 })
      await stream.subscribe('run-1')

      FakeEventSource.last.emit('step_complete', { index: 1, output: 'x' }, 12)
      FakeEventSource.last.fail()
      await vi.advanceTimersByTimeAsync(100)
      FakeEventSource.last.fail()
      await vi.advanceTimersByTimeAsync(1000)
      expect(handlers.onConnectionLost).toHaveBeenCalled()

      stream.resume()

      expect(FakeEventSource.last.afterSeqParam).toBe(12)
    })
  })

  describe('event idempotency', () => {
    it('ignores a replayed prefix so tokens are not double-counted', async () => {
      const tokens: string[] = []
      const { handlers } = makeHandlers({
        onStepToken: (_index: number, delta: string) => tokens.push(delta)
      })
      const stream = usePipelineStream(handlers)
      await stream.subscribe('run-1')

      FakeEventSource.last.emit('step_token', { index: 1, delta: 'a' }, 1)
      FakeEventSource.last.emit('step_token', { index: 1, delta: 'b' }, 2)
      FakeEventSource.last.fail()
      await vi.advanceTimersByTimeAsync(1000)

      // A server that rounds the cursor down replays seq 1 and 2.
      FakeEventSource.last.emit('step_token', { index: 1, delta: 'a' }, 1)
      FakeEventSource.last.emit('step_token', { index: 1, delta: 'b' }, 2)
      FakeEventSource.last.emit('step_token', { index: 1, delta: 'c' }, 3)

      expect(tokens).toEqual(['a', 'b', 'c'])
    })

    it('ignores duplicates delivered on one connection', async () => {
      const { handlers } = makeHandlers()
      const stream = usePipelineStream(handlers)
      await stream.subscribe('run-1')

      FakeEventSource.last.emit('step_complete', { index: 1, output: 'x' }, 4)
      FakeEventSource.last.emit('step_complete', { index: 1, output: 'x' }, 4)

      expect(handlers.onStepComplete).toHaveBeenCalledTimes(1)
    })

    it('treats unsequenced keepalives as liveness only', async () => {
      const { handlers } = makeHandlers()
      const stream = usePipelineStream(handlers)
      await stream.subscribe('run-1')

      FakeEventSource.last.emit('step_token', { index: 1, delta: 'a' }, 5)
      FakeEventSource.last.emit('hello', {})
      FakeEventSource.last.emit('ping', {})
      FakeEventSource.last.fail()
      await vi.advanceTimersByTimeAsync(1000)

      // hello/ping carry no id, so they must not rewind the cursor.
      expect(FakeEventSource.last.afterSeqParam).toBe(5)
    })
  })

  describe('terminal events', () => {
    it('stops retrying after run_complete', async () => {
      const { handlers } = makeHandlers()
      const stream = usePipelineStream(handlers)
      await stream.subscribe('run-1')
      const source = FakeEventSource.last

      source.emit('run_complete', { final_content: { content: 'x' }, total_cost: 1 }, 9)
      expect(handlers.onRunComplete).toHaveBeenCalledTimes(1)
      expect(source.closed).toBe(true)

      source.fail()
      await vi.advanceTimersByTimeAsync(60000)

      expect(FakeEventSource.openCount).toBe(1)
      expect(handlers.onConnectionLost).not.toHaveBeenCalled()
    })

    it('stops retrying after run_failed', async () => {
      const { handlers } = makeHandlers()
      const stream = usePipelineStream(handlers)
      await stream.subscribe('run-1')

      FakeEventSource.last.emit('run_failed', { error: 'boom' }, 3)
      await vi.advanceTimersByTimeAsync(60000)

      expect(handlers.onRunFailed).toHaveBeenCalledWith('boom')
      expect(FakeEventSource.openCount).toBe(1)
    })

    it('stops retrying after run_cancelled', async () => {
      const { handlers } = makeHandlers()
      const stream = usePipelineStream(handlers)
      await stream.subscribe('run-1')

      FakeEventSource.last.emit('run_cancelled', {}, 3)
      await vi.advanceTimersByTimeAsync(60000)

      expect(handlers.onRunCancelled).toHaveBeenCalledTimes(1)
      expect(FakeEventSource.openCount).toBe(1)
    })
  })

  describe('staleness', () => {
    it('reports stale after the silence budget without closing the socket', async () => {
      const { handlers, states } = makeHandlers()
      const stream = usePipelineStream(handlers, { staleAfterMs: 5000 })
      await stream.subscribe('run-1')
      FakeEventSource.last.emit('hello', {})

      await vi.advanceTimersByTimeAsync(5000)

      expect(states[states.length - 1].state).toBe('stale')
      expect(FakeEventSource.last.closed).toBe(false)
      expect(handlers.onConnectionLost).not.toHaveBeenCalled()
    })

    it('clears stale once an event arrives', async () => {
      const { handlers, states } = makeHandlers()
      const stream = usePipelineStream(handlers, { staleAfterMs: 5000 })
      await stream.subscribe('run-1')
      FakeEventSource.last.emit('hello', {})
      await vi.advanceTimersByTimeAsync(5000)
      expect(states[states.length - 1].state).toBe('stale')

      FakeEventSource.last.emit('step_token', { index: 1, delta: 'a' }, 1)

      expect(states[states.length - 1].state).toBe('open')
    })

    it('does not go stale after a terminal event', async () => {
      const { handlers, states } = makeHandlers()
      const stream = usePipelineStream(handlers, { staleAfterMs: 5000 })
      await stream.subscribe('run-1')

      FakeEventSource.last.emit('run_complete', { final_content: { content: 'x' } }, 2)
      await vi.advanceTimersByTimeAsync(60000)

      expect(states.some(s => s.state === 'stale')).toBe(false)
    })
  })

  describe('close', () => {
    it('closes the socket and cancels a pending reconnect', async () => {
      const { handlers } = makeHandlers()
      const stream = usePipelineStream(handlers, { initialDelayMs: 1000 })
      await stream.subscribe('run-1')
      const source = FakeEventSource.last

      source.fail()
      stream.close()
      await vi.advanceTimersByTimeAsync(60000)

      expect(source.closed).toBe(true)
      expect(FakeEventSource.openCount).toBe(1)
    })

    it('resets the cursor when subscribing to a different run', async () => {
      const { handlers } = makeHandlers()
      const stream = usePipelineStream(handlers)
      await stream.subscribe('run-1')
      FakeEventSource.last.emit('step_token', { index: 1, delta: 'a' }, 9)

      await stream.subscribe('run-2')

      expect(FakeEventSource.last.url).toContain('run-2')
      expect(FakeEventSource.last.afterSeqParam).toBeNull()
      expect(stream.getStatus().lastSeq).toBe(0)
    })
  })
})
