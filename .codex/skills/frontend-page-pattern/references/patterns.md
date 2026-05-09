# Frontend Patterns Reference

## Existing Layout

- Views: `frontend/src/views/*.vue`
- API client modules: `frontend/src/api/*.ts`
- Pinia stores: `frontend/src/stores/*.ts`
- Router: `frontend/src/router/index.ts`

## Recommended File Mapping

- New page: `frontend/src/views/<PageName>.vue`
- Page-specific API calls: `frontend/src/api/<domain>.ts`
- Shared page state: `frontend/src/stores/<domain>.ts`

## Minimum Build Gate

- `cd frontend && npm run build`

## Route Pattern

```ts
{ path: '/path', name: 'route-name', component: () => import('../views/Page.vue') }
```

## API Module Pattern

```ts
import { api } from './index'

export interface Item {
  id: number
  title: string
}

export async function listItems(): Promise<Item[]> {
  const { data } = await api.get<Item[]>('/items')
  return data
}
```

## Store Pattern

```ts
import { defineStore } from 'pinia'

export const useXStore = defineStore('x', {
  state: () => ({
    loading: false
  }),
  actions: {
    async refresh() {
      this.loading = true
      try {
        // call API
      } finally {
        this.loading = false
      }
    }
  }
})
```