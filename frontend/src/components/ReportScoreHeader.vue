<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, type PropType } from 'vue'

import api from '../api/client'
import { useSettingsStore } from '../stores/settings'
import type { ReportOut } from '../types/api'

interface PillTextStyle {
  fontFamily: string
  fontSize: string
  fontWeight: string
  color: string
  lineHeight: string
}

/** 焦点圈定用：按钮有 disabled，链接没有，按可选字段取 */
interface FocusableElement extends HTMLElement {
  disabled?: boolean
}

const props = defineProps({
  report: { type: Object as PropType<ReportOut>, default: null },
})

const settings = useSettingsStore()

const SCALE_OPTIONS = [
  { id: 'ielts', label: '雅思' },
  { id: 'cefr', label: 'CEFR' },
  { id: 'toefl', label: '托福' },
  { id: 'duolingo', label: '多邻国' },
  { id: 'cet', label: '四六级' },
]
const scaleEls: (HTMLElement | null)[] = []
const ghostLayer = ref<HTMLElement | null>(null)
const pillBoxEl = ref<HTMLElement | null>(null)
const pillHidden = ref(false)
const scaleInfoOpen = ref(false)
const scaleInfoEl = ref<HTMLElement | null>(null)
const scaleInfoTrigger = ref<HTMLElement | null>(null)
const ghostEls: HTMLElement[] = []
let switchToken = 0

const scaleItems = computed(() => props.report?.scales?.items || null)
const hasScales = computed(() => !!scaleItems.value)
const activeScale = computed(() => settings.reportScale)
const scaleVersion = computed(() => props.report?.scales?.version || '2026-11')
// scales 缺失（老后端）时回退到 band / cefr
const legacyScales = computed(
  () => !hasScales.value && props.report?.band !== null && props.report?.band !== undefined
)

// 四六级通过线从 band 4.0（B1）起算，与后端换算表里的 425 分线一致
const cetPassed = computed(() => typeof props.report?.band === 'number' && props.report.band >= 4.0)
const cetRangeText = computed(() => {
  const cet = scaleItems.value?.cet
  if (!cet) return '—'
  return `CET-4 ${cet.cet4 || '—'} · CET-6 ${cet.cet6 || '—'}`
})
const cetPassPills = computed(() => [
  { id: 'cet4', label: `CET-4 ${cetPassed.value ? '已通过' : '未通过'}`, passed: cetPassed.value },
  { id: 'cet6', label: `CET-6 ${cetPassed.value ? '已通过' : '未通过'}`, passed: cetPassed.value },
])

// 药丸四种读法 + 两种兜底：雅思单点（衬线）/ 字母 / 区间 / 四六级（两档或两枚通过水平）
const pillKind = computed(() => {
  if (legacyScales.value) return 'legacy'
  if (!hasScales.value) return 'below'
  const one = activeScale.value
  if (one === 'cet') return settings.cetPassOnly ? 'cet-pass' : 'cet'
  return one
})
const pillValue = computed(() => {
  const items = scaleItems.value
  if (!items) return ''
  if (activeScale.value === 'cet') return cetRangeText.value
  return items[activeScale.value]?.display || ''
})
// ghost 用的一行文本（与药丸内容一致，四六级通过水平合并成一行）
const pillFlatText = computed(() => {
  if (pillKind.value === 'below') return '低于 A2 · 暂不评级'
  if (pillKind.value === 'cet-pass') return cetPassPills.value.map((p) => p.label).join(' · ')
  if (pillKind.value === 'legacy') {
    if (activeScale.value === 'ielts') return `雅思 ${props.report?.band}`
    if (activeScale.value === 'cefr') return `CEFR ${props.report?.cefr}`
    return '—'
  }
  const name = SCALE_OPTIONS.find((s) => s.id === activeScale.value)?.label || ''
  return `${name} ${pillValue.value}`.trim()
})
const scaleRows = computed(() => {
  const items = scaleItems.value
  if (!items) return []
  return [
    { id: 'ielts', label: '雅思', value: items.ielts?.display || '—', reference: false },
    { id: 'cefr', label: 'CEFR', value: items.cefr?.display || '—', reference: false },
    { id: 'toefl', label: '托福', value: items.toefl?.display || '—', reference: false },
    { id: 'duolingo', label: '多邻国', value: items.duolingo?.display || '—', reference: false },
    { id: 'cet', label: '四六级', value: cetRangeText.value, reference: true },
  ]
})

function reducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function clearGhosts() {
  ghostEls.splice(0).forEach((el) => el.remove())
}

function pillTextStyle(): PillTextStyle | null {
  const el = pillBoxEl.value?.querySelector('[data-pill-text]')
  if (!el) return null
  const cs = getComputedStyle(el)
  return {
    fontFamily: cs.fontFamily,
    fontSize: cs.fontSize,
    fontWeight: cs.fontWeight,
    color: cs.color,
    lineHeight: cs.lineHeight,
  }
}

// 角标/飞行副本：固定层里按视口坐标摆，字体与药丸一致
function makeGhost(text: string, style: PillTextStyle | null) {
  const layer = ghostLayer.value
  if (!layer || !style) return null
  const el = document.createElement('span')
  el.textContent = text
  el.style.cssText =
    'position:absolute;pointer-events:none;white-space:nowrap;' +
    `font-family:${style.fontFamily};font-size:${style.fontSize};font-weight:${style.fontWeight};` +
    `color:${style.color};line-height:${style.lineHeight};`
  layer.appendChild(el)
  ghostEls.push(el)
  return el
}

function placeGhost(el: HTMLElement, centerX: number, centerY: number) {
  const rect = el.getBoundingClientRect()
  el.style.left = `${centerX - rect.width / 2}px`
  el.style.top = `${centerY - rect.height / 2}px`
}

async function persistScale(id: string) {
  try {
    await api.patch('/me/settings', { report_scale: id })
  } catch {
    // 静默：本次展示已生效，下次进来回到服务端值
  }
}

async function pickScale(id: string, event?: MouseEvent) {
  if (id === activeScale.value || !hasScales.value) return
  const token = ++switchToken
  clearGhosts()
  const from = SCALE_OPTIONS.findIndex((s) => s.id === activeScale.value)
  const to = SCALE_OPTIONS.findIndex((s) => s.id === id)
  const dir = to > from ? 1 : -1
  const chip = (event?.currentTarget as HTMLElement | null) || scaleEls[to]
  const chipRect = chip?.getBoundingClientRect()
  const oldText = pillFlatText.value
  const oldStyle = pillTextStyle()
  const oldTextEl = pillBoxEl.value?.querySelector('[data-pill-text]')
  const oldRect = oldTextEl?.getBoundingClientRect()

  // 立即换数据：药丸宽度一次性到位，不做宽度动画
  settings.setReportScale(id)
  persistScale(id)
  pillHidden.value = true

  if (reducedMotion()) {
    // 无 ghost、无位移，只做 120ms 透明度交叉
    await nextTick()
    pillHidden.value = false
    pillBoxEl.value?.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 120, easing: 'ease-out' })
    return
  }

  // 1) 旧值退场：120ms，按新 chip 的相对方向轻推 ∓6px
  if (oldRect && oldStyle) {
    const exit = makeGhost(oldText, oldStyle)
    if (exit) {
      placeGhost(exit, oldRect.left + oldRect.width / 2, oldRect.top + oldRect.height / 2)
      exit
        .animate(
          [
            { opacity: 1, transform: 'translateX(0px)' },
            { opacity: 0, transform: `translateX(${-dir * 6}px)` },
          ],
          { duration: 120, easing: 'ease-out', fill: 'forwards' }
        )
        .finished.then(() => exit.remove(), () => exit.remove())
    }
  }

  // 2) 新值 ghost：从被点 chip 中心飞进药丸中心（200ms，延迟 40ms）
  await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 40))
  if (token !== switchToken) return
  const box = pillBoxEl.value
  const style = pillTextStyle() || oldStyle
  const target = (box?.querySelector('[data-pill-text]') || box)?.getBoundingClientRect()
  if (!box || !chipRect || !target || !style) {
    pillHidden.value = false
    return
  }
  const ghost = makeGhost(pillFlatText.value, style)
  if (!ghost) {
    pillHidden.value = false
    return
  }
  const startX = chipRect.left + chipRect.width / 2
  const startY = chipRect.top + chipRect.height / 2
  placeGhost(ghost, startX, startY)
  const dx = target.left + target.width / 2 - startX
  const dy = target.top + target.height / 2 - startY
  ghost
    .animate(
      [
        { transform: 'translate(0px, 0px) scale(0.86)' },
        { transform: `translate(${dx}px, ${dy}px) scale(1)` },
      ],
      { duration: 200, easing: 'cubic-bezier(0.3,0.9,0.25,1)' }
    )
    .finished.then(
      () => {
        ghost.remove()
        if (token !== switchToken) return
        // 3) 到达后真药丸 100ms 淡入
        pillHidden.value = false
        nextTick(() => box.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 100, easing: 'ease-out' }))
      },
      () => ghost.remove()
    )
}

