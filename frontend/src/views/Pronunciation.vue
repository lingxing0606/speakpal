<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import api from '../api/client'
import AppHeader from '../components/AppHeader.vue'
import { createRecognizer, speakSmart } from '../utils/speech'

const router = useRouter()

const sets = ref([])
const loading = ref(true)
const error = ref('')
const activeKey = ref('')
const listening = ref(false)
const heard = ref('')
const results = ref({})
let recognizer = null

onMounted(async () => {
  try {
    const { data } = await api.get('/pronunciation/minimal-pairs')
    sets.value = data?.sets || []
  } catch (e) {
    error.value = '加载发音对比词表失败：' + (e?.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(stopRec)

function keyOf(set, idx, side) {
  return `${set.id}:${idx}:${side}`
}

function say(word) {
  speakSmart(word, { rate: 0.9 })
}

function stopRec() {
  if (recognizer) {
    recognizer.abort?.()
    recognizer = null
  }
  listening.value = false
}

async function check(target, key) {
  try {
    const { data } = await api.post('/pronunciation/check', { target, heard: heard.value })
    results.value = { ...results.value, [key]: data }
  } catch (e) {
    error.value = '判定失败：' + (e?.response?.data?.detail || e.message)
  }
}

function startCheck(set, idx, side) {
  const pair = set.pairs[idx]
  const target = pair[side]
  const key = keyOf(set, idx, side)
  if (listening.value) {
    stopRec()
    if (activeKey.value === key) return
  }
  stopRec()
  error.value = ''
  heard.value = ''
  activeKey.value = key
  results.value = { ...results.value, [key]: null }
  recognizer = createRecognizer(
    (text) => {
      heard.value = text
    },
    () => {
      listening.value = false
      if (heard.value.trim()) check(target, key)
    },
    (event) => {
      listening.value = false
      const map = {
        'not-allowed': '麦克风权限被拒了。允许麦克风后再试。',
        'no-speech': '没听到声音，再说一遍。',
        'audio-capture': '没找到麦克风。',
      }
      const msg = map[event?.error]
      if (msg) error.value = msg
    }
  )
  if (!recognizer) {
    error.value = '当前浏览器不支持语音识别，请换 Chrome。'
    return
  }
  listening.value = true
  recognizer.start()
}
</script>

<template>
  <div class="min-h-screen bg-canvas">
    <AppHeader title="发音对比" subtitle="最小对立对" back="/" />

    <main class="sp-shell pb-16 pt-10">
      <p v-if="error" class="sp-alert-error mb-4">{{ error }}</p>

      <div class="mb-8">
        <div class="sp-eyebrow">发音</div>
        <h1 class="sp-title mt-2">先听，再说，立刻知道听成了哪个词</h1>
        <p class="sp-lede">
          点 🔊 听标准读音，点「我说」读一遍，系统按识别结果判断你读的是目标词还是对手词。
          不需要声学模型，正确率就是可测的分数。
        </p>
      </div>

      <div v-if="loading" class="grid gap-5 lg:grid-cols-2" aria-label="正在加载词表"><div v-for="i in 2" :key="i" class="sp-skeleton h-72 rounded-card"></div></div>

      <div class="grid items-start gap-5 lg:grid-cols-2">
      <div v-for="(set, si) in sets" :key="set.id" :style="{ '--i': si }" class="sp-reveal sp-card p-6">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <div class="font-semibold text-ink">{{ set.focus }}</div>
          <div class="text-xs text-ink-mute">{{ set.zh_focus }}</div>
        </div>

        <div class="mt-4 grid gap-2.5 sm:grid-cols-2">
          <div v-for="(p, i) in set.pairs" :key="i" class="rounded-2xl bg-paper p-3.5 ring-1 ring-line/70 transition duration-200 hover:ring-brand-200">
            <div class="flex items-center justify-between gap-2 text-sm">
              <button class="inline-flex items-center gap-1 rounded-lg px-1.5 py-1 font-medium text-ink hover:bg-white" @click="say(p.a)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="text-brand-600">
                  <path d="M4 9.5h3.2L12 5.6v12.8L7.2 14.5H4a.8.8 0 0 1-.8-.8v-3.4a.8.8 0 0 1 .8-.8Z" />
                  <path d="M16 9.2a4 4 0 0 1 0 5.6" />
                </svg>
                {{ p.a }}
                <span class="text-[11px] font-normal text-ink-mute">{{ p.zh_a }}</span>
              </button>
              <span class="text-line">/</span>
              <button class="inline-flex items-center gap-1 rounded-lg px-1.5 py-1 font-medium text-ink hover:bg-white" @click="say(p.b)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="text-brand-600">
                  <path d="M4 9.5h3.2L12 5.6v12.8L7.2 14.5H4a.8.8 0 0 1-.8-.8v-3.4a.8.8 0 0 1 .8-.8Z" />
                  <path d="M16 9.2a4 4 0 0 1 0 5.6" />
                </svg>
                {{ p.b }}
                <span class="text-[11px] font-normal text-ink-mute">{{ p.zh_b }}</span>
              </button>
            </div>

            <div class="mt-2 flex flex-wrap gap-1.5">
              <button
                class="sp-btn-secondary !px-2.5 !py-1 text-[11px]"
                :class="activeKey === keyOf(set, i, 'a') && listening ? 'ring-brand-400' : ''"
                @click="startCheck(set, i, 'a')"
              >
                {{ activeKey === keyOf(set, i, 'a') && listening ? '正在听…' : `我说 ${p.a}` }}
              </button>
              <button
                class="sp-btn-secondary !px-2.5 !py-1 text-[11px]"
                :class="activeKey === keyOf(set, i, 'b') && listening ? 'ring-brand-400' : ''"
                @click="startCheck(set, i, 'b')"
              >
                {{ activeKey === keyOf(set, i, 'b') && listening ? '正在听…' : `我说 ${p.b}` }}
              </button>
            </div>

            <div
              v-for="side in ['a', 'b']"
              :key="side"
              class="mt-1.5 text-[11px] leading-5"
            >
              <template v-if="results[keyOf(set, i, side)]">
                <span
                  :class="results[keyOf(set, i, side)].correct ? 'text-good' : 'text-danger'"
                  class="font-medium"
                >
                  {{ results[keyOf(set, i, side)].correct ? '✓ 读对了' : '✗ 读错了' }}
                </span>
                <span class="ml-1 text-ink-soft">{{ results[keyOf(set, i, side)].reason }}</span>
              </template>
            </div>
          </div>
        </div>
      </div>

      </div>

      <p class="mt-8 text-center text-xs text-ink-mute">
        每组 10 对待测词，读对的比例可以直接当作发音练习的通过指标。
      </p>
    </main>
  </div>
</template>
