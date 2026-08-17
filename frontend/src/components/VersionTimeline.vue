<template>
  <div class="vt-wrap">
    <div class="vt-bar">
      <span class="vt-bar-label">时间范围</span>
      <el-select v-model="rangeMonths" size="small" style="width: 110px">
        <el-option label="全部" :value="0" />
        <el-option label="近 3 月" :value="3" />
        <el-option label="近 6 月" :value="6" />
        <el-option label="近 1 年" :value="12" />
      </el-select>
      <span class="vt-bar-hint">最新大版本为主线，旧版本从对应时间点拉枝；节点为迭代版本（悬停看详情）</span>
    </div>

    <div v-if="layout.empty" class="vt-empty">
      暂无可绘制的版本：大版本需至少有「版本范围开始」或迭代版本的「预计发布日期」才能定位到时间轴。
    </div>
    <template v-else>
      <svg
        class="vt-svg"
        :viewBox="`0 0 ${W} ${layout.height}`"
        :style="{ height: layout.height + 'px' }"
        preserveAspectRatio="xMinYMin meet"
      >
        <!-- 月份网格 -->
        <g class="vt-grid">
          <template v-for="t in layout.months" :key="t.x">
            <line :x1="t.x" :y1="layout.top - 6" :x2="t.x" :y2="layout.axisY" />
            <text :x="t.x" :y="layout.axisY + 16" text-anchor="middle">{{ t.label }}</text>
          </template>
        </g>

        <!-- 今天 -->
        <g v-if="layout.todayX != null" class="vt-today">
          <line :x1="layout.todayX" :y1="layout.top - 6" :x2="layout.todayX" :y2="layout.axisY" />
          <text :x="layout.todayX" :y="layout.top - 10" text-anchor="middle">今天</text>
        </g>

        <!-- 每个大版本：主线 or 支线 -->
        <g v-for="mv in layout.majors" :key="mv.id">
          <path
            v-if="!mv.isMain"
            :d="mv.branchPath"
            class="vt-branch-link"
            :stroke="mv.color"
            fill="none"
          />
          <line
            v-if="mv.isMain && mv.preX != null"
            :x1="mv.preX" :y1="mv.y" :x2="mv.startX" :y2="mv.y"
            class="vt-main-dash" :stroke="mv.color"
          />
          <line
            v-if="mv.isMain && mv.postX != null"
            :x1="mv.endX" :y1="mv.y" :x2="mv.postX" :y2="mv.y"
            class="vt-main-dash" :stroke="mv.color"
          />
          <line
            :x1="mv.startX" :y1="mv.y" :x2="mv.endX" :y2="mv.y"
            :stroke="mv.color" :stroke-width="mv.isMain ? 5 : 3" stroke-linecap="round"
          />
          <circle
            :cx="mv.endX" :cy="mv.y" :r="mv.isMain ? 6 : 5"
            :fill="mv.released ? mv.color : '#fff'" :stroke="mv.color" stroke-width="2"
          >
            <title>{{ mv.version_no }} {{ mv.released ? '已发布 ' + mv.releaseLabel : '计划至 ' + mv.endLabel }}</title>
          </circle>

          <!-- 迭代版本节点：标签上下交错 + 重叠自动隐藏（仍可悬停） -->
          <g v-for="n in mv.nodes" :key="n.id">
            <circle :cx="n.x" :cy="mv.y" r="4" :fill="mv.color">
              <title>{{ n.version_no }} {{ n.title }} · {{ n.dateLabel }}</title>
            </circle>
            <template v-if="n.showLabel">
              <line
                v-if="!n.above"
                :x1="n.x" :y1="mv.y + 4" :x2="n.x" :y2="mv.y + 11"
                class="vt-leader"
              />
              <text
                :x="n.x" :y="n.above ? mv.y - 9 : mv.y + 22"
                text-anchor="middle" class="vt-node-label"
              >{{ n.version_no }}</text>
            </template>
          </g>

          <!-- 大版本标签 -->
          <g>
            <rect
              :x="mv.labelX" :y="mv.y - 11" :width="mv.labelW" height="18" rx="9"
              :fill="mv.isMain ? mv.color : '#fff'" :stroke="mv.color"
            />
            <text
              :x="mv.labelX + mv.labelW / 2" :y="mv.y + 2" text-anchor="middle"
              class="vt-major-label" :fill="mv.isMain ? '#fff' : mv.color"
            >{{ mv.isMain ? '主线 ' : '' }}{{ mv.version_no }}</text>
            <title>{{ mv.version_no }} {{ mv.title }}</title>
          </g>
        </g>
      </svg>

      <div v-if="layout.skipped.length" class="vt-skipped">
        未上图（缺少日期）：{{ layout.skipped.join('、') }}
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { fmtDate } from '../utils/format'

