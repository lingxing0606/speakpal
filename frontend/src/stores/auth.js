import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

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

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('sp_token')
    localStorage.removeItem('sp_user')
  }

  return { token, user, isLoggedIn, setAuth, logout }
})
