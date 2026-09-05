import {
  pipelineStreamUrl,
  type AgentFinalContent,
  type PipelinePlanStep,
  type SubAgentToolEvent
} from '../api/agent'

export interface ToolCallStartEvent {
  index: number
  name: string
  args: Record<string, unknown>
}

export interface ToolCallResultEvent extends ToolCallStartEvent {
  status: 'completed' | 'failed'
  preview?: string
  error?: string | null
  duration_ms?: number
}

export interface StepCompleteEvent {
  index: number
  output: string
  duration_ms: number
  prompt_tokens: number
  completion_tokens: number
  cost_estimate: number
  tool_events?: SubAgentToolEvent[]
}

export interface PipelineRunCompleteEvent {
  final_content: AgentFinalContent
  saved_content_id?: number | null
  total_prompt_tokens: number
  total_completion_tokens: number
  total_cost: number
  revision_count: number
}

/**
 * Connection lifecycle, kept separate from run lifecycle.
 *
 * `stale` means the socket is still open but the server has gone quiet past the
 * keepalive budget: the run may still be alive, so we surface it rather than
 * tearing the connection down. `reconnecting` is a scheduled retry with the
 * resume cursor; `closed` is terminal for this subscription.
 */
export type StreamConnectionState =
  | 'idle'
  | 'connecting'
  | 'open'
  | 'stale'
  | 'reconnecting'
  | 'closed'

export interface StreamStatus {
  state: StreamConnectionState
  /** Highest server sequence applied. Doubles as the resume cursor. */
  lastSeq: number
  /** Reconnect attempts spent since the last successful open. */
  attempt: number
  /** Set when the transport gave up permanently and the caller must reconcile. */
  exhausted?: boolean
}

export interface PipelineStreamHandlers {
  onPlanReady(plan: PipelinePlanStep[]): void
  onStepStart(index: number): void
  onStepToken(index: number, delta: string): void
  onToolCallStart(event: ToolCallStartEvent): void
  onToolCallResult(event: ToolCallResultEvent): void
  onStepComplete(event: StepCompleteEvent): void
  onStepFailed(index: number, error: string): void
  onPlanRevised(plan: PipelinePlanStep[], revision: number): void
  onRunComplete(event: PipelineRunCompleteEvent): void
  onRunFailed(error?: string): void
  onRunCancelled?(): void
  /**
   * Transport gave up after exhausting retries. The run itself may well have
   * finished; the caller is expected to reconcile against GET /agent/runs/{id}
   * instead of assuming failure.
   */
  onConnectionLost?(): void
  onStateChange?(status: StreamStatus): void
}

export interface PipelineStreamOptions {
  /** Reconnect attempts before giving up and calling onConnectionLost. */
  maxRetries?: number
  initialDelayMs?: number
  maxDelayMs?: number
  /** Silence budget before the connection is reported `stale`. */
  staleAfterMs?: number
}

const DEFAULTS: Required<PipelineStreamOptions> = {
  maxRetries: 6,
  initialDelayMs: 1000,
  maxDelayMs: 30000,
  staleAfterMs: 45000
}

const TERMINAL_EVENTS = new Set(['run_complete', 'run_failed', 'run_cancelled'])

