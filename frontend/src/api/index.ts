import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
  timeout: 120000
})

api.interceptors.response.use(
  response => response,
  error => {
    const detail = error.response?.data?.detail
    return Promise.reject(new Error(typeof detail === 'string' ? detail : error.message))
  }
)
