import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'
import History from '../views/History.vue'
import Home from '../views/Home.vue'
import Login from '../views/Login.vue'
import Practice from '../views/Practice.vue'
import Report from '../views/Report.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: Login },
    { path: '/', component: Home },
    { path: '/practice', component: Practice },
    { path: '/report/:id', component: Report },
    { path: '/history', component: History },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.path !== '/login' && !auth.token) return '/login'
  if (to.path === '/login' && auth.token) return '/'
})

export default router
