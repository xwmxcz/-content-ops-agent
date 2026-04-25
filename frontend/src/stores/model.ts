import { defineStore } from 'pinia'
import { getModels, type ProviderInfo } from '../api/content'

export const useModelStore = defineStore('model', {
  state: () => ({
    providers: [] as ProviderInfo[],
    loading: false
  }),
  actions: {
    async refresh() {
      this.loading = true
      try {
        this.providers = await getModels()
      } finally {
        this.loading = false
      }
    }
  }
})
