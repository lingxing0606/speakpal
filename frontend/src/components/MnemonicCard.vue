<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import api from '../api/client'

const props = defineProps({
  term: { type: String, required: true },
  meaningZh: { type: String, default: '' },
  // 词库卡的近义/反义可作为「易混」兜底；后端返回 confusable 时优先用后端的
  related: { type: Object, default: () => ({}) },
  // 同批内已请求过的结果，避免重复打接口
  initial: { type: Object, default: null },
})

const emit = defineEmits(['done', 'fail'])

const assist = ref(null)
const loading = ref(true)
const failed = ref(false)
const showSkeleton = ref(false)
let skeletonTimer = null
let alive = true

const confusables = computed(() => {
  const raw = assist.value?.confusable
  if (Array.isArray(raw) && raw.length) {
    return raw
      .slice(0, 2)
      .map((item) =>
        typeof item === 'string'
          ? { word: item, zh: '' }
          : { word: item?.term || item?.word || '', zh: item?.meaning_zh || item?.zh || '' }
      )
      .filter((item) => item.word)
  }
  const rel = props.related || {}
  return [...(rel.similar || []), ...(rel.synonyms || []), ...(rel.antonyms || [])]
    .slice(0, 2)
    .map((word) => ({ word: String(word || ''), zh: '' }))
    .filter((item) => item.word)
})

async function load() {
  skeletonTimer = setTimeout(() => {
    if (alive && loading.value) showSkeleton.value = true
  }, 100)
  try {
    const { data } = await api.post('/study/words/assist', {
      term: props.term,
      meaning_zh: props.meaningZh,
    })
    if (!alive) return
    if (data?.assist) {
      assist.value = data.assist
      loading.value = false
      emit('done', data.assist)
    } else {
      failed.value = true
      emit('fail')
    }
  } catch {
    if (!alive) return
    failed.value = true
    emit('fail')
  } finally {
    clearTimeout(skeletonTimer)
    showSkeleton.value = false
  }
}

onMounted(() => {
  if (props.initial) {
    assist.value = props.initial
    loading.value = false
    emit('done', props.initial)
    return
  }
  load()
})

onBeforeUnmount(() => {
  alive = false
  clearTimeout(skeletonTimer)
})
</script>

<template>
  <div v-if="!failed" class="mt-3 rounded-xl bg-canvas px-3.5 py-3 text-left ring-1 ring-line/60">
    <div v-if="loading" class="space-y-2" aria-label="AI 助记加载中">
      <div v-if="showSkeleton" class="sp-skeleton h-3 w-full"></div>
      <div v-if="showSkeleton" class="sp-skeleton h-3 w-4/5"></div>
      <div v-if="showSkeleton" class="sp-skeleton h-3 w-3/5"></div>
    </div>

    <template v-else-if="assist">
      <div v-if="assist.root || assist.association" class="flex flex-wrap items-start gap-2">
        <span v-if="assist.root" class="sp-chip-line !whitespace-normal !py-0.5 !text-[11px]">词根 · {{ assist.root }}</span>
        <p v-if="assist.association" class="min-w-0 flex-1 text-[13px] leading-6 text-ink-soft">{{ assist.association }}</p>
      </div>

      <div v-if="assist.collocations?.length" class="mt-2">
        <div class="text-[11px] text-ink-mute">搭配</div>
        <ul class="mt-1 space-y-1">
          <li v-for="c in assist.collocations" :key="c" class="text-[13px] font-medium leading-5 text-ink">{{ c }}</li>
        </ul>
      </div>

      <div class="mt-2 flex flex-wrap items-center gap-1.5">
        <span class="text-[11px] text-ink-mute">易混</span>
        <template v-if="confusables.length">
          <span v-for="c in confusables" :key="c.word" class="sp-chip-line !py-0.5 !text-[11px]">
            {{ c.word }}<template v-if="c.zh"> · {{ c.zh }}</template>
          </span>
        </template>
        <span v-else class="text-[11px] text-ink-mute">暂无</span>
      </div>

      <p v-if="assist.scene_example" class="sp-num mt-2 text-[13px] italic leading-6 text-ink">{{ assist.scene_example }}</p>
      <p class="mt-2 text-right text-[11px] text-ink-mute">AI 生成，仅供参考</p>
    </template>
  </div>
</template>
