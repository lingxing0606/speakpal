import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'
import Home from '../views/Home.vue'
import Login from '../views/Login.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: Login },
    { path: '/', component: Home },
    { path: '/practice', component: () => import('../views/Practice.vue') },
    { path: '/practice/:id', component: () => import('../views/Practice.vue') },
    { path: '/report/:id', component: () => import('../views/Report.vue') },
    { path: '/history', component: () => import('../views/History.vue') },
    { path: '/review', component: () => import('../views/Review.vue') },
    { path: '/study', component: () => import('../views/StudyHome.vue') },
    { path: '/study/:scope/learn', component: () => import('../views/StudyLearn.vue') },
    { path: '/study/:scope', component: () => import('../views/StudyScope.vue') },
    { path: '/notes', component: () => import('../views/Notes.vue') },
    { path: '/pronunciation', component: () => import('../views/Pronunciation.vue') },
    { path: '/settings', component: () => import('../views/Settings.vue') },
    // 旧书签（比如 /welcome）和手误地址不再落到白屏，统一回首页；未登录会被下面的守卫送去登录页
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

// 部署更新后旧 chunk 失效：自动重载一次；5 分钟内再失败才让页面提示「需要更新」
const CHUNK_RELOAD_AT = 'sp_chunk_reload_at'
const CHUNK_RELOAD_TO = 'sp_chunk_reload_to'
const CHUNK_RELOAD_WINDOW = 5 * 60 * 1000
const CHUNK_ERROR_RE = /Failed to fetch dynamically imported module|Loading chunk .* failed|Importing a module script failed/i

router.onError((error) => {
  if (!CHUNK_ERROR_RE.test(String(error?.message || ''))) return
  const now = Date.now()
  let last = 0
  try {
    last = Number(sessionStorage.getItem(CHUNK_RELOAD_AT) || 0)
  } catch {
    // 隐私模式读不到 sessionStorage 就当第一次
  }
  if (last && now - last < CHUNK_RELOAD_WINDOW) {
    window.dispatchEvent(new CustomEvent('sp:fatal', { detail: { reason: 'stale' } }))
    return
  }
  try {
    sessionStorage.setItem(CHUNK_RELOAD_AT, String(now))
    sessionStorage.setItem(CHUNK_RELOAD_TO, `${window.location.pathname}${window.location.search}`)
  } catch {
    // 存不下也照样重载：reload 本身会停在原地址
  }
  window.location.reload()
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