const props = defineProps({
  majors: { type: Array, default: () => [] },
})

const W = 960
const PALETTE = ['#409EFF', '#67C23A', '#E6A23C', '#F56C6C', '#9B59B6', '#1ABC9C', '#909399']
const rangeMonths = ref(0)   // 0=全部；3/6/12=只看最近 N 个月

function ts(d) {
  if (!d) return null
  const t = new Date(d).getTime()
  return Number.isNaN(t) ? null : t
}

const layout = computed(() => {
  const padL = 40
  const padR = 28
  const top = 34
  const laneGap = 64

  // 1) 解析每个大版本的起止 + 迭代节点日期
  const raw = props.majors.map((m) => {
    const iters = (m.iteration_versions || [])
      .map((iv) => ({ id: iv.id, version_no: iv.version_no, title: iv.title || '', t: ts(iv.planned_date) }))
      .filter((iv) => iv.t != null)
      .sort((a, b) => a.t - b.t)
    const iterTs = iters.map((iv) => iv.t)
    const startT = ts(m.range_start) ?? (iterTs.length ? Math.min(...iterTs) : null)
    const relT = ts(m.actual_release_date)
    const endT = relT ?? ts(m.range_end) ?? (iterTs.length ? Math.max(...iterTs) : startT)
    return { m, iters, startT, endT, relT }
  })

  let placeable = raw.filter((r) => r.startT != null)
  const skipped = raw.filter((r) => r.startT == null).map((r) => r.m.version_no)
  if (!placeable.length) return { empty: true, skipped }

  // 2) 数据时间范围
  const allT = []
  placeable.forEach((r) => {
    allT.push(r.startT, r.endT ?? r.startT)
    r.iters.forEach((iv) => allT.push(iv.t))
  })
  const dataMin = Math.min(...allT)
  const dataMax = Math.max(...allT)

  // 「近 N 月」：以 max(数据最晚, 今天) 为锚回退 N 个月
  let clipMin = dataMin
  if (rangeMonths.value > 0) {
    const anchor = Math.max(dataMax, Date.now())
    const c = new Date(anchor)
    c.setMonth(c.getMonth() - rangeMonths.value)
    clipMin = Math.max(dataMin, c.getTime())
    // 整段落在窗口左侧之外的版本不再展示
    placeable = placeable.filter((r) => (r.endT ?? r.startT) >= clipMin)
    if (!placeable.length) return { empty: true, skipped }
  }

  let minT = clipMin
  let maxT = dataMax
  if (minT === maxT) { minT -= 15 * 864e5; maxT += 15 * 864e5 }
  const span = maxT - minT
  minT -= span * 0.04
  maxT += span * 0.04
  const xOf = (t) => padL + ((Math.max(t, clipMin) - minT) / (maxT - minT)) * (W - padL - padR)

  // 3) 排序：最新（起始最晚）在最上 = 主线
  placeable.sort((a, b) => {
    if (b.startT !== a.startT) return b.startT - a.startT
    return String(b.m.version_no).localeCompare(String(a.m.version_no), 'zh-Hans-CN', { numeric: true })
  })

  const mainY = top + 12
  const majors = placeable.map((r, i) => {
    const color = PALETTE[i % PALETTE.length]
    const y = mainY + i * laneGap
    const startX = xOf(r.startT)
    const endX = xOf(r.endT ?? r.startT)
    const isMain = i === 0
    const labelText = (isMain ? '主线 ' : '') + (r.m.version_no || '')
    const labelW = Math.max(34, labelText.length * 8 + 14)
    let labelX = startX - labelW - 8
    if (labelX < 2) labelX = startX + 8

    // 迭代节点：标签上下交错（even=上 / odd=下），同一行内重叠则隐藏标签
    let aboveR = -1e9
    let belowR = -1e9
    const nodes = r.iters
      .filter((iv) => iv.t >= clipMin)
      .map((iv, k) => {
        const x = xOf(iv.t)
        const halfW = (String(iv.version_no || '').length * 5) / 2
        const above = k % 2 === 0
        let showLabel = true
        if (above) {
          if (x - halfW < aboveR + 4) showLabel = false
          else aboveR = x + halfW
        } else {
          if (x - halfW < belowR + 4) showLabel = false
          else belowR = x + halfW
        }
        return { id: iv.id, version_no: iv.version_no, title: iv.title, x, dateLabel: fmtDate(iv.t), above, showLabel }
      })

    const out = {
      id: r.m.id, version_no: r.m.version_no, title: r.m.title || '',
      color, y, startX, endX, isMain, nodes, labelX, labelW,
      released: r.relT != null, releaseLabel: fmtDate(r.relT), endLabel: fmtDate(r.endT),
    }
    if (isMain) {
      out.preX = startX > padL + 1 ? padL : null
      out.postX = endX < W - padR - 1 ? W - padR : null
    } else {
      out.branchPath = `M ${startX},${mainY} C ${startX},${mainY + 24} ${startX + 18},${y - 24} ${startX + 18},${y}`
      out.startX = startX + 18
    }
    return out
  })

  // 4) 月份网格
  const months = []
  const d = new Date(minT); d.setDate(1); d.setHours(0, 0, 0, 0)
  while (d.getTime() <= maxT) {
    const t = d.getTime()
    if (t >= minT) {
      const m = d.getMonth() + 1
      months.push({ x: xOf(t), label: m === 1 ? `${d.getFullYear()}/1` : `${m}月` })
    }
    d.setMonth(d.getMonth() + 1)
  }

  const axisY = mainY + (majors.length - 1) * laneGap + 32
  const nowT = Date.now()
  const todayX = nowT >= minT && nowT <= maxT ? xOf(nowT) : null

  return { empty: false, skipped, majors, months, top, axisY, todayX, height: axisY + 24 }
})
</script>

