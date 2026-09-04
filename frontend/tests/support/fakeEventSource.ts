/**
 * Minimal EventSource double.
 *
 * jsdom has no EventSource, and the real one would reconnect on its own, which
 * is exactly the behaviour under test. This double never reconnects: every
 * connection attempt is an explicit, observable construction, so the composable's
 * own backoff and resume cursor are the only things driving reconnects.
 */
export class FakeEventSource {
  static instances: FakeEventSource[] = []

  static reset() {
    FakeEventSource.instances = []
  }

  static get last(): FakeEventSource {
    const found = FakeEventSource.instances[FakeEventSource.instances.length - 1]
    if (!found) throw new Error('No FakeEventSource has been constructed')
    return found
  }

  static get openCount() {
    return FakeEventSource.instances.length
  }

  url: string
  withCredentials: boolean
  closed = false
  onerror: ((event: Event) => void) | null = null

  private listeners = new Map<string, Array<(event: Event) => void>>()

  constructor(url: string, init?: { withCredentials?: boolean }) {
    this.url = url
    this.withCredentials = Boolean(init?.withCredentials)
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, handler: (event: Event) => void) {
    const existing = this.listeners.get(type)
    if (existing) existing.push(handler)
    else this.listeners.set(type, [handler])
  }

  close() {
    this.closed = true
  }

  /** Delivers one server frame. `seq` maps to the SSE `id:` field. */
  emit(type: string, data: unknown, seq?: number) {
    if (this.closed) throw new Error(`emit("${type}") on a closed EventSource`)
    const handlers = this.listeners.get(type)
    if (!handlers) return
    const event = {
      data: typeof data === 'string' ? data : JSON.stringify(data),
      lastEventId: seq === undefined ? '' : String(seq)
    } as MessageEvent
    handlers.forEach(handler => handler(event as unknown as Event))
  }

  /** Simulates a transport drop. */
  fail() {
    this.onerror?.(new Event('error'))
  }

  get afterSeqParam(): number | null {
    const match = /[?&]after_seq=(\d+)/.exec(this.url)
    return match ? Number(match[1]) : null
  }
}

export function installFakeEventSource() {
  FakeEventSource.reset()
  ;(globalThis as unknown as { EventSource: unknown }).EventSource = FakeEventSource
}
