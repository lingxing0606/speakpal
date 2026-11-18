<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'

import api from '../api/client'
import { useSettingsStore } from '../stores/settings'
import type { ImageSceneOut } from '../types/api'

const emit = defineEmits(['start'])
const settings = useSettingsStore()

const MAX_BYTES = 4 * 1024 * 1024
const LONG_EDGE = 1280

interface FileMeta {
  name: string
  size: number
  width: number
  height: number
}

interface ApiError {
  response?: { status?: number; data?: { detail?: string } }
}

const open = ref(false)
const dragOver = ref(false)
const fileEl = ref<HTMLInputElement | null>(null)
const preview = ref('')
const sourceBlob = ref<Blob | null>(null)
const fileMeta = ref<FileMeta | null>(null)
// idle | compressing | selected | uploading | success
const stage = ref('idle')
const fileError = ref('')
const errorText = ref('')
const unsupported = ref(false)
const result = ref<ImageSceneOut | null>(null)

const dimsText = computed(() =>
  fileMeta.value ? `${fileMeta.value.width}×${fileMeta.value.height}` : ''
)
const sizeText = computed(() =>
  fileMeta.value ? `${Math.max(1, Math.round(fileMeta.value.size / 1024))} KB` : ''
)
const startLabel = computed(() =>
  result.value?.scene_name ? `按这张${result.value.scene_name}开练` : '按这张图开练'
)

function triggerPick() {
  fileEl.value?.click()
}

function reset() {
  if (preview.value) URL.revokeObjectURL(preview.value)
  preview.value = ''
  sourceBlob.value = null
  fileMeta.value = null
  result.value = null
  fileError.value = ''
  errorText.value = ''
  unsupported.value = false
  stage.value = 'idle'
  dragOver.value = false
}

function openPanel() {
  open.value = true
}

function closePanel() {
  reset()
  open.value = false
}

function onPick(event: Event) {
  const input = event.target as HTMLInputElement
  const picked = input.files?.[0]
  input.value = ''
  if (picked) handleFile(picked)
}

function onDrop(event: DragEvent) {
  dragOver.value = false
  const dropped = event.dataTransfer?.files?.[0]
  if (dropped) handleFile(dropped)
}

async function handleFile(picked: File) {
  fileError.value = ''
  errorText.value = ''
  unsupported.value = false
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(picked.type)) {
    fileError.value = '只支持 JPG / PNG / WebP 图片'
    return
  }
  if (picked.size > MAX_BYTES) {
    fileError.value = '图片不能超过 4MB，换一张小一点的'
    return
  }
  if (preview.value) URL.revokeObjectURL(preview.value)
  preview.value = ''
  sourceBlob.value = null
  fileMeta.value = null
  result.value = null
  stage.value = 'compressing'
  try {
    const compressed = await compressImage(picked)
    if (preview.value) URL.revokeObjectURL(preview.value)
    sourceBlob.value = compressed.blob
    preview.value = URL.createObjectURL(compressed.blob)
    fileMeta.value = {
      name: picked.name,
      size: compressed.blob.size,
      width: compressed.width,
      height: compressed.height,
    }
    stage.value = 'selected'
  } catch {
    stage.value = 'idle'
    fileError.value = '这张图读不出来，换一张试试'
  }
}

async function compressImage(picked: File) {
  const url = URL.createObjectURL(picked)
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const el = new Image()
      el.onload = () => resolve(el)
      el.onerror = () => reject(new Error('decode'))
      el.src = url
    })
    const scale = Math.min(1, LONG_EDGE / Math.max(img.naturalWidth, img.naturalHeight))
    const width = Math.max(1, Math.round(img.naturalWidth * scale))
    const height = Math.max(1, Math.round(img.naturalHeight * scale))
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('canvas')
    ctx.drawImage(img, 0, 0, width, height)
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.8))
    if (!blob) throw new Error('encode')
    return { blob, width, height }
  } finally {
    URL.revokeObjectURL(url)
  }
}

