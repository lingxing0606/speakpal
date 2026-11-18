<script setup lang="ts">
import { ref } from 'vue'

import api from '../api/client'

const KINDS = [
  { id: 'bug', label: '遇到问题' },
  { id: 'idea', label: '功能建议' },
  { id: 'other', label: '其他' },
] as const

const kind = ref<'bug' | 'idea' | 'other'>('bug')
const content = ref('')
const sending = ref(false)
const tip = ref('')
const failed = ref(false)

async function submit() {
  const text = content.value.trim()
  if (!text || sending.value) return
  sending.value = true
  tip.value = ''
  failed.value = false
  try {
    await api.post('/feedback', { kind: kind.value, content: text, page: window.location.pathname })
    content.value = ''
    tip.value = '收到了，谢谢！我们会认真看每一条。'
  } catch (e) {
    const err = e as { response?: { data?: { detail?: unknown } } }
    const detail = err?.response?.data?.detail
    failed.value = true
    tip.value = typeof detail === 'string' ? detail : '提交失败，请稍后再试'
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <section id="feedback" class="sp-card scroll-mt-24 p-6 sm:p-7">
    <h2 class="sp-section-title">意见反馈</h2>
    <p class="mt-1 text-xs leading-5 text-ink-soft">评分不准、哪里卡住、想要什么功能，都可以写在这里。</p>
    <div class="mt-4 space-y-3">
      <div class="flex flex-wrap gap-2">
        <button
          v-for="k in KINDS"
          :key="k.id"
          type="button"
          class="rounded-full px-3 py-1.5 text-xs font-medium ring-1 transition"
          :class="kind === k.id ? 'bg-ink text-white ring-ink' : 'bg-white text-ink-soft ring-line hover:text-ink'"
          @click="kind = k.id"
        >
          {{ k.label }}
        </button>
      </div>
      <textarea
        v-model="content"
        rows="4"
        maxlength="1000"
        class="sp-input"
        placeholder="写下你的问题或建议（最多 1000 字）"
      ></textarea>
      <div class="flex items-center gap-3">
        <button class="sp-btn-primary" :disabled="sending || !content.trim()" @click="submit">
          {{ sending ? '提交中…' : '提交反馈' }}
        </button>
        <p v-if="tip" class="text-xs" :class="failed ? 'text-danger' : 'text-good'">{{ tip }}</p>
      </div>
    </div>
  </section>
</template>
