<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

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

// 阅读态
const reading = ref(null)
const readingLinks = ref([])
const readingLoading = ref(false)
let readToken = 0

// 知识条目侧栏 / 窄屏折叠条
const knowledgeItems = ref([])
const knowledgeQuery = ref('')
const knowledgeLoading = ref(false)
const knowledgeError = ref('')
const knowledgeOpen = ref(false)
const knowledgeShown = ref(false)
const flashItemId = ref(null)
const bodyInputEl = ref(null)
const ghostLayer = ref(null)
const lastSelection = ref({ start: 0, end: 0 })
let knowledgeTimer = null
let knowledgeRequest = 0
let flashTimer = null

// 悬停小窗 / 窄屏 sheet
const tipLink = ref(null)
const tipStyle = ref({})
const sheetLink = ref(null)
let hoverTimer = null
let hideTimer = null

const KIND_LABELS = { word: '单词', phrase: '短语', spelling: '拼写', grammar: '语法' }

const readSegments = computed(() => {
  const body = reading.value?.body || ''
  const links = [...(readingLinks.value || [])]
    .filter((link) => link.start >= 0 && link.end <= body.length && link.end > link.start)
    .sort((a, b) => a.start - b.start)
  const out = []
  let cursor = 0
  for (const link of links) {
    if (link.start < cursor) continue
    if (link.start > cursor) out.push({ text: body.slice(cursor, link.start) })
    out.push({ text: body.slice(link.start, link.end), link })
    cursor = link.end
  }
  if (cursor < body.length) out.push({ text: body.slice(cursor) })
  return out
})

function reduceMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function isNarrow() {
  return window.matchMedia('(max-width: 1023px)').matches
}

function kindLabel(kind) {
  return KIND_LABELS[kind] || kind
}