async function generate() {
  if (!sourceBlob.value || stage.value === 'uploading') return
  if (!settings.canUseLlm) {
    errorText.value = '还没有接入模型密钥，先去设置里填一个。'
    return
  }
  errorText.value = ''
  unsupported.value = false
  stage.value = 'uploading'
  const form = new FormData()
  form.append('file', new File([sourceBlob.value], 'scene.jpg', { type: 'image/jpeg' }))
  try {
    const { data } = await api.post('/scenes/from-image', form, { timeout: 60000 })
    result.value = data
    stage.value = 'success'
  } catch (e) {
    const err = e as ApiError
    stage.value = 'selected'
    const status = err?.response?.status
    const detail = String(err?.response?.data?.detail || '')
    if (status === 400 && detail.includes('不支持图片')) {
      unsupported.value = true
    } else if (status === 409) {
      errorText.value = '还没有接入模型密钥，先去设置里填一个。'
    } else if (status === 400) {
      errorText.value = detail || '这张图不合要求，换一张再试'
    } else {
      errorText.value = '这次没认出来，换张图再试'
    }
  }
}

function pickAnother() {
  result.value = null
  errorText.value = ''
  unsupported.value = false
  triggerPick()
}

function startPractice() {
  if (!result.value) return
  emit('start', result.value)
}

onBeforeUnmount(() => {
  if (preview.value) URL.revokeObjectURL(preview.value)
})
</script>

