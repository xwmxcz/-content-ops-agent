<template>
  <section class="model-selector">
    <div class="selector-head">
      <div>
        <span class="selector-kicker">Model Control</span>
        <h3>模型选择</h3>
      </div>
      <span class="selector-pill" :class="activeProvider?.configured ? 'ready' : 'warn'">
        {{ activeProvider?.configured ? '已配置' : '未配置' }}
      </span>
    </div>

    <div class="selector-grid">
      <div class="selector-field">
        <span>提供商</span>
        <el-select v-model="local.provider" placeholder="选择提供商" @change="onProviderChange">
          <el-option
            v-for="provider in providers"
            :key="provider.id"
            :label="provider.name"
            :value="provider.id"
          />
        </el-select>
      </div>

      <div class="selector-field">
        <span>模型</span>
        <el-select v-model="local.model" placeholder="选择模型">
          <el-option v-for="model in activeModels" :key="model.id" :label="model.name" :value="model.id" />
        </el-select>
      </div>
    </div>

    <div class="selector-meta">
      <article class="meta-card">
        <span>默认模型</span>
        <strong>{{ activeProvider?.default_model || '未设置' }}</strong>
      </article>
      <article class="meta-card">
        <span>可用模型</span>
        <strong>{{ activeModels.length }}</strong>
      </article>
      <article class="meta-card">
        <span>当前选择</span>
        <strong>{{ local.model || '自动' }}</strong>
      </article>
    </div>

    <div class="selector-grid compact">
      <div class="selector-field">
        <span>Temperature</span>
        <el-slider v-model="local.temperature" :min="0" :max="1" :step="0.1" />
      </div>

      <div class="selector-field">
        <span>Max Tokens</span>
        <el-input-number v-model="local.max_tokens" :min="128" :max="8192" :step="256" />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, watch } from 'vue'
import { getModels, type ProviderInfo } from '../api/content'

type ModelConfig = {
  provider?: string
  model?: string
  temperature: number
  max_tokens: number
}

const props = defineProps<{ modelValue: ModelConfig }>()

const emit = defineEmits<{
  'update:modelValue': [value: ModelConfig]
}>()

const providers = reactive<ProviderInfo[]>([])
const local = reactive<ModelConfig>({ ...props.modelValue })

const activeProvider = computed(() => providers.find(provider => provider.id === local.provider))
const activeModels = computed(() => activeProvider.value?.models ?? [])

watch(
  () => props.modelValue,
  value => {
    Object.assign(local, value)
  },
  { deep: true }
)

watch(
  local,
  value => {
    emit('update:modelValue', { ...value })
  },
  { deep: true }
)

function onProviderChange() {
  const defaultModel = activeProvider.value?.default_model
  const hasDefaultModel = activeModels.value.some(model => model.id === defaultModel)
  local.model = hasDefaultModel ? defaultModel : activeModels.value[0]?.id
}

onMounted(async () => {
  providers.splice(0, providers.length, ...(await getModels()))
  if (!local.provider) {
    local.provider = providers.find(provider => provider.configured)?.id ?? providers[0]?.id
  }
  if (!local.model) {
    onProviderChange()
  }
})
</script>

<style scoped>
.model-selector {
  display: grid;
  gap: 14px;
}

.selector-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.selector-kicker {
  display: inline-block;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.selector-head h3 {
  margin: 4px 0 0;
  color: var(--c-text);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -0.015em;
}

.selector-pill {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  font-family: var(--font-mono);
  letter-spacing: -0.01em;
  border: 1px solid var(--c-border);
}

.selector-pill.ready {
  color: var(--c-ok);
  border-color: var(--c-ok);
  background: var(--c-ok-soft);
}

.selector-pill.warn {
  color: var(--c-warn);
  border-color: var(--c-warn);
  background: var(--c-warn-soft);
}

.selector-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}

.selector-grid.compact {
  align-items: start;
}

.selector-field {
  display: grid;
  gap: 6px;
}

.selector-field > span {
  color: var(--c-text-secondary);
  font-size: 12px;
  font-weight: 500;
}

.selector-meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.meta-card {
  padding: 10px 12px;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  background: var(--c-bg-soft);
}

.meta-card span {
  display: block;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.meta-card strong {
  display: block;
  margin-top: 4px;
  color: var(--c-text);
  font-size: 12.5px;
  font-weight: 500;
  font-family: var(--font-mono);
  line-height: 1.4;
  letter-spacing: -0.01em;
  word-break: break-word;
}

@media (max-width: 900px) {
  .selector-grid,
  .selector-meta {
    grid-template-columns: 1fr;
  }
}
</style>
