<script setup>
// 学习数据面板：连续打卡、近 12 周热力图、各维度均分雷达、近 7 天可比档位变化。
// 口径见 docs/design.md §19；纯 SVG，不引图表库。
import { computed, onMounted, ref } from 'vue'

import api from '../api/client'
import CountUp from './CountUp.vue'
import EmptyState from './EmptyState.vue'

const data = ref(null)
const failed = ref(false)

onMounted(async () => {
  try {
    const res = await api.get('/me/dashboard', { params: { tz_offset: new Date().getTimezoneOffset() } })
    data.value = res.data
  } catch {
    // 面板只是附加信息，拿不到就不显示，不影响历史列表
    failed.value = true
  }
})

const DIM_LABELS = {
  pronunciation: '发音',
  fluency: '流利度',
  grammar_vocab: '语法词汇',
  task_completion: '任务完成',
  written_expression: '文字表达',
}

// ---------------------------------------------------------------- 热力图
const CELL = 11
const GAP = 3
const LEFT = 18
const TOP = 12
const SHADES = ['#EFEAE1', '#BFE5DD', '#7FCBBD', '#3FAE9B', '#14806F']

function shade(count) {
  if (!count) return SHADES[0]
  if (count <= 1) return SHADES[1]
  if (count <= 3) return SHADES[2]
  if (count <= 6) return SHADES[3]
  return SHADES[4]
}

const heat = computed(() => {
  const days = data.value?.heatmap || []
  if (!days.length) return null
  const cells = days.map((d, i) => {
    const col = Math.floor(i / 7)
    const row = i % 7
    return {
      ...d,
      x: LEFT + col * (CELL + GAP),
      y: TOP + row * (CELL + GAP),
      fill: shade(d.count),
      title: `${d.date}：${d.count ? `练了 ${d.count} 轮` : '没练'}`,
    }
  })
  const cols = Math.ceil(days.length / 7)
  // 月份标在该月第一次出现的那一列上方
  const months = []
  let last = ''
  for (let c = 0; c < cols; c += 1) {
    const d = days[c * 7]
    if (!d) continue
    const m = d.date.slice(5, 7)
    if (m !== last) {
      months.push({ x: LEFT + c * (CELL + GAP), label: `${Number(m)}月` })
      last = m
    }
  }
  return {
    cells,
    months,
    w: LEFT + cols * (CELL + GAP),
    h: TOP + 7 * (CELL + GAP),
  }
})

// ---------------------------------------------------------------- 雷达
const R = 62
const CX = 110
const CY = 86

const radar = computed(() => {
  const dims = data.value?.dimensions || []
  if (dims.length < 3) return null
  const n = dims.length
  const angle = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / n
  const pt = (i, v) => {
    const r = (Math.max(0, Math.min(100, v)) / 100) * R
    return [CX + r * Math.cos(angle(i)), CY + r * Math.sin(angle(i))]
  }
  const poly = (v) => dims.map((_, i) => pt(i, v).map((x) => x.toFixed(1)).join(',')).join(' ')
  return {
    rings: [25, 50, 75, 100].map(poly),
    axes: dims.map((_, i) => pt(i, 100)),
    shape: dims.map((d, i) => pt(i, d.avg).map((x) => x.toFixed(1)).join(',')).join(' '),
    labels: dims.map((d, i) => {
      const [x, y] = pt(i, 122)
      const cos = Math.cos(angle(i))
      return {
        x: x.toFixed(1),
        y: (y + 3).toFixed(1),
        anchor: Math.abs(cos) < 0.3 ? 'middle' : cos > 0 ? 'start' : 'end',
        text: DIM_LABELS[d.name] || d.name,
      }
    }),
  }
})

const weekText = computed(() => {
  const w = data.value?.week
  if (!w || w.recent_band === null) return '近 7 天还没有计分的练习。'
  if (w.delta === null) return `近 7 天平均 雅思 ${w.recent_band.toFixed(1)}（${w.recent_count} 次），再往前 7 天没有计分记录，暂时比不了。`
  const sign = w.delta > 0 ? '高' : w.delta < 0 ? '低' : '持平'
  const diff = Math.abs(w.delta).toFixed(1)
  return w.delta === 0
    ? `近 7 天平均 雅思 ${w.recent_band.toFixed(1)}，与前 7 天持平。`
    : `近 7 天平均 雅思 ${w.recent_band.toFixed(1)}，比前 7 天${sign} ${diff}（${w.recent_count} 次 vs ${w.previous_count} 次）。`
})
</script>

