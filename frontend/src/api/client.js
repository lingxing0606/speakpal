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
      const here = `${window.location.pathname}${window.location.search}`
      if (window.location.pathname !== '/login') {
        // 带上原因和原地址：登录后能回到刚才那一页，而不是把「接着练」变成空话
        window.location.href = `/login?expired=1&next=${encodeURIComponent(here)}`
      }
    }
    return Promise.reject(error)
  }
)

export default api
