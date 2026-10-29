<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import api from '../api/client'
import BrandLogo from '../components/BrandLogo.vue'
import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const settings = useSettingsStore()

const onboarding = computed(() => route.query.onboarding === '1')

const keyInput = ref(settings.apiKey)
const baseInput = ref(settings.baseUrl)
const modelInput = ref(settings.model)
const server = ref({ env_configured: null, error: '' })
const saveTip = ref('')
const testState = ref({ running: false, ok: null, message: '' })

const nicknameInput = ref(auth.user?.nickname || '')
const profileState = ref({ running: false, tip: '', error: '' })
const pwd = ref({ current: '', next: '', confirm: '' })
const pwdState = ref({ running: false, tip: '', error: '' })

const confirming = ref(false)
const confirmWord = ref('')
const dataState = ref({ running: false, tip: '', error: '' })

const accountOpen = ref(false)
const accountWord = ref('')
const accountState = ref({ running: false, error: '' })

function errText(e) {
  const detail = e?.response?.data?.detail
  // FastAPI 校验错误是数组，别把整段英文 JSON 甩给用户
  if (Array.isArray(detail)) {
    const first = detail[0]
    return first?.msg ? `输入格式不对：${first.msg}` : '输入格式不对，检查一下再提交'
  }
  return detail || e?.message || '未知错误'
}

async function loadServerStatus() {
  try {
    const { data } = await api.get('/config/llm')
    server.value = { env_configured: data?.env_configured ?? null, error: '' }
    if (!modelInput.value && data?.default_model) modelInput.value = data.default_model
    if (!baseInput.value && data?.default_base_url) baseInput.value = data.default_base_url
  } catch (e) {
    server.value = { env_configured: null, error: errText(e) }
  }
}

onMounted(loadServerStatus)

function saveKey() {
  settings.save({ apiKey: keyInput.value, baseUrl: baseInput.value, model: modelInput.value })
  saveTip.value = '已保存到本浏览器。'
  if (onboarding.value && settings.configured) router.push('/')
}

async function testKey() {
  testState.value = { running: true, ok: null, message: '正在发一次最小请求…' }
  settings.save({ apiKey: keyInput.value, baseUrl: baseInput.value, model: modelInput.value })
  try {
    const { data } = await api.post('/config/llm/test', {})
    if (data.ok) {
      testState.value = { running: false, ok: true, message: `连通 · 模型 ${data.model || '—'} · ${data.latency_ms ?? '—'} ms` }
    } else {
      const labels = {
        invalid_key: '密钥无效或被拒绝',
        timeout: '请求超时',
        unreachable: '服务不可达',
      }
      const why = labels[data.error_kind] || '调用失败'
      testState.value = { running: false, ok: false, message: `${why}${data.error ? '：' + data.error : ''}` }
    }
  } catch (e) {
    testState.value = { running: false, ok: false, message: errText(e) }
  }
}

function clearKey() {
  settings.clear()
  keyInput.value = ''
  baseInput.value = ''
  modelInput.value = ''
  saveTip.value = '已从本浏览器删除。'
}

async function saveNickname() {
  const nickname = nicknameInput.value.trim()
  profileState.value = { running: true, tip: '', error: '' }
  if (!nickname) {
    profileState.value = { running: false, tip: '', error: '昵称不能为空' }
    return
  }
  try {
    const { data } = await api.patch('/me/profile', { nickname })
    auth.setAuth(auth.token, { ...(auth.user || {}), ...data })
    nicknameInput.value = data?.nickname || nickname
    profileState.value = { running: false, tip: '昵称已更新。', error: '' }
  } catch (e) {
    profileState.value = { running: false, tip: '', error: errText(e) }
  }
}

async function changePassword() {
  pwdState.value = { running: true, tip: '', error: '' }
  if (!pwd.value.current) {
    pwdState.value = { running: false, tip: '', error: '请先填当前密码' }
    return
  }
  if (pwd.value.next.length < 4 || pwd.value.next.length > 64) {
    pwdState.value = { running: false, tip: '', error: '新密码要 4–64 位' }
    return
  }
  if (pwd.value.next !== pwd.value.confirm) {
    pwdState.value = { running: false, tip: '', error: '两次输入的新密码不一致' }
    return
  }
  try {
    await api.patch('/me/profile', {
      password: pwd.value.next,
      current_password: pwd.value.current,
    })
    pwd.value = { current: '', next: '', confirm: '' }
    pwdState.value = { running: false, tip: '密码已更新，下次登录用新密码。', error: '' }
  } catch (e) {
    pwdState.value = { running: false, tip: '', error: errText(e) }
  }
}

