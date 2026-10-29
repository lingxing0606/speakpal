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
      auth.logout({ clearKey: false })
      const here = `${window.location.pathname}${window.location.search}`
      const data = error?.response?.data || {}
      const detail = typeof data.detail === 'string' ? data.detail : ''
      // 后端在 401 响应头给权威原因码（X-Auth-Reason），body 里的 reason/kind 和文案只作兜底
      const headerReason = error?.response?.headers?.['x-auth-reason']
      const reason =
        headerReason ||
        data.reason ||
        data.kind ||
        (detail.includes('密码已修改')
          ? 'password_changed'
          : detail.includes('已注销')
            ? 'user_gone'
            : 'expired')
      if (window.location.pathname !== '/login') {
        // 带上原因和原地址：登录后能回到刚才那一页，而不是把「接着练」变成空话
        window.location.href = `/login?reason=${encodeURIComponent(reason)}&next=${encodeURIComponent(here)}`
      }
    }
    return Promise.reject(error)
  }
)

export default api