function onScaleKeydown(event: KeyboardEvent, i: number) {
  if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return
  event.preventDefault()
  const delta = event.key === 'ArrowRight' ? 1 : -1
  const next = (i + delta + SCALE_OPTIONS.length) % SCALE_OPTIONS.length
  pickScale(SCALE_OPTIONS[next].id)
  nextTick(() => scaleEls[next]?.focus())
}

// 换算说明：桌面居中卡 / 窄屏底部 sheet
async function openScaleInfo(event?: MouseEvent) {
  scaleInfoTrigger.value = (event?.currentTarget as HTMLElement | null) || (document.activeElement as HTMLElement | null)
  scaleInfoOpen.value = true
  await nextTick()
  const el = scaleInfoEl.value
  el?.focus({ preventScroll: true })
  if (!el || reducedMotion()) return
  const narrow = window.matchMedia('(max-width: 639px)').matches
  el.animate(
    narrow
      ? [
          { transform: 'translateY(24px)', opacity: 0 },
          { transform: 'translateY(0)', opacity: 1 },
        ]
      : [
          { transform: 'scale(0.98)', opacity: 0 },
          { transform: 'scale(1)', opacity: 1 },
        ],
    { duration: narrow ? 260 : 200, easing: 'cubic-bezier(0.2,0.7,0.2,1)' }
  )
}

async function closeScaleInfo() {
  const el = scaleInfoEl.value
  if (el && !reducedMotion()) {
    const narrow = window.matchMedia('(max-width: 639px)').matches
    const anim = el.animate(
      narrow
        ? [
            { transform: 'translateY(0)', opacity: 1 },
            { transform: 'translateY(24px)', opacity: 0 },
          ]
        : [
            { transform: 'scale(1)', opacity: 1 },
            { transform: 'scale(0.98)', opacity: 0 },
          ],
      { duration: 180, easing: 'ease-out', fill: 'forwards' }
    )
    await anim.finished.catch(() => {})
  }
  scaleInfoOpen.value = false
  await nextTick()
  scaleInfoTrigger.value?.focus({ preventScroll: true })
}

function onScaleInfoKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && scaleInfoOpen.value) closeScaleInfo()
}

onMounted(() => {
  window.addEventListener('keydown', onScaleInfoKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onScaleInfoKeydown)
  clearGhosts()
})

// aria-modal 只描述语义，Tab 仍会跑到背后的页签；这里把焦点循环限制在面板内
function trapScaleInfoFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab') return
  const el = scaleInfoEl.value
  if (!el) return
  const focusables = [...el.querySelectorAll<FocusableElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
    .filter((node) => !node.disabled && node.offsetParent !== null)
  if (!focusables.length) {
    event.preventDefault()
    el.focus({ preventScroll: true })
    return
  }
  const first = focusables[0]
  const last = focusables[focusables.length - 1]
  const active = document.activeElement
  if (event.shiftKey) {
    if (active === first || active === el || !el.contains(active)) {
      event.preventDefault()
      last.focus({ preventScroll: true })
    }
  } else if (active === last || !el.contains(active)) {
    event.preventDefault()
    first.focus({ preventScroll: true })
  }
}
</script>

