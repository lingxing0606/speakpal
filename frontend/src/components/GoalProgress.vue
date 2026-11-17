<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { useSessionStore } from '../stores/session'

const session = useSessionStore()

// Agent 本场计划：目标来自场景任务清单，达成由服务端每轮按关键词规则算
const planGoals = computed(() => session.plan?.goals || [])
const planAchieved = computed(() => session.plan?.achieved || [])

// ---- 目标条：吸顶描边、首次展开、达成飞行（规格 1.3）----
const stripScrolled = ref(false)
// chip 的展示态：比服务端数据晚 340ms 翻转，等飞行副本快落地再变形
const shapeAchieved = ref<string[]>([])
const poppingGoals = ref<string[]>([])
const countPulsing = ref(false)
const stripInlineHeight = ref<string | null>(null)
const stripContentShown = ref(true)
const stripEl = ref<HTMLElement | null>(null)
const flightLayer = ref<HTMLElement | null>(null)
const allGoalsDone = computed(() => planGoals.value.length > 0 && planAchieved.value.length >= planGoals.value.length)
const stripBorder = computed(() => {
  if (allGoalsDone.value) return 'border-brand-100'
  return stripScrolled.value ? 'border-line/70' : 'border-transparent'
})

// 副本与脉冲的定时器，离开页面时统一清
const goalTimers: ReturnType<typeof setTimeout>[] = []

function reducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function stripTargetHeight() {
  return window.matchMedia('(min-width: 640px)').matches ? 56 : 48
}

function onPageScroll() {
  stripScrolled.value = window.scrollY > 8
}

// 目标条首次出现：先在同一个 tick 里压到 0 高，下一帧再长到固定高
function beginStripEnter() {
  if (reducedMotion()) return
  stripContentShown.value = false
  stripInlineHeight.value = '0px'
}

function finishStripEnter() {
  if (reducedMotion()) {
    stripContentShown.value = true
    return
  }
  requestAnimationFrame(() => {
    stripInlineHeight.value = `${stripTargetHeight()}px`
    stripContentShown.value = true
  })
  goalTimers.push(
    setTimeout(() => {
      stripInlineHeight.value = null
    }, 260)
  )
}

function measureChip(index: number) {
  const el = stripEl.value?.querySelector(`[data-goal="${index}"]`)
  return el ? el.getBoundingClientRect() : null
}

// 飞行起点：刚到达的 AI 气泡顶部中点；气泡在视口外时退到对话区可视底边上方 24px
function flightSource(anchorEl: HTMLElement | null) {
  const nodes = document.querySelectorAll('[data-role="ai"]')
  const bubble = nodes.length ? nodes[nodes.length - 1].getBoundingClientRect() : null
  if (bubble && bubble.bottom > 0 && bubble.top < window.innerHeight) {
    return { left: bubble.left + bubble.width / 2, top: bubble.top }
  }
  const chat = anchorEl?.getBoundingClientRect()
  const bottom = chat ? Math.min(chat.bottom, window.innerHeight) : window.innerHeight
  const left = chat ? chat.left + chat.width / 2 : window.innerWidth / 2
  return { left, top: bottom - 24 }
}

// 与目标 chip 同尺寸的副本：直线插值 + 中途右弧，420ms 落到 chip 上再淡出
function spawnFlight(goal: string, from: { left: number; top: number }, to: DOMRect | null) {
  const layer = flightLayer.value
  if (!layer || !to) return
  const width = to.width || 88
  const height = to.height || 24
  const el = document.createElement('span')
  el.textContent = goal
  el.className =
    'pointer-events-none absolute inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-full bg-brand-50 px-2.5 text-[11px] font-medium text-brand-700 ring-1 ring-brand-100'
  el.style.position = 'absolute'
  el.style.left = `${from.left - width / 2}px`
  el.style.top = `${from.top}px`
  el.style.width = `${width}px`
  el.style.height = `${height}px`
  el.style.justifyContent = 'center'
  layer.appendChild(el)
  const dx = to.left - (from.left - width / 2)
  const dy = to.top - from.top
  const arc = width * 0.08
  const flight = el.animate(
    [
      { transform: 'translate(0px, 0px) scale(0.96)', opacity: 0.92 },
      { transform: `translate(${dx * 0.5 + arc}px, ${dy * 0.5}px) scale(1.04)`, offset: 0.5, opacity: 1 },
      { transform: `translate(${dx}px, ${dy}px) scale(1)`, opacity: 1 },
    ],
    { duration: 420, easing: 'cubic-bezier(0.3,0.9,0.25,1)', fill: 'forwards' }
  )
  flight.finished.then(
    () => {
      const fade = el.animate([{ opacity: 1 }, { opacity: 0 }], {
        duration: 120,
        easing: 'ease-out',
        fill: 'forwards',
      })
      fade.finished.then(
        () => el.remove(),
        () => el.remove()
      )
    },
    () => el.remove()
  )
}

