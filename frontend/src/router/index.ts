import { createRouter, createWebHistory } from 'vue-router'
import { getAuthStatus } from '../api/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('../views/Login.vue'), meta: { public: true } },
    { path: '/', name: 'studio', component: () => import('../views/Studio.vue') },
    { path: '/dashboard', name: 'dashboard', component: () => import('../views/Home.vue') },
    { path: '/generate', redirect: '/' },
    { path: '/refine', name: 'refine', component: () => import('../views/Refine.vue') },
    { path: '/pipeline', redirect: { path: '/', query: { mode: 'dynamic' } } },
    { path: '/calendar', name: 'calendar', component: () => import('../views/Calendar.vue') },
    { path: '/history', name: 'history', component: () => import('../views/History.vue') },
    { path: '/stats', name: 'stats', component: () => import('../views/Stats.vue') },
    { path: '/chat', name: 'chat', component: () => import('../views/Chat.vue') },
    { path: '/memory', name: 'memory', component: () => import('../views/Memory.vue') }
  ]
})

router.beforeEach(async to => {
  if (to.meta.public) return true

  try {
    const status = await getAuthStatus()
    if (!status.enabled || status.authenticated) return true
  } catch {
    return { path: '/login', query: { next: to.fullPath } }
  }

  return { path: '/login', query: { next: to.fullPath } }
})

export default router
