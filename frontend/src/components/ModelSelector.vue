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
  color: #6b7468;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.selector-head h3 {
  margin: 5px 0 0;
  color: #182126;
  font-size: 18px;
}

.selector-pill {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
}

.selector-pill.ready {
  color: #0e6154;
  background: rgba(15, 133, 116, 0.12);
}

.selector-pill.warn {
  color: #8a5d19;
  background: rgba(196, 147, 63, 0.12);
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
  gap: 8px;
}

.selector-field > span {
  color: #425158;
  font-size: 13px;
  font-weight: 600;
}

.selector-meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.meta-card {
  padding: 12px;
  border: 1px solid rgba(24, 33, 38, 0.08);
  border-radius: 8px;
  background: rgba(248, 244, 237, 0.86);
}

.meta-card span {
  display: block;
  color: #738086;
  font-size: 12px;
}

.meta-card strong {
  display: block;
  margin-top: 6px;
  color: #182126;
  font-size: 14px;
  line-height: 1.45;
  word-break: break-word;
}

@media (max-width: 900px) {
  .selector-grid,
  .selector-meta {
    grid-template-columns: 1fr;
  }
}
</style>
