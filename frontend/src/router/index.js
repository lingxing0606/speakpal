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
  // 新手引导只跑一次：看过就回首页；从设置点「再看一遍」时带 ?again=1 放行
  if (to.path === '/welcome' && localStorage.getItem('sp_welcomed') === '1' && to.query.again !== '1') return '/'
})

export default router
