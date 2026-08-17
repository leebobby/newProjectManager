<template>
  <div class="roadmap-card">
    <div class="roadmap-header">
      <div class="roadmap-title">{{ project.name }}</div>
      <div class="roadmap-meta">
        <span v-if="rangeText">{{ rangeText }}</span>
        <span class="tag" :class="{ alt: project.granularity === 'month' }">
          {{ project.granularity === 'month' ? '月度精度' : '季度精度' }}
        </span>
      </div>
    </div>
    <div v-if="project.description" class="roadmap-desc">{{ project.description }}</div>

    <div v-if="!hasContent" class="empty-hint">暂无阶段和里程碑数据</div>

    <div v-else class="roadmap-scroll">
      <div
        class="roadmap-canvas"
        :style="{
          minWidth: minCanvasWidth + 'px',
          maxWidth: maxCanvasWidth + 'px',
          height: canvasHeight + 'px',
        }"
      >
        <div class="canvas-inner">
          <!-- 年份分组带 -->
          <div class="year-band">
            <div
              v-for="(yg, i) in yearGroups"
              :key="'yg' + yg.year"
              class="year-cell"
              :class="['year-tone-' + (i % 2)]"
              :style="{ left: yg.leftPct, width: yg.widthPct }"
            >
              <span>{{ yg.year }} 年</span>
            </div>
          </div>

          <!-- 阶段连接线 -->
          <div
            v-for="(p, idx) in phasePositions"
            :key="'pc' + idx"
            class="phase-conn"
            :style="{
              left: p.leftPct,
              top: (ANCHOR_CENTER_Y + ANCHOR_R) + 'px',
              height: (AXIS_Y - ANCHOR_CENTER_Y - ANCHOR_R) + 'px',
              background: p.color,
            }"
          />

          <!-- 阶段锚点圆圈 -->
          <div
            v-for="(p, idx) in phasePositions"
            :key="'pa' + idx"
            class="phase-anchor"
            :style="{
              left: p.leftPct,
              top: (ANCHOR_CENTER_Y - ANCHOR_R) + 'px',
              background: p.color,
            }"
          >
            <span class="anchor-label" :class="{ small: p.label.length > 2 }">{{ p.label }}</span>
          </div>

          <!-- 阶段文本块 -->
          <div
            v-for="(p, idx) in phasePositions"
            :key="'pb' + idx"
            class="phase-block"
            :style="{
              left: `calc(${p.leftPct} + 30px)`,
              top: PHASE_BLOCK_TOP + 'px',
            }"
          >
            <div class="phase-title" :style="{ color: p.color }">{{ p.name }}</div>
            <div v-if="p.goalLines.length" class="phase-row"><span class="k">目标：</span></div>
            <div v-for="(line, i) in p.goalLines" :key="'g' + i" class="phase-row">{{ line }}</div>
            <div v-if="p.core_products" class="phase-row gap">
              <span class="k">核心产品：</span>{{ p.core_products }}
            </div>
            <template v-if="p.scenarioLines.length">
              <div class="phase-row gap"><span class="k">主要应用场景：</span></div>
              <div v-for="(line, i) in p.scenarioLines" :key="'s' + i" class="phase-row">{{ line }}</div>
            </template>
          </div>

          <!-- 时间轴主线 + 箭头 -->
          <div class="axis" :style="{ top: AXIS_Y + 'px' }">
            <div class="axis-arrow" />
          </div>

          <!-- 月份连接虚线 + 圆点 -->
          <template v-for="m in monthList" :key="'m' + m.abs">
            <div
              class="month-line"
              :style="{ left: m.leftPct, top: (AXIS_Y + 5) + 'px' }"
            />
            <div
              class="month-dot"
              :style="{ left: m.leftPct, top: (AXIS_Y - 5) + 'px' }"
            />
            <div
              class="month-label"
              :style="{ left: m.leftPct, top: MONTH_LABEL_Y + 'px' }"
            >
              {{ m.month }}月
            </div>
          </template>

          <!-- 里程碑卡片 -->
          <div
            v-for="(ms, idx) in milestonePositions"
            :key="'ms' + idx"
            class="milestone-block"
            :style="{
              left: ms.leftPct,
              top: MILESTONE_TOP + 'px',
            }"
          >
            <div v-if="ms.title" class="product">{{ ms.title }}</div>
            <div v-else class="product empty">·</div>
            <div v-if="ms.descLines.length" class="desc">
              <div v-for="(line, i) in ms.descLines" :key="'d' + i">{{ line }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  project: { type: Object, required: true },
})

// --- 布局常量（像素，相对于 canvas-inner 顶部）---
const Y_BAND_HEIGHT = 26
const PHASE_BLOCK_TOP = 50
const ANCHOR_CENTER_Y = 220
const ANCHOR_R = 22
const AXIS_Y = 305
const MONTH_LINE_HEIGHT = 50
const MONTH_LABEL_Y = AXIS_Y + 55
const MILESTONE_TOP = MONTH_LABEL_Y + 25

