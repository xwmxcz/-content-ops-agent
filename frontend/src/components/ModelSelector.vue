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
        <span title="值越高，表达越多样">创意程度</span>
        <el-slider v-model="local.temperature" :min="0" :max="1" :step="0.1" />
      </div>

      <div class="selector-field">
        <span title="单次模型回复的最大 token 数">输出上限</span>
        <el-input-number v-model="local.max_tokens" :min="128" :max="8192" :step="256" />
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
.model-selector { display: grid; gap: 16px; min-width: 0; }
.selector-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; }
.selector-grid.compact { align-items: start; }
.selector-field { display: grid; gap: 8px; min-width: 0; align-content: start; }
.selector-field > span { color: var(--c-text-secondary); font-size: 11px; font-weight: 500; }
.selector-field .selector-field-caption { font-family: var(--font-mono); font-size: 10px; font-weight: 400; color: var(--c-text-tertiary); overflow-wrap: anywhere; line-height: 1.5; }
.selector-status { display: flex; align-items: center; gap: 7px; padding: 0; font-size: 11px; }
.selector-status-dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
.selector-status-dot.ready { background: var(--c-ok); }
.selector-status-dot.warn { background: var(--c-warn); }
.selector-status-text { color: var(--c-text-secondary); }
.selector-status-meta { margin-left: auto; color: var(--c-text-tertiary); font-size: 10px; }
@media (max-width: 480px) { .selector-grid { grid-template-columns: 1fr; } .selector-grid.compact { grid-template-columns: 1fr 1fr; } }
</style>
