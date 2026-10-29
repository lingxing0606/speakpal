import axios from 'axios'

import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'

const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  // 用户自己的模型密钥只随请求发一次，服务端不存储
  const settings = useSettingsStore()
  Object.assign(config.headers, settings.headers())
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      const auth = useAuthStore()
      auth.logout()
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api
