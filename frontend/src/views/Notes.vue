<script setup>
import { nextTick, onMounted, ref } from 'vue'

import api from '../api/client'
import AppHeader from '../components/AppHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import TabBar from '../components/TabBar.vue'

const loading = ref(true)
const error = ref('')
const notes = ref([])
const editing = ref(false)
const saving = ref(false)
const draft = ref({ id: null, title: '', body: '' })
const menuFor = ref(null)
const confirming = ref(null)

// 编辑卡 FLIP：从底部按钮（或点开的卡片）长到列表首位；取消时反向收回按钮
const editorEl = ref(null)
const newNoteBtn = ref(null)
const editorContentShown = ref(true)
const closing = ref(false)
let editorStyleTimer = null

function reduceMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

async function openEditor(from) {
  editorContentShown.value = false
  editing.value = true
  await nextTick()
  const el = editorEl.value
  const target = el?.getBoundingClientRect()
  if (!el || !target || !from?.width || !target.width || reduceMotion()) {
    editorContentShown.value = true
    return
  }
  const dx = from.left - target.left
  const dy = from.top - target.top
  const sx = from.width / target.width
  const sy = from.height / target.height
  el.style.transformOrigin = 'top left'
  el.style.transition = 'none'
  el.style.transform = `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`
  el.style.opacity = '0'
  await nextTick()
  requestAnimationFrame(() => {
    // 先强制回流：否则起点与终点在同一帧计算，浏览器直接跳变、没有过渡
    void el.offsetWidth
    el.style.transition = 'transform 320ms cubic-bezier(0.2,0.7,0.2,1), opacity 160ms ease-out'
    el.style.transform = 'translate(0px, 0px) scale(1, 1)'
    el.style.opacity = '1'
    editorContentShown.value = true
  })
  clearTimeout(editorStyleTimer)
  editorStyleTimer = setTimeout(() => {
    el.style.transition = ''
    el.style.transform = ''
    el.style.opacity = ''
  }, 420)
}

// 列表退场：opacity 1→0 + 上移 8px，140ms，不做 stagger
function fadeListOut(el, done) {
  if (reduceMotion()) {
    done()
    return
  }
  el.animate(
    [
      { opacity: 1, transform: 'translateY(0px)' },
      { opacity: 0, transform: 'translateY(-8px)' },
    ],
    { duration: 140, easing: 'ease-out' }
  ).finished.then(done, done)
}

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
  openEditor(newNoteBtn.value?.getBoundingClientRect())
}

function startEdit(note, event) {
  draft.value = { id: note.id, title: note.title || '', body: note.body || '' }
  openEditor(event?.currentTarget?.getBoundingClientRect() || newNoteBtn.value?.getBoundingClientRect())
}

function finishCancel() {
  closing.value = false
  editing.value = false
  editorContentShown.value = true
  draft.value = { id: null, title: '', body: '' }
}

async function cancel() {
  if (closing.value) return
  const el = editorEl.value
  const btn = newNoteBtn.value
  if (!el || !btn || reduceMotion()) {
    finishCancel()
    return
  }
  closing.value = true
  const a = el.getBoundingClientRect()
  const b = btn.getBoundingClientRect()
  const dx = b.left - a.left
  const dy = b.top - a.top
  const sx = b.width / a.width
  const sy = b.height / a.height
  await el
    .animate(
      [
        { transform: 'translate(0px, 0px) scale(1, 1)', opacity: 1 },
        { transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`, opacity: 0 },
      ],
      { duration: 260, easing: 'cubic-bezier(0.2,0.7,0.2,1)', fill: 'forwards' }
    )
    .finished.catch(() => {})
  finishCancel()
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
  <div class="min-h-screen bg-canvas pb-20 sm:pb-0">
    <AppHeader title="笔记" />

    <main class="sp-shell pb-40 pt-10">
      <div class="mb-8">
        <div class="sp-eyebrow">笔记</div>
        <h1 class="sp-title mt-2">随手记下想记住的说法</h1>
        <p class="sp-lede">练习里冒出来的好句子、老是说错的地方，写在这里。点开就能改。</p>
      </div>
      <p v-if="error" class="sp-alert-error mb-4">{{ error }}</p>

      <div v-if="editing" ref="editorEl" class="sp-card mx-auto max-w-3xl p-6 sm:p-8">
        <div :class="editorContentShown ? 'opacity-100 transition-opacity duration-[180ms] delay-[120ms] ease-out' : 'opacity-0'">
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
          <button class="sp-btn-primary" :disabled="saving || closing || !draft.body.trim()" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
          <button class="sp-btn-ghost" :disabled="closing" @click="cancel">取消</button>
        </div>
        </div>
      </div>

      <Transition :css="false" @leave="fadeListOut">
        <div v-if="!editing">
      <div v-if="loading" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-label="正在加载"><div v-for="i in 6" :key="i" class="sp-skeleton h-36 rounded-2xl"></div></div>

      <div v-else-if="notes.length === 0" class="sp-card">
        <EmptyState icon="notes" title="还没有笔记" text="练习里遇到想记住的说法，随手写在这里。">
          <button class="sp-btn-primary" @click="startNew">写第一条</button>
        </EmptyState>
      </div>

      <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div
          v-for="(n, ni) in notes"
          :key="n.id"
          :style="{ '--i': Math.min(ni, 12) }"
          class="sp-reveal sp-hover group flex min-h-[9rem] cursor-pointer flex-col justify-between gap-4 rounded-2xl bg-white p-5 ring-1 ring-line/80"
          @click="startEdit(n, $event)"
        >
          <div class="min-w-0">
            <div class="truncate font-semibold text-ink">{{ n.title || '无标题' }}</div>
            <p class="mt-2 line-clamp-3 text-[13px] leading-6 text-ink-soft">{{ n.body }}</p>
          </div>
          <div class="flex items-center justify-between gap-2 border-t border-line/70 pt-3">
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
        </div>
      </Transition>
    </main>

    <!-- 底部动作条：窄屏悬在 TabBar 之上，编辑态隐藏（由编辑卡内的保存/取消承接） -->
    <div class="sticky bottom-16 z-10 bg-gradient-to-t from-canvas via-canvas/95 to-canvas/0 pb-[max(1rem,env(safe-area-inset-bottom))] pt-4 sm:bottom-0">
      <div class="sp-shell flex justify-end">
        <button
          ref="newNoteBtn"
          class="sp-btn-primary w-full py-3 transition duration-[120ms] ease-out sm:w-auto sm:!py-2.5"
          :class="editing ? 'pointer-events-none translate-y-2 opacity-0' : ''"
          @click="startNew"
        >
          ＋ 新建笔记
        </button>
      </div>
    </div>

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