<style scoped>
.vt-wrap {
  width: 100%;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 8px 10px 4px;
  margin-bottom: 12px;
}
.vt-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.vt-bar-label { font-size: 13px; color: #606266; }
.vt-bar-hint { color: #c0c4cc; font-size: 12px; margin-left: 4px; }
.vt-svg { width: 100%; min-width: 720px; display: block; overflow: visible; }
.vt-empty { color: #909399; font-size: 13px; padding: 18px 8px; }
.vt-grid line { stroke: #f0f2f5; stroke-width: 1; }
.vt-grid text { fill: #c0c4cc; font-size: 11px; }
.vt-today line { stroke: #f56c6c; stroke-width: 1; stroke-dasharray: 3 3; }
.vt-today text { fill: #f56c6c; font-size: 10px; }
.vt-branch-link { stroke-width: 2; opacity: 0.7; }
.vt-main-dash { stroke-width: 2; stroke-dasharray: 4 4; opacity: 0.45; }
.vt-leader { stroke: #dcdfe6; stroke-width: 1; }
.vt-node-label { fill: #606266; font-size: 9px; }
.vt-major-label { font-size: 11px; font-weight: 600; }
.vt-skipped { color: #c0c4cc; font-size: 12px; padding: 2px 4px 4px; }
</style>