<template>
  <button
    type="button"
    class="sp-photo-entry group flex h-full min-h-[13rem] flex-col rounded-card border border-dashed border-line bg-white/70 p-5 text-left transition duration-300 hover:border-brand-300 hover:shadow-soft"
    :disabled="stage === 'uploading'"
    @click="openPanel"
  >
    <div class="sp-icon-tile text-brand-700 transition duration-300 group-hover:-rotate-6">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M4 8.5h3l1.4-2h7.2L17 8.5h3a1.5 1.5 0 0 1 1.5 1.5v8A1.5 1.5 0 0 1 20 19.5H4A1.5 1.5 0 0 1 2.5 18v-8A1.5 1.5 0 0 1 4 8.5Z" />
        <circle cx="12" cy="13.5" r="3.4" />
      </svg>
    </div>
    <div class="mt-4 text-[15px] font-semibold text-ink">拍一张生成练习</div>
    <div class="mt-2 flex flex-wrap gap-1.5">
      <span class="sp-chip-line">菜单</span>
      <span class="sp-chip-line">登机牌</span>
      <span class="sp-chip-line">招聘 JD</span>
    </div>
    <div class="mt-auto flex items-center justify-between pt-5">
      <span class="text-[11px] text-ink-mute">选择图片</span>
      <span class="sp-arrow" aria-hidden="true">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
      </span>
    </div>
  </button>

  <div v-if="open" class="sp-photo-panel col-span-full">
    <div class="sp-card-soft border border-dashed border-line p-4 sm:p-5">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="text-[13px] font-semibold text-ink">拍照生成练习</div>
          <p class="mt-0.5 text-[11px] leading-5 text-ink-mute">
            图片只用于识别场景与用词，看完即弃；JPG / PNG / WebP · ≤4MB · 自动压到长边 1280。
          </p>
        </div>
        <button class="sp-btn-ghost !px-2 !py-1 text-ink-mute" aria-label="收起拍照面板" @click="closePanel">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
        </button>
      </div>

      <input
        ref="fileEl"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        class="sr-only"
        @change="onPick"
      />

      <div v-if="stage === 'success' && result" class="mt-4">
        <div class="flex items-baseline justify-between gap-2">
          <div class="text-[15px] font-semibold text-ink">{{ result.scene_name }}</div>
          <button class="sp-btn-ghost !px-2 !py-1 text-[11px]" @click="pickAnother">换一张</button>
        </div>
        <div v-if="result.key_vocab?.length" class="mt-2 flex flex-wrap gap-1.5">
          <span v-for="v in result.key_vocab" :key="v.term" class="sp-chip-line">
            {{ v.term }}<span v-if="v.zh" class="text-ink-mute"> · {{ v.zh }}</span>
          </span>
        </div>
        <p v-if="result.context" class="mt-2 line-clamp-2 text-xs leading-6 text-ink-soft">{{ result.context }}</p>
        <p v-if="result.opening" class="mt-2 rounded-xl bg-paper px-3 py-2 text-xs leading-6 text-ink-soft ring-1 ring-line/70">
          AI 开场：{{ result.opening }}
        </p>
        <button class="sp-btn-primary mt-3 w-full sm:w-auto" @click="startPractice">{{ startLabel }}</button>
      </div>

      <div
        v-else-if="stage === 'uploading'"
        class="mt-4 flex h-36 items-center justify-center gap-3 rounded-2xl bg-paper ring-1 ring-line/70 sm:h-40"
      >
        <span class="sp-skeleton h-9 w-9 shrink-0 rounded-full"></span>
        <span class="text-xs text-ink-soft">在看这张图…</span>
      </div>

      <div v-else>
        <label
          v-if="!fileMeta && stage !== 'compressing'"
          class="sp-photo-drop mt-4 flex h-36 cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl px-4 text-center sm:h-40"
          :class="dragOver ? 'bg-brand-50 ring-brand-200' : ''"
          role="button"
          tabindex="0"
          @dragover.prevent="dragOver = true"
          @dragleave.prevent="dragOver = false"
          @drop.prevent="onDrop"
          @click.prevent="triggerPick"
          @keydown.enter.prevent="triggerPick"
          @keydown.space.prevent="triggerPick"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" class="text-ink-mute" aria-hidden="true">
            <path d="M4 8.5h3l1.4-2h7.2L17 8.5h3a1.5 1.5 0 0 1 1.5 1.5v8A1.5 1.5 0 0 1 20 19.5H4A1.5 1.5 0 0 1 2.5 18v-8A1.5 1.5 0 0 1 4 8.5Z" />
            <circle cx="12" cy="13.5" r="3.4" />
          </svg>
          <span class="text-sm text-ink-soft">把图片拖到这里，或 <span class="font-medium text-brand-700">选择图片</span></span>
          <span class="text-[11px] text-ink-mute">JPG / PNG / WebP · ≤4MB · 自动压到长边 1280</span>
        </label>

        <div
          v-else-if="stage === 'compressing'"
          class="mt-4 flex h-36 items-center justify-center gap-3 rounded-2xl bg-paper ring-1 ring-line/70 sm:h-40"
        >
          <span class="sp-skeleton h-9 w-9 shrink-0 rounded-full"></span>
          <span class="text-xs text-ink-soft">压缩中…</span>
        </div>

        <div v-else class="mt-4 flex flex-col gap-3 sm:flex-row sm:items-start">
          <img :src="preview" alt="待识别的图片预览" class="max-h-56 w-full max-w-[280px] rounded-xl object-cover ring-1 ring-line max-sm:max-h-40" />
          <div class="min-w-0 flex-1">
            <div class="truncate text-xs text-ink-soft">{{ fileMeta?.name }}</div>
            <div class="mt-0.5 text-[11px] text-ink-mute">{{ dimsText }} · {{ sizeText }}</div>
            <div class="mt-3 flex flex-wrap gap-2">
              <button class="sp-btn-ghost !px-2 !py-1 text-[11px]" @click="pickAnother">换一张</button>
              <button
                class="sp-btn-primary max-sm:w-full"
                :disabled="stage === 'compressing' || stage === 'uploading'"
                @click="generate"
              >
                生成练习 →
              </button>
            </div>
          </div>
        </div>

        <p v-if="fileError" class="mt-2 text-[11px] leading-5 text-ink-soft">{{ fileError }}</p>
        <p v-if="errorText" class="mt-2 text-[11px] leading-5 text-ink-soft">{{ errorText }}</p>
        <div v-if="unsupported" class="sp-alert-warn mt-2 flex flex-wrap items-center gap-2 text-[11px]">
          当前模型不支持图片
          <router-link to="/settings#key" class="font-medium underline underline-offset-2">去设置换 deepseek-flash</router-link>
        </div>
      </div>
    </div>
  </div>
</template>
