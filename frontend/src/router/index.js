import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'
import History from '../views/History.vue'
import Home from '../views/Home.vue'
import Login from '../views/Login.vue'
import Practice from '../views/Practice.vue'
import Pronunciation from '../views/Pronunciation.vue'
import Report from '../views/Report.vue'
import Settings from '../views/Settings.vue'
import Welcome from '../views/Welcome.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: Login },
    { path: '/welcome', component: Welcome },
    { path: '/', component: Home },
    { path: '/practice', component: Practice },
    { path: '/practice/:id', component: Practice },
    { path: '/report/:id', component: Report },
    { path: '/history', component: History },
    { path: '/pronunciation', component: Pronunciation },
    { path: '/settings', component: Settings },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  const isPublic = to.path === '/login' || to.path === '/welcome'
  // 没登录不要直接怼到登录页：先让新来的人看一遍欢迎页（介绍这是什么、怎么用）
  if (!isPublic && !auth.token) return '/welcome'
  if (to.path === '/login' && auth.token) return '/'
  // 新手引导每个账号只跑一次：记号存的是「看过引导的用户名」；
  // 旧版本的全局 '1' 没有用户名，当作「未知」放行一次，让老账号也能看一遍
  if (to.path === '/welcome' && auth.token && to.query.again !== '1') {
    const mark = localStorage.getItem('sp_welcomed') || ''
    const current = auth.user?.username || ''
    if (!!mark && mark !== '1' && mark === current) return '/'
  }
})

export default router