async function clearData() {
  if (confirmWord.value.trim() !== '删除') {
    dataState.value = { running: false, tip: '', error: '请先输入「删除」两个字' }
    return
  }
  dataState.value = { running: true, tip: '', error: '' }
  try {
    const { data } = await api.delete('/me/data')
    dataState.value = {
      running: false,
      tip: `已删除 ${data.deleted_sessions ?? 0} 次练习、${data.deleted_reports ?? 0} 份报告。`,
      error: '',
    }
    confirming.value = false
    confirmWord.value = ''
  } catch (e) {
    dataState.value = { running: false, tip: '', error: errText(e) }
  }
}

async function deleteAccount() {
  if (accountWord.value.trim() !== '注销') {
    accountState.value = { running: false, error: '请先输入「注销」两个字' }
    return
  }
  accountState.value = { running: true, error: '' }
  try {
    await api.delete('/me/account', { data: { confirm: accountWord.value.trim() } })
    settings.clear()
    auth.logout()
    router.push('/login')
  } catch (e) {
    accountState.value = { running: false, error: errText(e) }
  }
}

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-canvas">
    <header class="sp-header">
      <div class="sp-shell flex items-center justify-between py-3">
        <div class="flex items-center gap-3">
          <router-link to="/" aria-label="返回首页">
            <BrandLogo :size="30" />
          </router-link>
          <span class="h-4 w-px bg-line"></span>
          <div class="font-semibold text-ink">设置</div>
        </div>
        <div class="flex items-center gap-1">
          <router-link to="/" class="sp-btn-ghost">返回首页</router-link>
          <button class="sp-btn-ghost" @click="logout">退出</button>
        </div>
      </div>
    </header>

    <main class="sp-shell space-y-5 py-8">
      <p v-if="onboarding" class="sp-alert-warn">
        配一下你自己的模型密钥，之后每次练习都用它调用评分模型。没有密钥也可以先跳过，用服务端的兜底密钥。
        <button class="ml-2 font-medium underline" @click="router.push('/')">先跳过</button>
      </p>

      <section class="sp-card p-6">
        <h2 class="font-semibold text-ink">个人资料</h2>
        <p class="mt-1 text-xs leading-5 text-ink-soft">
          昵称只影响显示，不影响登录账号<span v-if="auth.user?.username">（{{ auth.user.username }}）</span>。
        </p>

        <div class="mt-4 flex flex-wrap items-end gap-2">
          <label class="min-w-0 flex-1 text-sm">
            <span class="mb-1.5 block text-xs font-medium text-ink-mute">昵称</span>
            <input v-model="nicknameInput" class="sp-input" placeholder="昵称" maxlength="32" />
          </label>
          <button class="sp-btn-primary" :disabled="profileState.running" @click="saveNickname">保存昵称</button>
        </div>
        <p v-if="profileState.tip" class="mt-2 text-xs text-good">{{ profileState.tip }}</p>
        <p v-if="profileState.error" class="mt-2 text-xs text-danger">{{ profileState.error }}</p>

        <div class="mt-6 border-t border-line pt-5">
          <div class="text-sm font-medium text-ink">修改密码</div>
          <div class="mt-3 grid gap-3 sm:grid-cols-3">
            <label class="block text-sm">
              <span class="mb-1.5 block text-xs font-medium text-ink-mute">当前密码</span>
              <input v-model="pwd.current" type="password" autocomplete="current-password" class="sp-input" />
            </label>
            <label class="block text-sm">
              <span class="mb-1.5 block text-xs font-medium text-ink-mute">新密码</span>
              <input v-model="pwd.next" type="password" autocomplete="new-password" class="sp-input" placeholder="4–64 位" />
            </label>
            <label class="block text-sm">
              <span class="mb-1.5 block text-xs font-medium text-ink-mute">再输一次</span>
              <input v-model="pwd.confirm" type="password" autocomplete="new-password" class="sp-input" />
            </label>
          </div>
          <div class="mt-3 flex items-center gap-3">
            <button class="sp-btn-secondary" :disabled="pwdState.running" @click="changePassword">
              {{ pwdState.running ? '提交中…' : '修改密码' }}
            </button>
            <span class="text-xs text-ink-mute">改完密码，其他设备上的登录不会掉线。</span>
          </div>
          <p v-if="pwdState.tip" class="mt-2 text-xs text-good">{{ pwdState.tip }}</p>
          <p v-if="pwdState.error" class="mt-2 text-xs text-danger">{{ pwdState.error }}</p>
        </div>
      </section>

      <section class="sp-card p-6">
        <h2 class="font-semibold text-ink">模型密钥</h2>
        <p class="mt-1 text-xs leading-5 text-ink-soft">
          不填也能练：服务端配了兜底密钥时就用它；填了就优先用你自己的，且只存在这个浏览器里，不上传、不写数据库、不写日志。
        </p>

        <div class="mt-4 space-y-3">
          <label class="block text-sm">
            <span class="mb-1.5 block text-xs font-medium text-ink-mute">API Key</span>
            <input
              v-model="keyInput"
              type="password"
              autocomplete="off"
              placeholder="sk-…（DeepSeek 控制台获取）"
              class="sp-input font-mono"
            />
          </label>

          <div class="grid gap-3 sm:grid-cols-2">
            <label class="block text-sm">
              <span class="mb-1.5 block text-xs font-medium text-ink-mute">Base URL（可留空用默认）</span>
              <input v-model="baseInput" placeholder="https://api.deepseek.com/v1" class="sp-input" />
            </label>
            <label class="block text-sm">
              <span class="mb-1.5 block text-xs font-medium text-ink-mute">模型（可留空用默认）</span>
              <input v-model="modelInput" placeholder="deepseek-chat" class="sp-input" />
            </label>
          </div>

          <div class="flex flex-wrap items-center gap-2">
            <button class="sp-btn-primary" :disabled="!keyInput.trim()" @click="saveKey">保存</button>
            <button class="sp-btn-secondary" :disabled="testState.running || !keyInput.trim()" @click="testKey">
              {{ testState.running ? '测试中…' : '测试连接' }}
            </button>
            <button v-if="settings.configured" class="sp-btn-ghost text-danger hover:bg-rose-50" @click="clearKey">
              删除本浏览器密钥
            </button>
          </div>

          <p v-if="saveTip" class="text-xs text-good">{{ saveTip }}</p>
          <p
            v-if="testState.message"
            class="text-xs"
            :class="testState.ok === false ? 'text-danger' : 'text-ink-soft'"
          >
            {{ testState.message }}
          </p>
          <p class="text-xs leading-5 text-ink-mute">
            当前：{{ settings.configured ? `已配置（${settings.masked}）` : '本浏览器未配置' }}
            <span v-if="server.env_configured === true">· 服务端已配置兜底密钥</span>
            <span v-else-if="server.env_configured === false">· 服务端未配置兜底密钥</span>
            <span v-if="server.error">· 读取服务端状态失败：{{ server.error }}</span>
          </p>
        </div>
      </section>

      <section class="sp-card p-6">
        <h2 class="font-semibold text-ink">我的数据</h2>
        <p class="mt-1 text-xs leading-5 text-ink-soft">
          只删除你自己的练习记录和报告，账号保留，别人的数据不受影响。删除后不可恢复。
        </p>
        <div class="mt-4 space-y-2 text-sm">
          <button v-if="!confirming" class="sp-btn-secondary text-danger hover:ring-rose-300" :disabled="dataState.running" @click="confirming = true">
            清除我的练习数据
          </button>
          <template v-else>
            <p class="text-ink-soft">确认删除你的全部练习记录与报告？输入「删除」两个字再点确认。</p>
            <div class="flex flex-wrap items-center gap-2">
              <input v-model="confirmWord" placeholder="删除" class="sp-input w-24" />
              <button class="sp-btn bg-danger text-white hover:bg-rose-700" :disabled="dataState.running" @click="clearData">
                {{ dataState.running ? '删除中…' : '确认删除' }}
              </button>
              <button class="sp-btn-ghost" @click="confirming = false; confirmWord = ''">取消</button>
            </div>
          </template>
        </div>
        <p v-if="dataState.tip" class="mt-3 text-xs text-good">{{ dataState.tip }}</p>
        <p v-if="dataState.error" class="mt-3 text-xs text-danger">{{ dataState.error }}</p>
      </section>

      <section class="sp-card p-6">
        <h2 class="font-semibold text-ink">注销账号</h2>
        <p class="mt-1 text-xs leading-5 text-ink-soft">
          会删除账号本身，以及这个账号名下的全部练习记录、对话和报告，之后无法登录、无法恢复。
          只清记录不删账号的话，用上面那段。
        </p>
        <div class="mt-4 space-y-2 text-sm">
          <button v-if="!accountOpen" class="sp-btn-secondary text-danger hover:ring-rose-300" @click="accountOpen = true">
            注销我的账号
          </button>
          <template v-else>
            <p class="text-ink-soft">确认注销「{{ auth.user?.username || '当前账号' }}」？输入「注销」两个字再点确认。</p>
            <div class="flex flex-wrap items-center gap-2">
              <input v-model="accountWord" placeholder="注销" class="sp-input w-24" />
              <button class="sp-btn bg-danger text-white hover:bg-rose-700" :disabled="accountState.running" @click="deleteAccount">
                {{ accountState.running ? '注销中…' : '确认注销' }}
              </button>
              <button class="sp-btn-ghost" @click="accountOpen = false; accountWord = ''">取消</button>
            </div>
          </template>
          <p v-if="accountState.error" class="text-xs text-danger">{{ accountState.error }}</p>
        </div>
      </section>

      <p class="pb-4 text-center text-xs text-ink-mute">
        密钥只在你的浏览器里；练习数据按账号存在服务端，可以随时自己删掉。
      </p>
    </main>
  </div>
</template>