// 达成飞行：同屏最多 3 个副本，其余只做 chip 变形；间隔 70ms
function animateAchieved(added: string[], anchorEl: HTMLElement | null = null) {
  const goals = planGoals.value
  if (reducedMotion()) {
    shapeAchieved.value = [...new Set([...shapeAchieved.value, ...added])]
    return
  }
  const from = flightSource(anchorEl)
  added.forEach((goal, i) => {
    const index = goals.indexOf(goal)
    const landAt = 420 + i * 70
    const flipAt = Math.max(0, landAt - 80)
    if (i < 3) {
      const to = measureChip(index)
      if (to) goalTimers.push(setTimeout(() => spawnFlight(goal, from, to), i * 70))
    }
    goalTimers.push(
      setTimeout(() => {
        shapeAchieved.value = [...new Set([...shapeAchieved.value, goal])]
        poppingGoals.value = [...poppingGoals.value, goal]
        goalTimers.push(
          setTimeout(() => {
            poppingGoals.value = poppingGoals.value.filter((g) => g !== goal)
          }, 220)
        )
      }, flipAt)
    )
  })
  goalTimers.push(
    setTimeout(() => {
      countPulsing.value = true
      goalTimers.push(
        setTimeout(() => {
          countPulsing.value = false
        }, 200)
      )
    }, 420)
  )
}

/** 直接跟服务端对齐（进页面 / 回填）：chip 立刻就是已达成的样子，不做飞行 */
function syncAchieved(list: string[] | null | undefined) {
  shapeAchieved.value = [...(list || [])]
}

/** 新达成的目标做飞行；没新增就什么都不做（返回新增条数，便于判断） */
function animateNew(achieved: string[] | null | undefined, anchorEl: HTMLElement | null = null) {
  const added = (achieved || []).filter((g) => !shapeAchieved.value.includes(g))
  if (added.length) animateAchieved(added, anchorEl)
  return added.length
}

// 带着 plan 进页面（首页开练 / 刷新回填）：目标条在第一帧就是 0 高，再由 onMounted 展开
if (planGoals.value.length && !reducedMotion()) {
  stripContentShown.value = false
  stripInlineHeight.value = '0px'
}

onMounted(() => {
  window.addEventListener('scroll', onPageScroll, { passive: true })
  onPageScroll()
})

onUnmounted(() => {
  window.removeEventListener('scroll', onPageScroll)
  goalTimers.forEach((t) => clearTimeout(t))
  goalTimers.length = 0
  flightLayer.value?.replaceChildren()
})

defineExpose({ beginStripEnter, finishStripEnter, animateAchieved, animateNew, syncAchieved })
</script>

<template>
  <div
    v-if="planGoals.length"
    ref="stripEl"
    class="sp-goal-strip border-b"
    :class="stripBorder"
    :style="stripInlineHeight ? { height: stripInlineHeight } : undefined"
  >
    <div
      class="sp-shell-narrow flex h-full items-center gap-3 transition-opacity duration-[120ms] ease-out"
      :class="stripContentShown ? 'opacity-100 delay-[60ms]' : 'opacity-0'"
    >
      <div class="shrink-0" aria-live="polite">
        <span class="sr-only">已达成 {{ planAchieved.length }} / 共 {{ planGoals.length }} 个目标</span>
        <div class="flex items-baseline gap-1.5" aria-hidden="true">
          <span class="hidden text-[11px] text-ink-mute sm:inline">本轮目标</span>
          <span
            class="sp-num text-[13px]"
            :class="allGoalsDone ? 'text-brand-700' : 'text-ink'"
            :style="countPulsing ? { animation: 'sp-goal-count 180ms ease-out' } : undefined"
          >
            {{ planAchieved.length }}/{{ planGoals.length }}
          </span>
        </div>
      </div>
      <div
        class="flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto [mask-image:linear-gradient(to_right,transparent,black_12px,black_calc(100%_-_12px),transparent)] [scrollbar-width:none] sm:[mask-image:none] [&::-webkit-scrollbar]:hidden"
      >
        <span
          v-for="(g, gi) in planGoals"
          :key="g"
          :data-goal="gi"
          class="inline-flex h-6 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-[11px] font-medium transition-colors duration-[160ms] ease-out"
          :class="[
            shapeAchieved.includes(g) ? 'bg-brand-50 text-brand-700 ring-1 ring-brand-100' : 'bg-white text-ink-mute ring-1 ring-line',
            poppingGoals.includes(g) ? 'sp-chip-pop' : '',
          ]"
        >
          <span class="relative flex h-3 w-3 shrink-0 items-center justify-center" aria-hidden="true">
            <span
              class="absolute h-2.5 w-2.5 rounded-full ring-1 ring-line transition-opacity duration-[120ms] ease-out"
              :class="shapeAchieved.includes(g) ? 'opacity-0' : 'opacity-100'"
            ></span>
            <span
              class="absolute text-[12px] leading-none transition-opacity duration-[120ms] ease-out"
              :class="shapeAchieved.includes(g) ? 'opacity-100' : 'opacity-0'"
            >✓</span>
          </span>
          {{ g }}
        </span>
      </div>
    </div>
  </div>

  <!-- chip 飞行副本的落点层：固定覆盖视口，脱离吸顶条的层级限制 -->
  <div ref="flightLayer" class="pointer-events-none fixed inset-0 z-50" aria-hidden="true"></div>
</template>
