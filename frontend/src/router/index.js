import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'
import History from '../views/History.vue'
import Home from '../views/Home.vue'
import Login from '../views/Login.vue'
import Notes from '../views/Notes.vue'
import Practice from '../views/Practice.vue'
import Pronunciation from '../views/Pronunciation.vue'
import Report from '../views/Report.vue'
import Review from '../views/Review.vue'
import Settings from '../views/Settings.vue'
import StudyHome from '../views/StudyHome.vue'
import StudyLearn from '../views/StudyLearn.vue'
import StudyScope from '../views/StudyScope.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: Login },
    { path: '/', component: Home },
    { path: '/practice', component: Practice },
    { path: '/practice/:id', component: Practice },
    { path: '/report/:id', component: Report },
    { path: '/history', component: History },
    { path: '/review', component: Review },
    { path: '/study', component: StudyHome },
    { path: '/study/:scope/learn', component: StudyLearn },
    { path: '/study/:scope', component: StudyScope },
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

  // 旧学习页链接：复习独立成页，其余 tab 落到上次范围（没有就四级）
  if (to.path === '/study' && to.query.tab) {
    const raw = Array.isArray(to.query.tab) ? to.query.tab[0] : to.query.tab
    const tab = raw === 'phrase' ? 'spoken' : raw
    if (tab === 'review') return { path: '/review' }
    if (tab === 'new' || tab === 'grammar' || tab === 'spoken') {
      const scope = useSettingsStore().wordScope || 'cet4'
      return { path: `/study/${scope}`, query: { tab } }
    }
  }
})

export default router