// 每月最小/最大宽度（px），用于自适应 canvas 宽度
const MIN_SLOT_WIDTH = 110
const MAX_SLOT_WIDTH = 180
const PAD_LR = 60 // canvas 左右内边距（像素，加在 min/max 上）

function absOf(year, month) {
  return year * 12 + (month - 1)
}

// --- 计算月份范围 ---
const monthRange = computed(() => {
  const phases = props.project.phases || []
  const milestones = props.project.milestones || []
  const all = []
  for (const p of phases) {
    if (p.start_year && p.start_month) all.push(absOf(p.start_year, p.start_month))
    if (p.end_year && p.end_month) all.push(absOf(p.end_year, p.end_month))
  }
  for (const m of milestones) {
    if (m.year && m.month) all.push(absOf(m.year, m.month))
  }
  if (!all.length) {
    const y = new Date().getFullYear()
    return { minAbs: absOf(y, 1), maxAbs: absOf(y, 12), count: 12 }
  }
  const minAbs = Math.min(...all)
  const maxAbs = Math.max(...all)
  return { minAbs, maxAbs, count: maxAbs - minAbs + 1 }
})

const monthList = computed(() => {
  const { minAbs, count } = monthRange.value
  const list = []
  for (let i = 0; i < count; i++) {
    const abs = minAbs + i
    const year = Math.floor(abs / 12)
    const month = (abs % 12) + 1
    list.push({ abs, year, month, leftPct: pctOf(abs) })
  }
  return list
})

// 把绝对月转成 inner 的百分比（左为 0%，右为 100%）。中心位置。
function pctOf(absMonth) {
  const { minAbs, count } = monthRange.value
  return ((absMonth - minAbs + 0.5) / count) * 100 + '%'
}

const rangeText = computed(() => {
  const list = monthList.value
  if (!list.length) return ''
  const f = list[0]
  const l = list[list.length - 1]
  if (f.year === l.year) return `${f.year} 年 ${f.month}–${l.month} 月`
  return `${f.year}.${f.month} — ${l.year}.${l.month}`
})

const hasContent = computed(
  () => (props.project.phases?.length || 0) + (props.project.milestones?.length || 0) > 0
)

// --- 年份分组 ---
const yearGroups = computed(() => {
  const { minAbs, count } = monthRange.value
  const groups = []
  let cur = null
  for (let i = 0; i < count; i++) {
    const abs = minAbs + i
    const year = Math.floor(abs / 12)
    if (!cur || cur.year !== year) {
      if (cur) groups.push(cur)
      cur = { year, startIdx: i, endIdx: i }
    } else {
      cur.endIdx = i
    }
  }
  if (cur) groups.push(cur)
  return groups.map((g) => ({
    year: g.year,
    leftPct: (g.startIdx / count) * 100 + '%',
    widthPct: ((g.endIdx - g.startIdx + 1) / count) * 100 + '%',
  }))
})

// --- 阶段（以起始月份定位锚点）---
const phasePositions = computed(() => {
  const list = props.project.phases || []
  return list.map((p) => {
    const abs = absOf(p.start_year, p.start_month)
    const label = props.project.granularity === 'month'
      ? `${p.start_month}月`
      : `Q${Math.ceil(p.start_month / 3)}`
    return {
      leftPct: pctOf(abs),
      label,
      name: p.name,
      color: p.color || '#409EFF',
      goalLines: (p.goal || '').split('\n').map((s) => s.trim()).filter(Boolean),
      core_products: p.core_products || '',
      scenarioLines: (p.scenarios || '').split('\n').map((s) => s.trim()).filter(Boolean),
    }
  })
})

const milestonePositions = computed(() => {
  const list = props.project.milestones || []
  return list.map((m) => ({
    leftPct: pctOf(absOf(m.year, m.month)),
    title: m.title || '',
    descLines: (m.description || '').split('\n').map((s) => s.trim()).filter(Boolean),
  }))
})

// --- canvas 尺寸：根据月份数动态计算 min/max width ---
const minCanvasWidth = computed(() => monthRange.value.count * MIN_SLOT_WIDTH + PAD_LR * 2)
const maxCanvasWidth = computed(() => monthRange.value.count * MAX_SLOT_WIDTH + PAD_LR * 2)