async function openEditor(from) {
  menuFor.value = null
  reading.value = null
  tipLink.value = null
  sheetLink.value = null
  knowledgeShown.value = false
  knowledgeOpen.value = false
  knowledgeQuery.value = ''
  knowledgeItems.value = []
  editorContentShown.value = false
  editing.value = true
  loadKnowledge()
  await nextTick()
  lastSelection.value = { start: draft.value.body.length, end: draft.value.body.length }
  bodyInputEl.value?.setSelectionRange(draft.value.body.length, draft.value.body.length)

  const el = editorEl.value
  const target = el?.getBoundingClientRect()
  if (!el || !target || !from?.width || !target.width || reduceMotion()) {
    editorContentShown.value = true
    knowledgeShown.value = true
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
    knowledgeShown.value = true
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

onMounted(() => {
  load()
  window.addEventListener('scroll', hideTip, { passive: true })
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', hideTip)
  clearTimeout(editorStyleTimer)
  clearTimeout(knowledgeTimer)
  clearTimeout(flashTimer)
  clearTimeout(hoverTimer)
  clearTimeout(hideTimer)
})

function startNew() {
  reading.value = null
  draft.value = { id: null, title: '', body: '' }
  openEditor(newNoteBtn.value?.getBoundingClientRect())
}

function startEdit(note, event) {
  reading.value = null
  draft.value = { id: note.id, title: note.title || '', body: note.body || '' }
  openEditor(event?.currentTarget?.getBoundingClientRect() || newNoteBtn.value?.getBoundingClientRect())
}

function startEditFromRead(event) {
  if (!reading.value) return
  const note = reading.value
  startEdit(note, event)
}

function finishCancel() {
  closing.value = false
  editing.value = false
  editorContentShown.value = true
  knowledgeShown.value = false
  knowledgeOpen.value = false
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
  knowledgeShown.value = false
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
    reading.value = null
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
    if (reading.value?.id === note.id) reading.value = null
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

// ---------------------------------------------------------------- 阅读态
async function openRead(note) {
  menuFor.value = null
  reading.value = note
  readingLinks.value = []
  readingLoading.value = true
  error.value = ''
  const token = ++readToken
  try {
    const { data } = await api.get(`/notes/${note.id}/links`)
    if (token !== readToken) return
    readingLinks.value = Array.isArray(data) ? data : []
  } catch (e) {
    if (token === readToken) {
      error.value = '加载知识关联失败：' + (e?.response?.data?.detail || e.message)
    }
  } finally {
    if (token === readToken) readingLoading.value = false
  }
}

function closeRead() {
  reading.value = null
  readingLinks.value = []
  hideTip()
  sheetLink.value = null
}

async function muteLink(link) {
  if (!reading.value || !link) return
  try {
    await api.post(`/notes/${reading.value.id}/mutes`, { item_id: link.item_id })
    readingLinks.value = readingLinks.value.filter((item) => item.item_id !== link.item_id)
    hideTip()
    sheetLink.value = null
  } catch (e) {
    error.value = '取消关联失败：' + (e?.response?.data?.detail || e.message)
  }
}

function cancelHideTip() {
  clearTimeout(hideTimer)
}

function hideTip() {
  clearTimeout(hoverTimer)
  clearTimeout(hideTimer)
  tipLink.value = null
}

function showTip(link, el) {
  const rect = el?.getBoundingClientRect()
  if (!rect) return
  const half = 120
  const left = Math.min(
    Math.max(rect.left + rect.width / 2, half + 8),
    window.innerWidth - half - 8
  )
  tipStyle.value = {
    left: `${left}px`,
    top: `${rect.top}px`,
  }
  tipLink.value = link
}

function onTermEnter(link, event) {
  if (isNarrow()) return
  const el = event.currentTarget
  clearTimeout(hoverTimer)
  clearTimeout(hideTimer)
  hoverTimer = setTimeout(() => showTip(link, el), 400)
}

function onTermLeave() {
  if (isNarrow()) return
  clearTimeout(hoverTimer)
  clearTimeout(hideTimer)
  hideTimer = setTimeout(hideTip, 120)
}

function onTermClick(link, event) {
  if (isNarrow()) {
    sheetLink.value = link
    return
  }
  clearTimeout(hoverTimer)
  showTip(link, event.currentTarget)
}

// ---------------------------------------------------------------- 知识条目
async function loadKnowledge() {
  if (!editing.value) return
  const token = ++knowledgeRequest
  knowledgeLoading.value = true
  knowledgeError.value = ''
  try {
    const params = { limit: 100 }
    const keyword = knowledgeQuery.value.trim()
    if (keyword) params.q = keyword
    const { data } = await api.get('/study/items', { params })
    if (token !== knowledgeRequest) return
    knowledgeItems.value = Array.isArray(data) ? data : []
  } catch (e) {
    if (token === knowledgeRequest) knowledgeError.value = '知识条目暂时取不到'
  } finally {
    if (token === knowledgeRequest) knowledgeLoading.value = false
  }
}

watch(knowledgeQuery, () => {
  if (!editing.value) return
  clearTimeout(knowledgeTimer)
  knowledgeTimer = setTimeout(loadKnowledge, 250)
})

function captureSelection() {
  const el = bodyInputEl.value
  if (!el) return
  lastSelection.value = {
    start: el.selectionStart ?? 0,
    end: el.selectionEnd ?? el.selectionStart ?? 0,
  }
}

function spawnGhost(text, sourceEl, targetEl) {
  if (reduceMotion() || !ghostLayer.value || !sourceEl || !targetEl || !text) return
  const from = sourceEl.getBoundingClientRect()
  const to = targetEl.getBoundingClientRect()
  const el = document.createElement('span')
  el.className = 'sp-tip text-[12px] text-ink'
  el.textContent = text
  ghostLayer.value.appendChild(el)
  const w = el.offsetWidth
  const h = el.offsetHeight
  const startX = from.left + from.width / 2 - w / 2
  const startY = from.top + from.height / 2 - h / 2
  const endX = to.left + 28 - w / 2
  const endY = to.top + 30 - h / 2
  el.style.position = 'absolute'
  el.style.left = '0'
  el.style.top = '0'
  el
    .animate(
      [
        { transform: `translate(${startX}px, ${startY}px) scale(1)`, opacity: 1 },
        { transform: `translate(${endX}px, ${endY}px) scale(0.86)`, opacity: 0 },
      ],
      { duration: 220, easing: 'cubic-bezier(0.3,0.9,0.25,1)', fill: 'forwards' }
    )
    .finished.then(() => el.remove(), () => el.remove())
}

function insertItem(item, event) {
  const el = bodyInputEl.value
  const body = draft.value.body || ''
  if (!el || !item?.term) return
  const start = Math.min(lastSelection.value.start ?? body.length, body.length)
  const end = Math.min(lastSelection.value.end ?? start, body.length)
  const text = item.term
  draft.value.body = body.slice(0, start) + text + body.slice(end)
  const caret = start + text.length
  lastSelection.value = { start: caret, end: caret }
  spawnGhost(text, event?.currentTarget, el)
  flashItemId.value = item.id
  clearTimeout(flashTimer)
  flashTimer = setTimeout(() => {
    flashItemId.value = null
  }, 120)
  nextTick(() => {
    el.focus()
    el.setSelectionRange(caret, caret)
    captureSelection()
  })
}
</script>

<template>
  <div class="min-h-screen bg-canvas pb-20 sm:pb-0">
    <AppHeader title="笔记" />

    <main class="sp-shell pb-40 pt-10">
      <div class="mb-8">
        <div class="sp-eyebrow">笔记</div>
        <h1 class="sp-title mt-2">随手记下想记住的说法</h1>
      </div>
      <p v-if="error" class="sp-alert-error mb-4">{{ error }}</p>

      <div v-if="editing" class="mx-auto max-w-5xl">
        <div class="grid gap-5 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div ref="editorEl" class="sp-card p-6 sm:p-8">
            <div :class="editorContentShown ? 'opacity-100 transition-opacity duration-[180ms] delay-[120ms] ease-out' : 'opacity-0'">
              <input
                v-model="draft.title"
                class="sp-input border-0 !text-lg !font-semibold focus:ring-0"
                placeholder="标题"
              />
              <textarea
                ref="bodyInputEl"
                v-model="draft.body"
                rows="8"
                class="sp-input mt-2 resize-none border-0 focus:ring-0"
                placeholder="写点什么…"
                @click="captureSelection"
                @keyup="captureSelection"
                @select="captureSelection"
                @blur="captureSelection"
              ></textarea>
              <div class="mt-4 flex items-center gap-2">
                <button class="sp-btn-primary" :disabled="saving || closing || !draft.body.trim()" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
                <button class="sp-btn-ghost" :disabled="closing" @click="cancel">取消</button>
              </div>
            </div>
          </div>

          <button class="sp-btn-secondary w-full justify-between lg:hidden" @click="knowledgeOpen = !knowledgeOpen">
            <span>知识条目 · {{ knowledgeItems.length }}</span>
            <span>{{ knowledgeOpen ? '收起' : '展开' }}</span>
          </button>

          <aside
            class="lg:sticky lg:top-24 lg:max-h-[calc(100vh-8rem)] lg:overflow-y-auto"
            :class="[
              knowledgeOpen ? 'block' : 'hidden lg:block',
              knowledgeShown ? 'translate-x-0 opacity-100' : 'translate-x-4 opacity-0',
              'transition-[transform,opacity] duration-[240ms] ease-out',
            ]"
          >
            <div class="sp-card p-4">
              <div class="flex items-center justify-between">
                <div class="text-sm font-semibold text-ink">知识条目</div>
                <span class="text-[11px] text-ink-mute">{{ knowledgeLoading ? '…' : knowledgeItems.length }}</span>
              </div>
              <input
                v-model="knowledgeQuery"
                class="sp-input mt-3 !py-1.5 text-xs"
                placeholder="搜词 / 释义"
              />
              <div v-if="knowledgeLoading" class="mt-3 space-y-2" aria-label="正在加载知识条目">
                <div v-for="i in 3" :key="i" class="sp-skeleton h-8"></div>
              </div>
              <p v-else-if="knowledgeError" class="mt-2 text-[11px] text-danger">{{ knowledgeError }}</p>
              <p v-else-if="!knowledgeItems.length" class="mt-2 text-[11px] text-ink-mute">没有匹配的条目</p>
              <ul v-else class="mt-2 space-y-0.5">
                <li v-for="item in knowledgeItems" :key="item.id">
                  <button
                    class="w-full rounded-lg px-2 py-1.5 text-left transition hover:bg-canvas"
                    :class="flashItemId === item.id ? 'bg-brand-50' : ''"
                    @click="insertItem(item, $event)"
                  >
                    <div class="flex flex-wrap items-center gap-1.5">
                      <span class="text-[12px] font-medium text-ink">{{ item.term }}</span>
                      <span class="sp-chip-line !px-1.5 !py-0 !text-[10px]">{{ kindLabel(item.kind) }}</span>
                    </div>
                    <div class="mt-0.5 line-clamp-1 text-[11px] text-ink-mute">{{ item.meaning_zh || '暂无释义' }}</div>
                  </button>
                </li>
              </ul>
            </div>
          </aside>
        </div>
      </div>

      <div v-else-if="reading" class="sp-card mx-auto max-w-3xl p-6 sm:p-8">
        <div class="flex items-start justify-between gap-4">
          <div class="min-w-0">
            <div class="truncate text-lg font-semibold text-ink">{{ reading.title || '无标题' }}</div>
            <div class="mt-1 text-[11px] text-ink-mute">{{ when(reading.updated_at || reading.created_at) }}</div>
          </div>
          <div class="flex shrink-0 gap-2">
            <button class="sp-btn-secondary !px-3 !py-1.5 text-xs" @click="startEditFromRead($event)">编辑</button>
            <button class="sp-btn-ghost !px-3 !py-1.5 text-xs" @click="closeRead">关闭</button>
          </div>
        </div>

        <div v-if="readingLoading" class="mt-5 space-y-2" aria-label="正在加载知识关联">
          <div v-for="i in 3" :key="i" class="sp-skeleton h-4"></div>
        </div>
        <div v-else class="mt-5 whitespace-pre-wrap text-sm leading-7 text-ink">
          <template v-for="(seg, i) in readSegments" :key="i">
            <span v-if="!seg.link">{{ seg.text }}</span>
            <span
              v-else
              class="sp-term"
              @mouseenter="onTermEnter(seg.link, $event)"
              @mouseleave="onTermLeave"
              @click="onTermClick(seg.link, $event)"
            >{{ seg.text }}</span>
          </template>
        </div>
      </div>

      <Transition v-else :css="false" @leave="fadeListOut">
        <div v-if="!editing && !reading">
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
              @click="openRead(n, $event)"
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

    <!-- 编辑态从左栏插入时飞向输入框的副本 -->
    <div ref="ghostLayer" class="pointer-events-none fixed inset-0 z-50" aria-hidden="true"></div>

    <!-- 桌面悬停小窗：从词向上 160ms -->
    <div class="pointer-events-none fixed z-40" :style="tipStyle">
      <Transition
        enter-active-class="transition duration-[160ms] ease-out"
        enter-from-class="translate-y-1 opacity-0"
        enter-to-class="translate-y-0 opacity-100"
        leave-active-class="transition duration-[120ms] ease-in"
        leave-to-class="opacity-0"
      >
        <div
          v-if="tipLink"
          class="sp-tip pointer-events-auto absolute bottom-full left-1/2 mb-2 w-[240px] -translate-x-1/2"
          @mouseenter="cancelHideTip"
          @mouseleave="hideTip"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="flex flex-wrap items-baseline gap-1.5">
                <span class="text-sm font-semibold text-ink">{{ tipLink.term }}</span>
                <span v-if="tipLink.phonetic" class="text-[11px] text-ink-mute">{{ tipLink.phonetic }}</span>
              </div>
              <p class="mt-1 text-[12px] leading-5 text-ink-soft">{{ tipLink.meaning_zh || '暂无释义' }}</p>
              <p v-if="tipLink.example" class="sp-num mt-1 text-[12px] italic leading-5 text-ink-soft">{{ tipLink.example }}</p>
            </div>
            <button class="shrink-0 text-lg leading-none text-ink-mute transition hover:text-ink" aria-label="关闭" @click="hideTip">×</button>
          </div>
          <div class="mt-2 flex justify-end">
            <button class="text-[11px] text-danger transition hover:underline" @click="muteLink(tipLink)">取消关联</button>
          </div>
        </div>
      </Transition>
    </div>

    <!-- 窄屏点词底部 sheet：260ms -->
    <Transition
      enter-active-class="transition-transform duration-[260ms] ease-out"
      enter-from-class="translate-y-full"
      leave-active-class="transition-transform duration-[180ms] ease-in"
      leave-to-class="translate-y-full"
    >
      <div v-if="sheetLink" class="fixed inset-0 z-40 flex items-end bg-ink/30 backdrop-blur-sm" @click.self="sheetLink = null">
        <div class="w-full rounded-t-card bg-white p-6 pb-[max(1.5rem,env(safe-area-inset-bottom))] shadow-lift">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-baseline gap-2">
                <span class="text-base font-semibold text-ink">{{ sheetLink.term }}</span>
                <span v-if="sheetLink.phonetic" class="text-[12px] text-ink-mute">{{ sheetLink.phonetic }}</span>
              </div>
              <p class="mt-1.5 text-sm leading-6 text-ink-soft">{{ sheetLink.meaning_zh || '暂无释义' }}</p>
              <p v-if="sheetLink.example" class="sp-num mt-2 text-sm italic leading-6 text-ink-soft">{{ sheetLink.example }}</p>
            </div>
            <button class="shrink-0 text-xl leading-none text-ink-mute" aria-label="关闭" @click="sheetLink = null">×</button>
          </div>
          <div class="mt-4 flex justify-end">
            <button class="sp-btn-secondary text-xs" @click="muteLink(sheetLink)">取消关联</button>
          </div>
        </div>
      </div>
    </Transition>

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
