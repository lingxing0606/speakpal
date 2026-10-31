<script setup>
import { onMounted, ref } from 'vue'

import api from '../api/client'
import BrandLogo from '../components/BrandLogo.vue'
import TabBar from '../components/TabBar.vue'

const loading = ref(true)
const error = ref('')
const notes = ref([])
const editing = ref(false)
const saving = ref(false)
const draft = ref({ id: null, title: '', body: '' })
const menuFor = ref(null)
const confirming = ref(null)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/notes')
    notes.value = Array.isArray(data) ? data : data?.items || []
  } catch (e) {
    if (e?.response?.status === 404) {
      notes.value = []
    } else {
      error.value = '加载笔记失败：' + (e?.response?.data?.detail || e.message)
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)

function startNew() {
  draft.value = { id: null, title: '', body: '' }
  editing.value = true
}

function startEdit(note) {
  draft.value = { id: note.id, title: note.title || '', body: note.body || '' }
  editing.value = true
}

function cancel() {
  editing.value = false
  draft.value = { id: null, title: '', body: '' }
}

async function save() {
  if (saving.value) return
  saving.value = true
  error.value = ''
  try {
    const payload = { title: draft.value.title.trim(), body: draft.value.body.trim() }
    if (!payload.title && !payload.body) {
      saving.value = false
      return
    }
    if (draft.value.id) {
      await api.patch(`/notes/${draft.value.id}`, payload)
    } else {
      await api.post('/notes', payload)
    }
    editing.value = false
    draft.value = { id: null, title: '', body: '' }
    await load()
  } catch (e) {
    error.value = '保存失败：' + (e?.response?.data?.detail || e.message)
  } finally {
    saving.value = false
  }
}

function askRemove(note) {
  menuFor.value = null
  confirming.value = note
}

async function remove(note) {
  try {
    await api.delete(`/notes/${note.id}`)
    confirming.value = null
    await load()
  } catch (e) {
    error.value = '删除失败：' + (e?.response?.data?.detail || e.message)
  }
}

function when(iso) {
  if (!iso) return ''
  const hasZone = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso)
  const d = new Date(hasZone ? iso : `${iso}Z`)
  if (Number.isNaN(d.getTime())) return iso
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
</script>

<template>
  <div class="min-h-screen bg-canvas pb-16 sm:pb-0">
    <header class="sp-header">
      <div class="sp-shell flex items-center justify-between py-3">
        <div class="flex items-center gap-3">
          <router-link to="/" aria-label="返回首页">
            <BrandLogo :size="30" />
          </router-link>
          <span class="h-4 w-px bg-line"></span>
          <div class="font-semibold text-ink">笔记</div>
        </div>
        <div class="flex items-center gap-1">
          <router-link to="/study" class="sp-btn-ghost">今日复习</router-link>
          <button class="sp-btn-primary !px-3 !py-1.5 text-xs" @click="startNew">新建</button>
        </div>
      </div>
    </header>

    <main class="sp-shell py-8">
      <p v-if="error" class="sp-alert-error mb-4">{{ error }}</p>

      <div v-if="editing" class="sp-card p-6">
        <input
          v-model="draft.title"
          class="sp-input border-0 !text-lg !font-semibold focus:ring-0"
          placeholder="标题"
        />
        <textarea
          v-model="draft.body"
          rows="8"
          class="sp-input mt-2 resize-none border-0 focus:ring-0"
          placeholder="写点什么…"
        ></textarea>
        <div class="mt-4 flex items-center gap-2">
          <button class="sp-btn-primary" :disabled="saving || !draft.body.trim()" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
          <button class="sp-btn-ghost" @click="cancel">取消</button>
        </div>
      </div>

      <p v-if="loading" class="text-sm text-ink-mute">正在加载…</p>

      <div v-else-if="!editing && notes.length === 0" class="mt-10 flex flex-col items-center text-center">
        <div class="sp-icon-tile h-14 w-14 text-brand-700">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M6 3.5h9l4 4v13H6z" />
            <path d="M15 3.5v4h4" />
            <path d="M9 12h7M9 16h5" />
          </svg>
        </div>
        <div class="mt-4 text-lg font-semibold text-ink">还没有笔记</div>
        <p class="mt-1 max-w-xs text-sm leading-6 text-ink-soft">练习里遇到想记住的说法，随手写在这里。</p>
        <button class="sp-btn-primary mt-6" @click="startNew">写第一条</button>
      </div>

      <div v-else-if="!editing" class="space-y-3">
        <div
          v-for="n in notes"
          :key="n.id"
          class="sp-card-flat group flex cursor-pointer items-start justify-between gap-4 p-5 transition duration-200 ease-out hover:-translate-y-0.5 hover:shadow-lift"
          @click="startEdit(n)"
        >
          <div class="min-w-0">
            <div class="truncate font-medium text-ink">{{ n.title || '无标题' }}</div>
            <p class="mt-1 line-clamp-2 text-xs leading-5 text-ink-soft">{{ n.body }}</p>
          </div>
          <div class="flex shrink-0 flex-col items-end gap-1">
            <span class="text-[11px] text-ink-mute">{{ when(n.updated_at || n.created_at) }}</span>
            <div class="relative">
              <button class="rounded-lg px-1.5 py-0.5 text-sm text-ink-mute transition hover:bg-canvas hover:text-ink-soft" aria-label="更多操作" @click.stop="menuFor = menuFor === n.id ? null : n.id">⋯</button>
              <div v-if="menuFor === n.id" class="absolute right-0 top-6 z-10 w-28 rounded-xl bg-white p-1 shadow-card ring-1 ring-line">
                <button class="block w-full rounded-lg px-3 py-1.5 text-left text-xs text-danger hover:bg-rose-50" @click.stop="askRemove(n)">删除</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>

    <div v-if="confirming" class="fixed inset-0 z-40 flex items-center justify-center bg-ink/30 px-4">
      <div class="w-full max-w-sm rounded-2xl bg-white p-6 shadow-lift">
        <div class="font-semibold text-ink">删除这条笔记？</div>
        <p class="mt-1 text-xs leading-5 text-ink-soft">删除后无法恢复。</p>
        <div class="mt-4 flex justify-end gap-2">
          <button class="sp-btn-ghost" @click="confirming = null">取消</button>
          <button class="sp-btn bg-danger text-white hover:bg-rose-700" @click="remove(confirming)">删除</button>
        </div>
      </div>
    </div>

    <TabBar />
  </div>
</template>