<template>
  <section v-if="data && !failed" class="sp-card p-5 sm:p-6" aria-label="学习数据">
    <div class="flex items-baseline justify-between">
      <div class="font-semibold text-ink">学习数据</div>
      <div class="text-xs text-ink-mute">{{ data.practiced_today ? '今天已练' : '今天还没练' }}</div>
    </div>

    <div class="mt-3 grid grid-cols-3 gap-2 text-center">
      <div class="sp-stat !px-2">
        <div class="sp-num text-2xl font-semibold text-brand-700"><CountUp :value="data.current_streak" /></div>
        <div class="mt-0.5 text-[11px] text-ink-mute">连续天数</div>
      </div>
      <div class="sp-stat !px-2">
        <div class="sp-num text-2xl font-semibold text-ink"><CountUp :value="data.longest_streak" /></div>
        <div class="mt-0.5 text-[11px] text-ink-mute">最长连续</div>
      </div>
      <div class="sp-stat !px-2">
        <div class="sp-num text-2xl font-semibold text-ink"><CountUp :value="data.practice_days" /></div>
        <div class="mt-0.5 text-[11px] text-ink-mute">累计练习天</div>
      </div>
    </div>

    <div v-if="heat" class="mt-4">
      <div class="text-xs font-medium text-ink-soft">近 12 周</div>
      <div class="mt-1 overflow-x-auto">
        <svg :viewBox="`0 0 ${heat.w} ${heat.h}`" class="w-full max-w-[340px]" role="img" aria-label="近 12 周每天练习轮数热力图">
          <g fill="#98A2B3" font-size="8">
            <text v-for="m in heat.months" :key="m.x + m.label" :x="m.x" y="8">{{ m.label }}</text>
            <text x="0" :y="12 + 0 * 14 + 9">一</text>
            <text x="0" :y="12 + 2 * 14 + 9">三</text>
            <text x="0" :y="12 + 4 * 14 + 9">五</text>
          </g>
          <rect
            v-for="c in heat.cells"
            :key="c.date"
            :x="c.x"
            :y="c.y"
            width="11"
            height="11"
            rx="2.5"
            :fill="c.fill"
          >
            <title>{{ c.title }}</title>
          </rect>
        </svg>
      </div>
      <div class="mt-1 flex max-w-[340px] items-center justify-end gap-1 text-[10px] text-ink-mute">
        少
        <span v-for="s in SHADES" :key="s" class="inline-block h-2.5 w-2.5 rounded-sm" :style="{ background: s }"></span>
        多
      </div>
    </div>

    <div class="mt-4 border-t border-line/70 pt-4">
      <div class="text-xs font-medium text-ink-soft">各维度平均分</div>
      <EmptyState
        v-if="!data.dimensions.length"
        compact
        icon="chart"
        title="还没有计分的报告"
        text="完成一次正式计分的练习后，这里会画出各维度雷达。示例报告不计分，也不算进来。"
      />
      <div v-else class="mt-2 flex flex-col items-center gap-3">
        <svg v-if="radar" viewBox="0 0 220 172" class="h-44 w-full max-w-[240px] shrink-0" role="img" aria-label="各维度平均分雷达图，满分 100">
          <polygon v-for="(r, i) in radar.rings" :key="i" :points="r" fill="none" stroke="#E3EAE9" stroke-width="1" />
          <line v-for="(a, i) in radar.axes" :key="`a${i}`" :x1="110" :y1="86" :x2="a[0]" :y2="a[1]" stroke="#E3EAE9" stroke-width="1" />
          <polygon :points="radar.shape" fill="#1F9C89" fill-opacity="0.18" stroke="#1F9C89" stroke-width="1.8" stroke-linejoin="round" />
          <g fill="#475467" font-size="9">
            <text v-for="(l, i) in radar.labels" :key="`l${i}`" :x="l.x" :y="l.y" :text-anchor="l.anchor">{{ l.text }}</text>
          </g>
        </svg>
        <ul class="w-full space-y-1.5 text-xs">
          <li v-for="d in data.dimensions" :key="d.name" class="flex items-center gap-2">
            <span class="w-16 shrink-0 text-ink-soft">{{ DIM_LABELS[d.name] || d.name }}</span>
            <span class="h-1.5 flex-1 overflow-hidden rounded-full bg-line/60">
              <span class="block h-full rounded-full bg-brand-500" :style="{ width: `${Math.min(100, d.avg)}%` }"></span>
            </span>
            <span class="w-9 shrink-0 text-right font-medium text-ink">{{ d.avg.toFixed(0) }}</span>
            <span class="w-10 shrink-0 text-right text-ink-mute">{{ d.samples }} 次</span>
          </li>
        </ul>
      </div>
      <p v-if="data.dimensions.length" class="mt-2 text-[11px] leading-5 text-ink-mute">
        每个维度只在评过它的练习里平均：发音、流利度来自录音，文字表达来自打字，所以次数可能不同。
      </p>
    </div>

    <p class="mt-4 rounded-xl bg-paper px-3.5 py-2.5 text-xs leading-5 text-ink-soft ring-1 ring-line/70">{{ weekText }}</p>
  </section>
</template>