const canvasHeight = computed(() => {
  let maxPhaseLines = 0
  for (const p of phasePositions.value) {
    let lines = 1
    if (p.goalLines.length) lines += 1 + p.goalLines.length
    if (p.core_products) lines += 1
    if (p.scenarioLines.length) lines += 1 + p.scenarioLines.length
    if (lines > maxPhaseLines) maxPhaseLines = lines
  }
  let maxMilestoneLines = 0
  for (const m of milestonePositions.value) {
    const lines = (m.title ? 1 : 0) + m.descLines.length + 1
    if (lines > maxMilestoneLines) maxMilestoneLines = lines
  }
  const phaseBottom = PHASE_BLOCK_TOP + 28 + maxPhaseLines * 20 + 10
  const phaseSection = Math.max(AXIS_Y - 5, phaseBottom)
  const milestoneSection = MILESTONE_TOP + Math.max(40, maxMilestoneLines * 18 + 30)
  return Math.max(phaseSection + 80, milestoneSection + 20, 500)
})
</script>

<style scoped>
.roadmap-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
  padding: 20px 24px 24px;
}
.roadmap-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #ebeef5;
  padding-bottom: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
  gap: 8px;
}
.roadmap-title {
  font-size: 16px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 10px;
}
.roadmap-title::before {
  content: '';
  display: inline-block;
  width: 4px;
  height: 16px;
  background: #409EFF;
  border-radius: 2px;
}
.roadmap-meta {
  font-size: 12px;
  color: #909399;
  display: flex;
  gap: 8px;
  align-items: center;
}
.roadmap-meta .tag {
  padding: 2px 8px;
  border-radius: 3px;
  background: #f0f7ff;
  color: #409EFF;
  font-size: 11px;
}
.roadmap-meta .tag.alt {
  background: #fef0e7;
  color: #e6a23c;
}
.roadmap-desc {
  font-size: 12px;
  color: #909399;
  margin-bottom: 16px;
  line-height: 1.7;
}
.empty-hint {
  text-align: center;
  color: #c0c4cc;
  padding: 40px 0;
  font-size: 13px;
}

.roadmap-scroll {
  overflow-x: auto;
}
.roadmap-canvas {
  position: relative;
  width: 100%;
  margin: 0 auto;
}
.canvas-inner {
  position: absolute;
  left: 60px;
  right: 60px;
  top: 0;
  bottom: 0;
}

/* 年份分组带 */
.year-band {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  height: 26px;
  pointer-events: none;
}
.year-cell {
  position: absolute;
  top: 0;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: #606266;
  border-radius: 4px;
  letter-spacing: 0.5px;
}
.year-tone-0 {
  background: #ecf5ff;
  color: #409EFF;
}
.year-tone-1 {
  background: #f0f9eb;
  color: #67c23a;
}

/* 时间轴 */
.axis {
  position: absolute;
  left: -10px;
  right: -10px;
  height: 2px;
  background: #cbd5e0;
}
.axis-arrow {
  position: absolute;
  right: -8px;
  top: -6px;
  width: 0;
  height: 0;
  border-style: solid;
  border-width: 7px 0 7px 12px;
  border-color: transparent transparent transparent #cbd5e0;
}

/* 月份点和连接线 */
.month-dot {
  position: absolute;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #fff;
  border: 2px solid #cbd5e0;
  transform: translateX(-50%);
  box-sizing: border-box;
}
.month-line {
  position: absolute;
  width: 1px;
  height: 50px;
  background-image: linear-gradient(#cbd5e0 50%, transparent 0);
  background-size: 1px 6px;
  transform: translateX(-50%);
}
.month-label {
  position: absolute;
  font-size: 13px;
  color: #303133;
  font-weight: 500;
  transform: translateX(-50%);
  white-space: nowrap;
}

/* 阶段锚点圆圈 */
.phase-anchor {
  position: absolute;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
}
.anchor-label {
  color: #fff;
  font-size: 14px;
  font-weight: 600;
}
.anchor-label.small {
  font-size: 11px;
}

/* 阶段连接线 */
.phase-conn {
  position: absolute;
  width: 1.5px;
  transform: translateX(-50%);
}

/* 阶段文本块 */
.phase-block {
  position: absolute;
  width: 260px;
  max-width: 280px;
  pointer-events: none;
}
.phase-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 8px;
}
.phase-row {
  font-size: 12px;
  line-height: 1.7;
  color: #606266;
}
.phase-row .k {
  color: #303133;
  font-weight: 500;
}
.phase-row.gap {
  margin-top: 6px;
}

/* 里程碑卡片 */
.milestone-block {
  position: absolute;
  width: 130px;
  transform: translateX(-50%);
  text-align: center;
  pointer-events: none;
}
.milestone-block .product {
  display: inline-block;
  border: 1.5px solid #409EFF;
  color: #409EFF;
  padding: 5px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  background: #fff;
  min-width: 95px;
  margin-bottom: 8px;
}
.milestone-block .product.empty {
  visibility: hidden;
  margin-bottom: 0;
}
.milestone-block .desc {
  font-size: 11px;
  color: #909399;
  line-height: 1.6;
  padding: 0 4px;
}
</style>