<template>
  <div
    class="relative overflow-hidden rounded-card bg-ink p-6 text-white shadow-lift sm:p-7"
  >
    <div class="pointer-events-none absolute -right-12 -top-16 h-48 w-48 rounded-full bg-brand-500/40 blur-2xl"></div>
    <div class="pointer-events-none absolute -bottom-16 -left-10 h-40 w-40 rounded-full bg-coral-500/25 blur-2xl"></div>
    <div class="relative">
      <div class="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/60">综合得分</div>
      <div class="mt-2 flex items-end gap-2">
        <span class="sp-num text-[64px] font-semibold leading-none">{{ report.total_score }}</span>
        <span class="mb-2 text-sm text-white/50">/ 100</span>
      </div>
      <!-- 等级药丸：随量表换读法（雅思衬线单点 / 字母 / 区间 / 四六级两档或两枚通过水平） -->
      <div ref="pillBoxEl" class="mt-4 flex flex-wrap items-center gap-1.5">
        <span v-if="pillKind === 'below'" class="text-[11px] text-white/50">低于 A2 · 暂不评级</span>
        <template v-else-if="pillKind === 'cet-pass'">
          <span
            v-for="cet in cetPassPills"
            :key="cet.id"
            class="inline-flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-full bg-white/10 px-2.5 py-1.5 text-[12px] font-medium text-white ring-1 ring-white/15"
          >
            <span
              class="h-[5px] w-[5px] shrink-0 rounded-full"
              :class="cet.passed ? 'bg-brand-200' : 'bg-white/30'"
            ></span>
            {{ cet.label }}
          </span>
        </template>
        <span
          v-else
          :style="pillHidden ? { opacity: 0 } : undefined"
          class="inline-flex max-w-full items-center gap-1.5 rounded-full bg-white/10 px-3.5 py-1.5 text-[13px] font-medium text-white ring-1 ring-white/15"
        >
          <span data-pill-text class="inline-flex min-w-0 items-center gap-1.5">
            <template v-if="pillKind === 'ielts'">
              <span class="text-[13px]">雅思</span>
              <span class="sp-num text-[15px] font-semibold">{{ scaleItems?.ielts?.display }}</span>
            </template>
            <template v-else-if="pillKind === 'cefr'">
              <span class="text-[13px]">CEFR</span>
              <span class="font-semibold">{{ scaleItems?.cefr?.display }}</span>
            </template>
            <template v-else-if="pillKind === 'toefl'">
              <span class="text-[13px]">托福</span>
              <span class="font-semibold">{{ scaleItems?.toefl?.display }}</span>
            </template>
            <template v-else-if="pillKind === 'duolingo'">
              <span class="text-[13px]">多邻国</span>
              <span class="font-semibold">{{ scaleItems?.duolingo?.display }}</span>
            </template>
            <template v-else-if="pillKind === 'cet'">
              <span class="truncate font-semibold">{{ cetRangeText }}</span>
            </template>
            <template v-else>
              <span class="truncate font-semibold">{{ pillFlatText }}</span>
            </template>
          </span>
          <button
            v-if="pillKind === 'cet'"
            class="relative inline-flex h-[18px] shrink-0 items-center rounded-full bg-coral-500/15 px-1.5 text-[10px] font-medium text-coral-300 ring-1 ring-coral-500/30 after:absolute after:-inset-2 after:content-['']"
            aria-label="四六级为参考换算，点开换算说明"
            @click.stop="openScaleInfo($event)"
          >
            参考
          </button>
        </span>
      </div>

      <!-- 切换器 + 换算说明入口 -->
      <div class="mt-4 flex flex-wrap items-center gap-1.5 border-t border-white/10 pt-4">
        <div class="flex flex-wrap items-center gap-1.5" role="radiogroup" aria-label="评分量表">
          <button
            v-for="(s, si) in SCALE_OPTIONS"
            :key="s.id"
            :ref="(el) => (scaleEls[si] = el as HTMLElement | null)"
            role="radio"
            :aria-checked="activeScale === s.id"
            :aria-disabled="!hasScales"
            :tabindex="activeScale === s.id ? 0 : -1"
            class="h-9 rounded-full px-3 text-[11px] font-medium transition duration-[180ms] ease-out sm:h-7 sm:px-2.5"
            :class="[
              activeScale === s.id
                ? 'bg-white/15 text-white ring-1 ring-white/25'
                : 'text-white/50 hover:bg-white/5 hover:text-white/80',
              hasScales ? '' : 'pointer-events-none opacity-40',
            ]"
            @click="pickScale(s.id, $event)"
            @keydown="onScaleKeydown($event, si)"
          >
            {{ s.label }}
          </button>
        </div>
        <button
          class="ml-auto inline-flex items-center gap-1 text-[11px] text-white/45 transition hover:text-white/70"
          @click="openScaleInfo($event)"
        >
          换算说明
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 11v5M12 8.2v.2" stroke-linecap="round" />
          </svg>
        </button>
      </div>
    </div>
  </div>

  <!-- 换算说明：桌面居中卡 / 窄屏底部 sheet -->
  <Transition
    enter-active-class="transition-opacity duration-[160ms] ease-out"
    leave-active-class="transition-opacity duration-[180ms] ease-out"
    enter-from-class="opacity-0"
    leave-to-class="opacity-0"
  >
    <div
      v-if="scaleInfoOpen"
      class="fixed inset-0 z-40 flex items-end justify-center bg-ink/40 backdrop-blur-sm sm:items-center sm:px-4"
      @click.self="closeScaleInfo"
    >
      <div
        ref="scaleInfoEl"
        role="dialog"
        aria-modal="true"
        aria-label="换算说明"
        tabindex="-1"
        class="max-h-[80vh] w-full max-w-md overflow-y-auto rounded-t-card bg-white p-6 shadow-lift ring-1 ring-line/80 sm:rounded-card"
        @keydown="trapScaleInfoFocus"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="sp-section-title">换算说明</div>
          <button class="sp-btn-ghost !p-1.5 text-lg leading-none" aria-label="关闭换算说明" @click="closeScaleInfo">×</button>
        </div>
        <table class="mt-4 w-full text-sm">
          <thead>
            <tr class="text-[11px] text-ink-mute">
              <th class="pb-2 text-left font-medium">量表</th>
              <th class="pb-2 text-right font-medium">本次</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in scaleRows"
              :key="row.id"
              class="rounded-xl"
              :class="row.id === activeScale ? 'bg-brand-50 ring-1 ring-brand-100' : ''"
            >
              <td class="px-2.5 py-2 text-ink-soft">{{ row.label }}</td>
              <td class="px-2.5 py-2 text-right">
                <span class="sp-num text-ink">{{ row.value }}</span>
                <span
                  v-if="row.reference"
                  class="ml-1 inline-flex h-[18px] items-center rounded-full bg-coral-50 px-1.5 text-[10px] font-medium text-coral-700 ring-1 ring-coral-100"
                >参考</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div class="mt-4 space-y-1 text-[11px] leading-5 text-ink-mute">
          <p>雅思↔CEFR：IELTS 官方对照</p>
          <p>托福、多邻国：ETS、DET 官方 CEFR 对照</p>
          <p>四六级：无官方换算，按 425 通过线做水平段</p>
        </div>
        <p class="mt-3 text-right text-[11px] text-ink-mute">换算表版本 {{ scaleVersion }}</p>
      </div>
    </div>
  </Transition>

  <!-- 量表切换的飞行副本落点层：固定覆盖视口，脱离 hero 的层级 -->
  <div ref="ghostLayer" class="pointer-events-none fixed inset-0 z-50" aria-hidden="true"></div>
</template>
