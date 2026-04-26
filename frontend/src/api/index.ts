import axios from 'axios'

export class ApiError extends Error {
  status?: number
  detail: unknown

  constructor(message: string, status?: number, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export const api = axios.create({
  baseURL: '/api',
  timeout: 120000
})

api.interceptors.response.use(
  response => response,
  error => {
    const detail = error.response?.data?.detail
    const message = typeof detail === 'string' ? detail : detail?.message ?? error.message
    return Promise.reject(new ApiError(message, error.response?.status, detail))
  }
)
