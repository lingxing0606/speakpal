import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { clearRecordings } from '../utils/recordings'
import { useSettingsStore } from './settings'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('sp_token') || '')
  const user = ref(JSON.parse(localStorage.getItem('sp_user') || 'null'))

  const isLoggedIn = computed(() => !!token.value)

  function setAuth(newToken, newUser) {
    token.value = newToken
    user.value = newUser
    localStorage.setItem('sp_token', newToken)
    localStorage.setItem('sp_user', JSON.stringify(newUser))
  }

  function logout({ clearKey = true } = {}) {
    token.value = ''
    user.value = null
    localStorage.removeItem('sp_token')
    localStorage.removeItem('sp_user')
    // 主动退出：连本浏览器的模型密钥一起清掉，换账号登录时不会把上一个人的 key 带出去。
    // 被 401 踢下线时传 { clearKey: false }：用户没说要换账号，不该顺手删掉他的密钥。
    if (!clearKey) return
    // 主动退出：本浏览器里的录音一起清，换人用这台电脑听不到上一个人的声音
    clearRecordings()
    try {
      useSettingsStore().clear()
    } catch {
      localStorage.removeItem('sp_llm')
    }
  }

  return { token, user, isLoggedIn, setAuth, logout }
})
