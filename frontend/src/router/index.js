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
  if (to.path !== '/login' && !auth.token) return '/login'
  if (to.path === '/login' && auth.token) return '/'
  // 新手引导每个账号只跑一次：记号存的是「看过引导的用户名」，
  // 这样同一台机器换个新账号注册，仍然能看到引导；从设置点「再看一遍」带 ?again=1 放行
  if (to.path === '/welcome' && to.query.again !== '1') {
    const mark = localStorage.getItem('sp_welcomed') || ''
    const current = auth.user?.username || ''
    // '1' 是旧版浏览器的记号，没有用户名，按「看过」处理
    if (mark === '1' || (!!mark && mark === current)) return '/'
  }
})

export default router
