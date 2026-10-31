import axios from 'axios'

import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'

const api = axios.create({ baseURL: '/api' })

// 启动探测（App.vue 的 /auth/me）还没结束时，拦截器不抢跳登录页：
// 否则首页同时发出的 /scenes 等请求先 401，会把本该落到欢迎页的首屏顶成登录页
let startupProbePending = true

export function endStartupProbe() {
  startupProbePending = false
}

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
      const hadToken = !!auth.token
      auth.logout({ clearKey: false })
      // 启动探测期间，或本来就没有登录态：交给路由守卫决定去欢迎页还是登录页，别硬跳
      if (startupProbePending || !hadToken) return Promise.reject(error)
      const here = `${window.location.pathname}${window.location.search}`
      // 启动时的 /auth/me 探测用 skipAuthRedirect 标记：它失败说明本地 token 过期，
      // 调用方自己会清干净并回欢迎页。拦在这里抢跳登录页，会把首屏的欢迎页顶掉。
      if (error?.config?.skipAuthRedirect) return Promise.reject(error)
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
