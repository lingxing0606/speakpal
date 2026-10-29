<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import api from '../api/client'
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

const storage = ref({ path: '', exists: null, size_bytes: null, writable: null, error: '' })
const newPath = ref('')
const adminKey = ref('')
const copyExisting = ref(true)
const migrating = ref(false)
const migrateTip = ref({ ok: null, message: '' })

const confirming = ref(false)
const confirmWord = ref('')
const dataState = ref({ running: false, tip: '', error: '' })

const sizeText = computed(() => {
  const bytes = storage.value.size_bytes
  if (bytes === null || bytes === undefined) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
})

function errText(e) {
  return e?.response?.data?.detail || e.message || '未知错误'
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

async function loadStorage() {
  try {
    const { data } = await api.get('/system/storage')
    storage.value = { ...data, error: '' }
    if (!newPath.value) newPath.value = data.path || ''
  } catch (e) {
    storage.value = { ...storage.value, error: errText(e) }
  }
}

onMounted(() => {
  loadServerStatus()
  loadStorage()
})

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
      const why = data.error_kind === 'invalid_key' ? '密钥无效或被拒绝' : data.error_kind === 'unavailable' ? '服务不可达或超时' : '调用失败'
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

async function migrateStorage() {
  if (!adminKey.value.trim()) {
    migrateTip.value = { ok: false, message: '改数据目录需要管理密钥，请先填写' }
    return
  }
  migrating.value = true
  migrateTip.value = { ok: null, message: '正在处理…' }
  try {
    const { data } = await api.put('/admin/storage', {
      path: newPath.value.trim(),
      admin_key: adminKey.value.trim(),
      copy_existing: copyExisting.value,
    })
    migrateTip.value = {
      ok: true,
      message: `已写入 ${data.path || newPath.value}${data.copied_bytes ? `（复制了 ${Math.round(data.copied_bytes / 1024)} KB）` : ''}，重启后端后生效。`,
    }
    await loadStorage()
  } catch (e) {
    migrateTip.value = { ok: false, message: errText(e) }
    await loadStorage()
  } finally {
    migrating.value = false
  }
}

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <header class="border-b border-slate-200 bg-white">
      <div class="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
        <div class="text-lg font-bold">设置</div>
        <div class="flex items-center gap-3 text-sm">
          <router-link to="/" class="text-indigo-600 hover:underline">返回首页</router-link>
          <button class="text-slate-500 hover:text-slate-800" @click="logout">退出</button>
        </div>
      </div>
    </header>

    <main class="mx-auto max-w-3xl space-y-5 px-4 py-8">
      <p v-if="onboarding" class="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800 ring-1 ring-amber-200">
        配一下你自己的模型密钥，之后每次练习都用它调用评分模型。没有密钥也可以先跳过，用服务端的兜底密钥。
        <button class="ml-2 font-medium underline" @click="router.push('/')">先跳过</button>
      </p>

      <section class="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <h2 class="font-semibold text-slate-900">模型密钥</h2>
        <p class="mt-1 text-xs leading-5 text-slate-500">
          密钥只存在本浏览器（localStorage），每次请求随请求头发送，服务端不写数据库、不写日志。
          服务端 <code>backend/.env</code> 的密钥作为兜底，优先级「本浏览器 &gt; .env」。
        </p>

        <div class="mt-4 space-y-3">
          <label class="block text-sm">
            <span class="text-slate-600">API Key</span>
            <input
              v-model="keyInput"
              type="password"
              autocomplete="off"
              placeholder="sk-…（DeepSeek 控制台获取）"
              class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm"
            />
          </label>

          <div class="grid gap-3 sm:grid-cols-2">
            <label class="block text-sm">
              <span class="text-slate-600">Base URL（可留空用默认）</span>
              <input
                v-model="baseInput"
                placeholder="https://api.deepseek.com/v1"
                class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </label>
            <label class="block text-sm">
              <span class="text-slate-600">模型（可留空用默认）</span>
              <input
                v-model="modelInput"
                placeholder="deepseek-chat"
                class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </label>
          </div>

          <div class="flex flex-wrap items-center gap-2 text-sm">
            <button
              class="rounded-lg bg-indigo-600 px-3 py-1.5 text-white disabled:opacity-60"
              :disabled="!keyInput.trim()"
              @click="saveKey"
            >
              保存
            </button>
            <button
              class="rounded-lg border border-slate-300 px-3 py-1.5 text-slate-700 disabled:opacity-60"
              :disabled="testState.running || !keyInput.trim()"
              @click="testKey"
            >
              {{ testState.running ? '测试中…' : '测试连接' }}
            </button>
            <button v-if="settings.configured" class="text-slate-500 hover:text-rose-600" @click="clearKey">
              删除本浏览器密钥
            </button>
          </div>

          <p v-if="saveTip" class="text-xs text-emerald-600">{{ saveTip }}</p>
          <p v-if="testState.message" :class="testState.ok === false ? 'text-xs text-rose-600' : 'text-xs text-slate-600'">
            {{ testState.message }}
          </p>
          <p class="text-xs text-slate-400">
            当前：{{ settings.configured ? `已配置（${settings.masked}）` : '本浏览器未配置' }}
            <span v-if="server.env_configured === true">· 服务端已配置兜底密钥</span>
            <span v-else-if="server.env_configured === false">· 服务端未配置兜底密钥</span>
            <span v-if="server.error">· 读取服务端状态失败：{{ server.error }}</span>
          </p>
        </div>
      </section>

      <section class="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <h2 class="font-semibold text-slate-900">我的数据</h2>
        <p class="mt-1 text-xs leading-5 text-slate-500">
          只删除你自己的练习记录和报告，账号保留，别人的数据不受影响。删除后不可恢复。
        </p>
        <div class="mt-4 space-y-2 text-sm">
          <button
            v-if="!confirming"
            class="rounded-lg border border-rose-300 px-3 py-1.5 text-rose-600 disabled:opacity-60"
            :disabled="dataState.running"
            @click="confirming = true"
          >
            清除我的练习数据
          </button>
          <template v-else>
            <p class="text-slate-600">确认删除你的全部练习记录与报告？输入「删除」两个字再点确认。</p>
            <div class="flex flex-wrap items-center gap-2">
              <input
                v-model="confirmWord"
                placeholder="删除"
                class="w-24 rounded-lg border border-slate-200 px-3 py-1.5"
              />
              <button
                class="rounded-lg bg-rose-600 px-3 py-1.5 text-white disabled:opacity-60"
                :disabled="dataState.running"
                @click="clearData"
              >
                {{ dataState.running ? '删除中…' : '确认删除' }}
              </button>
              <button class="text-slate-500 hover:text-slate-800" @click="confirming = false; confirmWord = ''">取消</button>
            </div>
          </template>
        </div>
        <p v-if="dataState.tip" class="mt-3 text-xs text-emerald-600">{{ dataState.tip }}</p>
        <p v-if="dataState.error" class="mt-3 text-xs text-rose-600">{{ dataState.error }}</p>
      </section>

      <section class="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <h2 class="font-semibold text-slate-900">数据存储位置</h2>
        <p class="mt-1 text-xs leading-5 text-slate-500">
          练习记录、报告、账号都在这一个 SQLite 文件里。改位置需要管理密钥，写入后<b>重启后端生效</b>，
          原库文件不会被删除。
        </p>

        <dl class="mt-4 space-y-2 text-sm">
          <div class="flex gap-2">
            <dt class="w-20 shrink-0 text-slate-500">当前路径</dt>
            <dd class="break-all font-mono text-xs text-slate-800">{{ storage.path || '—' }}</dd>
          </div>
          <div class="flex gap-2">
            <dt class="w-20 shrink-0 text-slate-500">文件大小</dt>
            <dd class="text-slate-800">{{ sizeText }}</dd>
          </div>
          <div class="flex gap-2">
            <dt class="w-20 shrink-0 text-slate-500">状态</dt>
            <dd class="text-slate-800">
              {{ storage.exists === true ? '存在' : storage.exists === false ? '不存在（首次启动时创建）' : '—' }}
              <span v-if="storage.writable === false" class="text-rose-600">· 目录不可写</span>
            </dd>
          </div>
        </dl>

        <div class="mt-4 space-y-2">
          <label class="block text-sm">
            <span class="text-slate-600">迁移到（目录或 .db 文件路径）</span>
            <input
              v-model="newPath"
              placeholder="D:\SpeakPalData\speakpal.db"
              class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-xs"
            />
          </label>
          <label class="block text-sm">
            <span class="text-slate-600">管理密钥（ADMIN_KEY）</span>
            <input
              v-model="adminKey"
              type="password"
              autocomplete="off"
              class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm"
            />
          </label>
          <label class="flex items-center gap-2 text-xs text-slate-600">
            <input v-model="copyExisting" type="checkbox" />
            把现有数据复制到新位置（推荐；失败可回滚）
          </label>
          <button
            class="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-60"
            :disabled="migrating || !newPath.trim()"
            @click="migrateStorage"
          >
            {{ migrating ? '处理中…' : '写入新位置（重启后生效）' }}
          </button>
          <p v-if="migrateTip.message" :class="migrateTip.ok === false ? 'text-xs text-rose-600' : 'text-xs text-emerald-600'">
            {{ migrateTip.message }}
          </p>
          <p v-if="storage.error" class="text-xs text-rose-600">读取存储信息失败：{{ storage.error }}</p>
        </div>
      </section>
    </main>
  </div>
</template>
