<template>
  <section class="model-selector">
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
        <el-select v-model="local.model" placeholder="选择模型" :fit-input-width="false">
          <el-option v-for="model in activeModels" :key="model.id" :label="model.name" :value="model.id" />
        </el-select>
        <span v-if="local.model" class="selector-field-caption" :title="local.model">{{ local.model }}</span>
      </div>
    </div>

    <div class="selector-status">
      <span :class="['selector-status-dot', activeProvider?.configured ? 'ready' : 'warn']" aria-hidden="true"></span>
      <span class="selector-status-text">
        {{ activeProvider?.configured ? '已配置' : '未配置' }}
      </span>
      <span class="selector-status-meta">
        {{ activeModels.length }} 个可选模型
      </span>
    </div>

      <div class="selector-grid compact">
      <div class="selector-field">
        <span title="值越高，表达越多样">创意程度 ({{ local.temperature.toFixed(1) }})</span>
        <el-slider v-model="local.temperature" :min="0" :max="1" :step="0.1" />
      </div>

      <div class="selector-field">
        <span title="单次模型回复的最大 token 数">输出上限 (Tokens)</span>
        <el-input-number v-model="local.max_tokens" :min="128" :max="8192" :step="256" controls-position="right" />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, watch } from 'vue'
import { ElInputNumber } from 'element-plus/es/components/input-number/index'
import { ElSlider } from 'element-plus/es/components/slider/index'
import 'element-plus/es/components/input-number/style/css'
import 'element-plus/es/components/slider/style/css'
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
.model-selector { display: grid; gap: 14px; min-width: 0; }
.selector-grid { display: grid; grid-template-columns: 1fr; gap: 12px; }
.selector-grid.compact {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 14px;
  align-items: center;
  padding-top: 4px;
}
.selector-field { display: grid; gap: 6px; min-width: 0; align-content: start; }
.selector-field > span {
  color: var(--c-text-secondary);
  font-size: 12px;
  font-weight: 600;
}
.selector-field .selector-field-caption {
  display: inline-block;
  justify-self: start;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--c-bg-soft);
  border: 1px solid var(--c-border-soft);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  color: var(--c-text-secondary);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.4;
}
.selector-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 9px;
  background: var(--c-bg-soft);
  border: 1px solid var(--c-border-soft);
  font-size: 12px;
}
.selector-status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.selector-status-dot.ready {
  background: var(--c-ok);
  box-shadow: 0 0 0 3px rgba(5, 150, 105, 0.16);
}
.selector-status-dot.warn {
  background: var(--c-warn);
  box-shadow: 0 0 0 3px rgba(217, 119, 6, 0.16);
}
.selector-status-text { color: var(--c-text); font-weight: 600; }
.selector-status-meta { margin-left: auto; color: var(--c-text-tertiary); font-size: 11.5px; font-weight: 500; }
@media (max-width: 480px) { .selector-grid.compact { grid-template-columns: 1fr; } }
</style>
