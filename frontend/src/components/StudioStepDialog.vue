<script setup lang="ts">
/**
 * Detail view for one pipeline step: its status, tool trace, and output.
 *
 * Presentation only — the parent owns which step is open and the streaming
 * buffers. The tool trace is passed pre-resolved rather than looked up here,
 * because live events and the recorded events on the step come from different
 * places and the parent already knows which one wins.
 */
import { Loading } from '@element-plus/icons-vue'
import type { PipelinePlanStep, SubAgentToolEvent } from '../api/agent'
import { agentLabel, formatToolArgs, formatToolPreview, isResearchStep, statusLabel, statusToPill } from '../composables/useStudioPresentation'

const props = defineProps<{
  open: boolean
  step: PipelinePlanStep | null
  /** Already resolved by the parent: live events win over recorded ones. */
  toolEvents: SubAgentToolEvent[]
  /** Streamed text so far, used until the step's own output is available. */
  streamingOutput: string
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
}>()

function displayOutput(): string {
  if (!props.step) return ''
  return props.step.output || props.streamingOutput
}
</script>

<template>
  <el-dialog
    :model-value="open"
    :title="step ? `Step ${step.index} · ${agentLabel(step.agent_id)}` : ''"
    width="720px"
    append-to-body
    destroy-on-close
    @update:model-value="emit('update:open', $event)"
  >
    <template v-if="step">
      <div class="step-dialog-meta">
        <span class="surface-kicker">
          {{ step.agent_id }}
          <span v-if="isResearchStep(step.agent_id)" class="research-tag">research</span>
        </span>
        <span class="surface-pill" :class="statusToPill(step.status)">{{ statusLabel(step.status) }}</span>
        <small v-if="step.duration_ms" class="step-dialog-duration">{{ step.duration_ms }} ms</small>
      </div>
      <p class="step-description">{{ step.description }}</p>
      <ul v-if="toolEvents.length" class="tool-trace">
        <li
          v-for="(event, idx) in toolEvents"
          :key="`${step.index}-${idx}-${event.name}`"
          class="tool-row"
          :class="event.status"
        >
          <span class="tool-arrow">▸</span>
          <span class="tool-name">{{ event.name }}</span>
          <span v-if="formatToolArgs(event.args)" class="tool-args">({{ formatToolArgs(event.args) }})</span>
          <span v-if="event.status === 'started'" class="tool-status">运行中…</span>
          <template v-else>
            <span class="tool-arrow">→</span>
            <span v-if="event.status === 'failed'" class="tool-error">{{ event.error || '失败' }}</span>
            <span v-else class="tool-preview">{{ formatToolPreview(event.preview) }}</span>
            <span v-if="event.duration_ms" class="tool-duration">{{ event.duration_ms }} ms</span>
          </template>
        </li>
      </ul>
      <pre v-if="displayOutput()" class="step-output">{{ displayOutput() }}</pre>
      <div v-else-if="step.status === 'running'" class="step-running">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在生成…</span>
      </div>
      <div v-else-if="step.status === 'completed'" class="step-empty">
        该步骤未产出文本输出，仅记录上方工具调用。
      </div>
      <div v-else-if="step.status === 'failed'" class="step-empty failed">
        步骤失败，未产出输出
      </div>
      <div v-else-if="step.status === 'skipped'" class="step-empty">已跳过</div>
      <div v-else class="step-pending">等待执行</div>
    </template>
  </el-dialog>
</template>

<style scoped>
.surface-kicker {
  display: inline-block;
  color: var(--c-text-tertiary);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.surface-pill {
  display: inline-flex;
  align-items: center;
  min-height: 25px;
  padding: 2px 9px;
  border: 1px solid var(--c-border-soft);
  border-radius: 999px;
  color: var(--c-text-secondary);
  background: var(--c-bg-soft);
  font-size: 12px;
  font-weight: 500;
  font-family: var(--font-ui);
  letter-spacing: 0;
  white-space: nowrap;
}

.research-tag {
  display: inline-flex;
  align-items: center;
  height: 16px;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--c-accent-soft);
  color: var(--c-accent);
  font-size: 9.5px;
  font-weight: 600;
  font-family: var(--font-mono);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.step-dialog-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.step-dialog-duration {
  margin-left: auto;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-family: var(--font-mono);
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
}

.step-description {
  margin: 0 0 12px;
  color: var(--c-text-secondary);
  font-size: 12.5px;
  line-height: 1.55;
}

.tool-trace {
  list-style: none;
  margin: 0 0 12px;
  padding: 8px 12px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg-soft);
  display: grid;
  gap: 4px;
  font-family: var(--font-mono);
  font-size: 11.5px;
  line-height: 1.55;
}

.tool-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
  color: var(--c-text-secondary);
}

.tool-row.failed {
  color: var(--c-fail);
}

.tool-row.completed .tool-name {
  color: var(--c-text);
}

.tool-arrow {
  color: var(--c-text-tertiary);
}

.tool-name {
  color: var(--c-accent);
  font-weight: 600;
}

.tool-args {
  color: var(--c-text-tertiary);
  word-break: break-word;
}

.tool-status {
  color: var(--c-warn);
  font-style: italic;
}

.tool-preview {
  flex: 1 0 100%;
  min-width: 0;
  margin-left: 18px;
  color: var(--c-text-secondary);
  word-break: break-word;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.tool-error {
  flex: 1 0 100%;
  min-width: 0;
  margin-left: 18px;
  color: var(--c-fail);
  word-break: break-word;
  overflow-wrap: anywhere;
}

.tool-duration {
  color: var(--c-text-tertiary);
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
}

.step-output {
  margin: 0;
  padding: 14px;
  max-height: 420px;
  overflow-y: auto;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg-code);
  color: var(--c-text);
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-mono);
  font-size: 12.5px;
  line-height: 1.6;
}

.step-running {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 12px 14px;
  border: 1px solid var(--c-accent);
  border-radius: 6px;
  background: var(--c-accent-soft);
  color: var(--c-accent);
  font-size: 13px;
}

.step-pending {
  padding: 12px 14px;
  border: 1px dashed var(--c-border);
  border-radius: 6px;
  color: var(--c-text-tertiary);
  font-size: 13px;
}

.step-empty {
  padding: 12px 14px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg-soft);
  color: var(--c-text-tertiary);
  font-size: 12.5px;
  line-height: 1.55;
}

.step-empty.failed {
  border-color: var(--c-fail);
  color: var(--c-fail);
  background: var(--c-fail-soft);
}
.is-loading {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* The spinner is decorative motion; match the page's reduced-motion contract. */
@media (prefers-reduced-motion: reduce) {
  .is-loading {
    animation: none;
  }
}
</style>