export function usePipelineStream(
  handlers: PipelineStreamHandlers,
  options: PipelineStreamOptions = {}
) {
  const opts = { ...DEFAULTS, ...options }

  let eventSource: EventSource | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let staleTimer: ReturnType<typeof setTimeout> | null = null
  let currentRunId = ''
  let state: StreamConnectionState = 'idle'
  let attempt = 0
  // Resume cursor. Every reconnect asks for events strictly after this seq, so a
  // replayed prefix is never re-applied and tokens are not double-counted.
  let lastSeq = 0
  let terminal = false

  function status(exhausted?: boolean): StreamStatus {
    return exhausted ? { state, lastSeq, attempt, exhausted } : { state, lastSeq, attempt }
  }

  function setState(next: StreamConnectionState, exhausted?: boolean) {
    if (state === next && !exhausted) return
    state = next
    handlers.onStateChange?.(status(exhausted))
  }

  function clearTimers() {
    if (retryTimer) {
      clearTimeout(retryTimer)
      retryTimer = null
    }
    if (staleTimer) {
      clearTimeout(staleTimer)
      staleTimer = null
    }
  }

  function markActivity() {
    if (staleTimer) clearTimeout(staleTimer)
    if (terminal) return
    staleTimer = setTimeout(() => {
      // Socket is still open; only the liveness signal is missing. `connecting`
      // counts too: a proxy that accepts the TCP connection and then sends
      // nothing produces neither an event nor an error, and would otherwise
      // leave the UI waiting forever.
      if (state === 'open' || state === 'connecting') setState('stale')
    }, opts.staleAfterMs)
  }

  function close() {
    clearTimers()
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    if (state !== 'idle' && state !== 'closed') setState('closed')
  }

  /** Terminal run event: stop for good, and never schedule another retry. */
  function finish() {
    terminal = true
    close()
  }

  function backoffDelay(nextAttempt: number) {
    const raw = opts.initialDelayMs * Math.pow(2, Math.max(0, nextAttempt - 1))
    return Math.min(raw, opts.maxDelayMs)
  }

  function scheduleReconnect() {
    if (terminal) return
    if (attempt >= opts.maxRetries) {
      clearTimers()
      if (eventSource) {
        eventSource.close()
        eventSource = null
      }
      state = 'closed'
      handlers.onStateChange?.(status(true))
      handlers.onConnectionLost?.()
      return
    }
    attempt += 1
    const delay = backoffDelay(attempt)
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    if (staleTimer) {
      clearTimeout(staleTimer)
      staleTimer = null
    }
    setState('reconnecting')
    retryTimer = setTimeout(() => {
      retryTimer = null
      open()
    }, delay)
  }

  function open() {
    if (terminal || !currentRunId) return
    const url = pipelineStreamUrl(currentRunId, lastSeq > 0 ? lastSeq : undefined)
    setState('connecting')
    const source = new EventSource(url, { withCredentials: true })
    eventSource = source
    bind(source)
    markActivity()
  }

  /**
   * Applies one server event exactly once.
   *
   * Returns false when the event's seq was already applied, which happens on
   * every resume whose cursor the server rounds down, and on any duplicate
   * delivery. Callers must not mutate run state for a rejected event.
   */
  function accept(event: Event): boolean {
    if (isAlreadyApplied(event)) return false
    receiveActivity()
    return true
  }

  function receiveActivity() {
    if (terminal) return
    if (state !== 'open') {
      attempt = 0
      setState('open')
    }
    markActivity()
  }

  /** Advances the resume cursor, or reports the seq as already applied. */
  function isAlreadyApplied(event: Event): boolean {
    const seq = Number((event as MessageEvent).lastEventId)
    // Run frames without a usable sequence cannot advance the replay cursor.
    if (!Number.isFinite(seq) || seq <= 0) return false
    if (seq <= lastSeq) return true
    lastSeq = seq
    return false
  }

  function bind(source: EventSource) {
    // EventSource inherits the preceding lastEventId when a frame omits `id:`.
    // Heartbeats therefore bypass run-event dedupe entirely: they refresh
    // liveness without reading or advancing the persisted replay cursor.
    source.addEventListener('hello', receiveActivity)
    source.addEventListener('ping', receiveActivity)

    source.addEventListener('plan_ready', event => {
      if (!accept(event)) return
      const data = parseEvent<{ plan: PipelinePlanStep[] }>(event)
      if (data) handlers.onPlanReady(data.plan)
    })

    source.addEventListener('step_start', event => {
      if (!accept(event)) return
      const data = parseEvent<{ index: number }>(event)
      if (data) handlers.onStepStart(data.index)
    })

    source.addEventListener('step_token', event => {
      if (!accept(event)) return
      const data = parseEvent<{ index: number; delta: string }>(event)
      if (data) handlers.onStepToken(data.index, data.delta)
    })

    source.addEventListener('tool_call_start', event => {
      if (!accept(event)) return
      const data = parseEvent<ToolCallStartEvent>(event)
      if (data) handlers.onToolCallStart(data)
    })

    source.addEventListener('tool_call_result', event => {
      if (!accept(event)) return
      const data = parseEvent<ToolCallResultEvent>(event)
      if (data) handlers.onToolCallResult(data)
    })

    source.addEventListener('step_complete', event => {
      if (!accept(event)) return
      const data = parseEvent<StepCompleteEvent>(event)
      if (data) handlers.onStepComplete(data)
    })

    source.addEventListener('step_failed', event => {
      if (!accept(event)) return
      const data = parseEvent<{ index: number; error: string }>(event)
      if (data) handlers.onStepFailed(data.index, data.error)
    })

    source.addEventListener('plan_revised', event => {
      if (!accept(event)) return
      const data = parseEvent<{ plan: PipelinePlanStep[]; revision: number }>(event)
      if (data) handlers.onPlanRevised(data.plan, data.revision)
    })

    source.addEventListener('run_complete', event => {
      if (!accept(event)) return
      const data = parseEvent<PipelineRunCompleteEvent>(event)
      finish()
      if (data) handlers.onRunComplete(data)
    })

    source.addEventListener('run_failed', event => {
      if (!accept(event)) return
      const data = parseEvent<{ error?: string }>(event)
      finish()
      handlers.onRunFailed(data?.error)
    })

    source.addEventListener('run_cancelled', event => {
      if (!accept(event)) return
      finish()
      handlers.onRunCancelled?.()
    })

    source.onerror = () => {
      // A terminal run event already closed us; a trailing error is noise.
      if (terminal) return
      scheduleReconnect()
    }
  }

  async function subscribe(runId: string) {
    close()
    currentRunId = runId
    terminal = false
    attempt = 0
    lastSeq = 0
    state = 'idle'
    open()
  }

  /**
   * Reopens a subscription that gave up, keeping the resume cursor so the server
   * replays only what was missed. Used by the manual reconnect affordance after
   * automatic retries are exhausted.
   */
  function resume() {
    if (!currentRunId) return
    clearTimers()
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    terminal = false
    attempt = 0
    open()
  }

  return {
    close,
    subscribe,
    resume,
    getStatus: () => status()
  }
}

function parseEvent<T>(event: Event): T | null {
  const raw = (event as MessageEvent).data
  if (typeof raw !== 'string' || raw.length === 0) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    // A malformed frame must not kill the subscription; the next event or the
    // reconciliation path will correct the view.
    return null
  }
}
