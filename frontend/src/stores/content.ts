import { defineStore } from 'pinia'
import { getContents, type ContentItem } from '../api/content'

export const useContentStore = defineStore('content', {
  state: () => ({
    items: [] as ContentItem[],
    loading: false
  }),
  actions: {
    async refresh(limit = 20) {
      this.loading = true
      try {
        this.items = await getContents({ limit })
      } finally {
        this.loading = false
      }
    }
  }
})
