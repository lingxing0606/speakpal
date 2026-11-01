import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'
import History from '../views/History.vue'
import Home from '../views/Home.vue'
import Login from '../views/Login.vue'
import Notes from '../views/Notes.vue'
import Practice from '../views/Practice.vue'
import Pronunciation from '../views/Pronunciation.vue'
import Report from '../views/Report.vue'
import Settings from '../views/Settings.vue'
import Study from '../views/Study.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: Login },
    { path: '/', component: Home },
    { path: '/practice', component: Practice },
    { path: '/practice/:id', component: Practice },
    { path: '/report/:id', component: Report },
    { path: '/history', component: History },
    { path: '/study', component: Study },
    { path: '/notes', component: Notes },
    { path: '/pronunciation', component: Pronunciation },
    { path: '/settings', component: Settings },
    // 旧书签（比如 /welcome）和手误地址不再落到白屏，统一回首页；未登录会被下面的守卫送去登录页
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  // 登录页是唯一公开页：没登录时去任何地址都先登录，登录成功后回到原来那一页
  if (to.path !== '/login' && !auth.token) {
    return { path: '/login', query: to.path === '/' ? {} : { next: to.fullPath } }
  }
  if (to.path === '/login' && auth.token) return '/'
})

export default router
