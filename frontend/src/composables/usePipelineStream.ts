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
  onConnectionLost?(): void
}

export function usePipelineStream(handlers: PipelineStreamHandlers) {
  let eventSource: EventSource | null = null

  function close() {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
  }

  function subscribe(runId: string) {
    close()
    const source = new EventSource(pipelineStreamUrl(runId))
    eventSource = source

    source.addEventListener('plan_ready', event => {
      const data = parseEvent<{ plan: PipelinePlanStep[] }>(event)
      handlers.onPlanReady(data.plan)
    })

    source.addEventListener('step_start', event => {
      const data = parseEvent<{ index: number }>(event)
      handlers.onStepStart(data.index)
    })

    source.addEventListener('step_token', event => {
      const data = parseEvent<{ index: number; delta: string }>(event)
      handlers.onStepToken(data.index, data.delta)
    })

    source.addEventListener('tool_call_start', event => {
      handlers.onToolCallStart(parseEvent<ToolCallStartEvent>(event))
    })

    source.addEventListener('tool_call_result', event => {
      handlers.onToolCallResult(parseEvent<ToolCallResultEvent>(event))
    })

    source.addEventListener('step_complete', event => {
      handlers.onStepComplete(parseEvent<StepCompleteEvent>(event))
    })

    source.addEventListener('step_failed', event => {
      const data = parseEvent<{ index: number; error: string }>(event)
      handlers.onStepFailed(data.index, data.error)
    })

    source.addEventListener('plan_revised', event => {
      const data = parseEvent<{ plan: PipelinePlanStep[]; revision: number }>(event)
      handlers.onPlanRevised(data.plan, data.revision)
    })

    source.addEventListener('run_complete', event => {
      handlers.onRunComplete(parseEvent<PipelineRunCompleteEvent>(event))
    })

    source.addEventListener('run_failed', event => {
      const data = parseEvent<{ error?: string }>(event)
      handlers.onRunFailed(data.error)
    })

    source.addEventListener('run_cancelled', () => {
      handlers.onRunCancelled?.()
    })

    source.onerror = () => {
      handlers.onConnectionLost?.()
    }
  }

  return {
    close,
    subscribe
  }
}

function parseEvent<T>(event: Event): T {
  return JSON.parse((event as MessageEvent).data) as T
}
