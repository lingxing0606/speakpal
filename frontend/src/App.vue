<script setup>
import { onMounted } from 'vue'

import api from './api/client'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()

// 刷新页面时用 /auth/me 校准本地用户：账号被删、改密被踢之后，别继续显示旧昵称
onMounted(async () => {
  if (!auth.token) return
  try {
    const { data } = await api.get('/auth/me')
    auth.setAuth(auth.token, data)
  } catch {
    // 401 由拦截器统一踢回登录页；纯网络问题就先用本地缓存渲染
  }
})
</script>

<template>
  <router-view />
</template>
