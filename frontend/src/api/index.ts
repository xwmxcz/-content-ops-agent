import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
  timeout: 120000
})

api.interceptors.response.use(
  response => response,
  error => {
    const detail = error.response?.data?.detail
    const message = typeof detail === 'string' ? detail : detail?.message ?? error.message
    return Promise.reject(new Error(message))
  }
)
