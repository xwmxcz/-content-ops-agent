<template>
  <div class="model-selector">
    <el-form label-position="top">
      <el-form-item label="模型提供商">
        <el-select v-model="local.provider" placeholder="选择提供商" @change="onProviderChange">
          <el-option
            v-for="provider in providers"
            :key="provider.id"
            :label="`${provider.name}${provider.configured ? '' : '（未配置）'}`"
            :value="provider.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="模型">
        <el-select v-model="local.model" placeholder="选择模型">
          <el-option v-for="model in activeModels" :key="model.id" :label="model.name" :value="model.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="Temperature">
        <el-slider v-model="local.temperature" :min="0" :max="1" :step="0.1" />
      </el-form-item>
      <el-form-item label="Max Tokens">
        <el-input-number v-model="local.max_tokens" :min="128" :max="8192" :step="256" />
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, watch } from 'vue'
import { getModels, type ProviderInfo } from '../api/content'

const props = defineProps<{
  modelValue: {
    provider?: string
    model?: string
    temperature: number
    max_tokens: number
  }
}>()

const emit = defineEmits<{
  'update:modelValue': [value: typeof props.modelValue]
}>()

const providers = reactive<ProviderInfo[]>([])
const local = reactive({ ...props.modelValue })

const activeProvider = computed(() => providers.find(provider => provider.id === local.provider))
const activeModels = computed(() => activeProvider.value?.models ?? [])

function onProviderChange() {
  const defaultModel = activeProvider.value?.default_model
  const hasDefaultModel = activeModels.value.some(model => model.id === defaultModel)
  local.model = hasDefaultModel ? defaultModel : activeModels.value[0]?.id
}

watch(local, value => emit('update:modelValue', { ...value }), { deep: true })

onMounted(async () => {
  providers.splice(0, providers.length, ...(await getModels()))
  if (!local.provider) {
    local.provider = providers.find(provider => provider.configured)?.id ?? providers[0]?.id
  }
  if (!local.model) {
    const provider = providers.find(provider => provider.id === local.provider)
    const hasDefaultModel = provider?.models.some(model => model.id === provider.default_model)
    local.model = hasDefaultModel ? provider?.default_model : provider?.models[0]?.id
  }
})
</script>
