<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import api from '../api/client'

const router = useRouter()
const items = ref([])
const error = ref('')

onMounted(async () => {
  try {
    const { data } = await api.get('/sessions')
    items.value = data
  } catch (e) {
    error.value = '加载失败：' + (e?.response?.data?.detail || e.message)
  }
})

function open(item) {
  if (item.total_score !== null) {
    router.push(`/report/${item.id}`)
  }
}
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <header class="border-b border-slate-200 bg-white">
      <div class="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
        <div class="font-semibold">历史记录</div>
        <button class="text-sm text-slate-500 hover:text-slate-800" @click="router.push('/')">返回首页</button>
      </div>
    </header>

    <main class="mx-auto max-w-3xl px-4 py-8">
      <p v-if="error" class="text-rose-500">{{ error }}</p>
      <div v-if="items.length === 0" class="text-slate-500">还没有练习记录。</div>

      <div
        v-for="it in items"
        :key="it.id"
        :class="it.total_score !== null ? 'cursor-pointer hover:ring-indigo-400' : ''"
        class="mb-3 flex items-center justify-between rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200"
        @click="open(it)"
      >
        <div>
          <div class="font-medium">{{ it.scene_name }}</div>
          <div class="text-xs text-slate-500">{{ it.created_at }}</div>
        </div>
        <div class="text-lg font-semibold text-indigo-600">{{ it.total_score ?? '—' }}</div>
      </div>
    </main>
  </div>
</template>
