<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

import api, { endStartupProbe } from './api/client'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const router = useRouter()

// 刷新页面时用 /auth/me 校准本地用户：账号被删、改密被踢之后，别继续显示旧昵称。
// 探测带 skipAuthRedirect，且在结束时放开拦截器的硬跳闸：这里失败是「本地 token 对不上现在的库」，
// 要按原因回到登录页，由用户重新登录或注册。
onMounted(async () => {
  if (!auth.token) {
    endStartupProbe()
    return
  }
  try {
    // 探测带超时：后端没起来时不能把 startupProbePending 一直挂着，否则全站 401 都被静默吞掉
    const { data } = await api.get('/auth/me', { skipAuthRedirect: true, timeout: 5000 })
    auth.setAuth(auth.token, data)
  } catch (e) {
    if (e?.response?.status === 401) {
      const reason = e?.response?.headers?.['x-auth-reason'] || ''
      const here = `${window.location.pathname}${window.location.search}`
      auth.logout({ clearKey: false })
      if (reason === 'password_changed' || reason === 'token_invalid' || reason === 'expired') {
        // 被改密/凭证失效要有明确原因，别让人以为账号没了
        router.push(`/login?reason=${encodeURIComponent(reason)}&next=${encodeURIComponent(here)}`)
      } else if (reason === 'user_gone') {
        // 账号已注销：去登录页并说明原因，注册新号就能继续
        router.push('/login?reason=user_gone')
      } else {
        // 没有原因（老 token / 后端刚清库）：回登录页重新登录，不要把用户丢到空白页
        router.push('/login')
      }
    }
    // 纯网络问题就先用本地缓存渲染，不打扰用户
  } finally {
    endStartupProbe()
  }
})
</script>

<template>
  <router-view />
</template>
