<template>
  <div class="vt-wrap">
    <div class="vt-bar">
      <span class="vt-bar-label">时间范围</span>
      <el-select v-model="rangeMonths" size="small" style="width: 150px">
        <el-option label="全部（自动收窄）" :value="0" />
        <el-option label="近 3 月" :value="3" />
        <el-option label="近 6 月" :value="6" />
        <el-option label="近 1 年" :value="12" />
        <el-option label="按月份区间…" :value="-1" />
      </el-select>
      <!-- 「全部」会把横轴收窄到有内容的时间段，这个按月挑的区间就是看完整声明
           范围的退路（也用来只盯某几个月的版本）。没选够两头时退回「全部」的口径，
           而不是画一张空图 -->
      <el-date-picker
        v-if="rangeMonths === -1"
        v-model="monthRange"
        type="monthrange"
        size="small"
        style="width: 230px"
        range-separator="~"
        start-placeholder="起始月"
        end-placeholder="结束月"
      />

      <span class="vt-bar-label">节点粒度</span>
      <el-select v-model="level" size="small" style="width: 150px">
        <el-option label="只看大版本" value="major" />
        <el-option label="版本" value="release" />
        <el-option label="迭代版本（B 版）" value="iteration" />
      </el-select>

      <el-dropdown size="small" @command="onExport">
        <el-button size="small" :icon="Download" :loading="exporting">导出图</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="png">PNG 图片（贴 PPT / 邮件）</el-dropdown-item>
            <el-dropdown-item command="svg">SVG 矢量图（放大不糊）</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <span class="vt-bar-hint">{{ hint }}</span>
    </div>

    <div v-if="layout.empty" class="vt-empty">
      暂无可绘制的版本：大版本需至少有「版本范围开始」，或其下版本填了「计划发布 / 实际发布」，才能定位到时间轴。
    </div>
    <template v-else>
      <svg
        ref="svgRef"
        class="vt-svg"
        :viewBox="`0 0 ${W} ${layout.height}`"
        :style="{ height: layout.height + 'px' }"
        preserveAspectRatio="xMinYMin meet"
        xmlns="http://www.w3.org/2000/svg"
        :font-family="FONT"
      >
        <!-- 画笔（颜色 / 线宽 / 字号）一律写成**元素属性**，不走 <style scoped>：
             一是 scoped CSS 靠 data-v 属性挂在页面 DOM 上，序列化出去的那份 svg 带不走它，
             表现是"页面上好好的，导出来网格线和文字全变成黑的默认色"；
             二是 Vue 的模板编译器会把模板里的 <style> 当副作用标签整个丢掉，
             所以也不能把样式塞进 svg 内部的 <style> 里。属性是唯一两边都成立的写法 -->

        <!-- 月份网格 -->
        <g>
          <template v-for="t in layout.months" :key="t.x">
            <line :x1="t.x" :y1="layout.top - 6" :x2="t.x" :y2="layout.axisY" :stroke="C.grid" stroke-width="1" />
            <text :x="t.x" :y="layout.axisY + 16" text-anchor="middle" :fill="C.axisText" font-size="11">{{ t.label }}</text>
          </template>
        </g>

        <!-- 今天 -->
        <g v-if="layout.todayX != null">
          <line
            :x1="layout.todayX" :y1="layout.top - 6" :x2="layout.todayX" :y2="layout.axisY"
            :stroke="C.today" stroke-width="1" stroke-dasharray="3 3"
          />
          <text :x="layout.todayX" :y="layout.top - 10" text-anchor="middle" :fill="C.today" font-size="10">今天</text>
        </g>

        <!-- 每个大版本：主线 or 支线 -->
        <g v-for="mv in layout.majors" :key="mv.id">
          <path
            v-if="!mv.isMain"
            :d="mv.branchPath"
            :stroke="mv.color"
            stroke-width="2"
            opacity="0.7"
            fill="none"
          />
          <line
            v-if="mv.isMain && mv.preX != null"
            :x1="mv.preX" :y1="mv.y" :x2="mv.startX" :y2="mv.y"
            :stroke="mv.color" stroke-width="2" stroke-dasharray="4 4" opacity="0.45"
          />
          <line
            :x1="mv.startX" :y1="mv.y" :x2="mv.endX" :y2="mv.y"
            :stroke="mv.color" :stroke-width="mv.isMain ? 5 : 3" stroke-linecap="butt"
          />
          <!-- 起点在窗口之外：标 « 而不是让线贴着左边缘——贴边看着像"这个大版本
               就是从这天开始的"，而它其实更早 -->
          <text
            v-if="mv.clipped"
            :x="mv.startX - 7" :y="mv.y + 4" text-anchor="end"
            :fill="mv.color" font-size="13" font-weight="600"
          >
            «
            <title>{{ mv.version_no }} 的开始时间早于当前时间范围，线是从窗口左边缘画起的</title>
          </text>
          <!-- 收尾用箭头不用圆点：圆点是"到此为止"，而版本线的末端是"还在往前走"。
               线本身已经比最后一个节点多伸了 TAIL_DAYS 天，最后那个版本就不会正好
               压在端点上、看着像被截断 -->
          <polygon
            :points="`${mv.endX},${mv.y - (mv.isMain ? 6 : 5)} ${mv.endX},${mv.y + (mv.isMain ? 6 : 5)} ${mv.endX + (mv.isMain ? 12 : 10)},${mv.y}`"
            :fill="mv.color"
          >
            <title>{{ mv.version_no }} {{ mv.released ? '已发布 ' + mv.releaseLabel : '计划至 ' + mv.endLabel }}（线尾多画 {{ TAIL_DAYS }} 天，不代表计划到这天）</title>
          </polygon>

          <!-- 版本节点：标签上下交错 + 重叠自动隐藏（仍可悬停） -->
          <!-- 未发布＝**换色**（琥珀实心），不再是空心圈：空心在缩小和打印时几乎看不见，
               而"这个版本还没发"恰恰是看这张图的人最想一眼扫到的事。琥珀已经从泳道
               配色里摘掉了，所以它永远不会和某条泳道的已发布节点撞色 -->
          <g v-for="n in mv.nodes" :key="n.id">
            <circle
              :cx="n.x" :cy="mv.y" :r="mv.nodeR"
              :fill="n.released ? mv.color : PLANNED"
              :stroke="n.released ? mv.color : PLANNED" stroke-width="1.5"
            >
              <title>{{ n.version_no }} {{ n.title }} · {{ n.released ? '已发布 ' : '计划 ' }}{{ n.dateLabel }}{{ n.sub }}</title>
            </circle>
            <template v-if="n.showLabel">
              <line
                v-if="!n.above"
                :x1="n.x" :y1="mv.y + layout.leadFrom" :x2="n.x" :y2="mv.y + layout.leadTo"
                :stroke="C.leader" stroke-width="1"
              />
              <text
                :x="n.x" :y="n.above ? mv.y - layout.labelUp : mv.y + layout.labelDown"
                text-anchor="middle" :fill="n.released ? C.nodeLabel : PLANNED"
                :font-size="layout.labelFS"
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
              font-size="11" font-weight="600" :fill="mv.isMain ? '#fff' : mv.color"
            >{{ mv.isMain ? '主干 ' : '' }}{{ mv.version_no }}</text>
            <title>{{ mv.version_no }} {{ mv.title }}</title>
          </g>
        </g>

        <!-- 图例画进 svg 里，导出的那张图才带得走「琥珀＝还没发布」这条说明 -->
        <g v-if="layout.showLegend">
          <circle cx="40" :cy="layout.legendY - 4" r="4" :fill="layout.legendColor" />
          <text x="50" :y="layout.legendY" :fill="C.nodeLabel" font-size="10">已发布（取所在大版本的颜色）</text>
          <circle cx="212" :cy="layout.legendY - 4" r="4" :fill="PLANNED" />
          <text x="222" :y="layout.legendY" :fill="PLANNED" font-size="10">计划中，未发布</text>
        </g>
      </svg>

      <div v-if="layout.skipped.length" class="vt-skipped">
        未上图（缺少日期）：{{ layout.skipped.join('、') }}
      </div>
      <!-- 少画了几个节点要如实说：只筛不报的表现是"这个版本怎么不在图上" -->
      <div v-if="layout.nodeSkipped" class="vt-skipped">
        另有 {{ layout.nodeSkipped }} 个{{ LEVEL_LABEL[level] }}没填发布日期，画不到轴上。
      </div>
      <div v-if="layout.nodeClipped" class="vt-skipped">
        另有 {{ layout.nodeClipped }} 个{{ LEVEL_LABEL[level] }}落在当前时间范围之外，
        换个时间范围就能看到。
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { fmtDate } from '../utils/format'
import { downloadBlob } from '../api'

const props = defineProps({
  majors: { type: Array, default: () => [] },
})

const W = 960
// 琥珀 #E6A23C 从泳道配色里**摘掉了**，专门留给「计划中未发布」的节点。
// 不摘的话，落在琥珀色泳道上的已发布节点会和未发布节点同色，而那一条泳道
// 单独看完全正常——最难被当成 bug 报的那类
const PALETTE = ['#409EFF', '#67C23A', '#F56C6C', '#9B59B6', '#1ABC9C', '#909399']
const PLANNED = '#E6A23C'
// 线尾比最后一个节点多伸的天数。**只是画法，不是数据**：范围结束时间没有被改写，
// 箭头的 tooltip 里写的仍是真正的结束日期
const TAIL_DAYS = 5
// 「全部」时横轴收窄到有内容的区间，头上留这么多天，第一个节点才不贴着左边缘
const HEAD_PAD_DAYS = 14
// 图上节点不超过这么多个就整体放大一档（泳道拉高、点变粗、字号变大）
const SPARSE_NODE_MAX = 12
const LEVEL_LABEL = { major: '大版本', release: '版本', iteration: '迭代版本' }

// 图上非节点部分的颜色。写在这儿而不是 <style scoped> 里，模板按属性绑上去，
// 导出的 svg 才带得走（见模板里的说明）
const C = { grid: '#f0f2f5', axisText: '#c0c4cc', today: '#f56c6c', leader: '#dcdfe6', nodeLabel: '#606266' }
const FONT = '"Microsoft YaHei", "PingFang SC", "Helvetica Neue", Arial, sans-serif'

// 0=全部（横轴自动收窄到有内容的区间）；3/6/12=近 N 月；-1=自定义月份区间
const rangeMonths = ref(0)
const monthRange = ref(null) // [Date, Date]，rangeMonths === -1 时生效
const level = ref('release') // 节点画到哪一层：major=不画节点 / release=版本 / iteration=迭代版本
const svgRef = ref(null)

function ts(d) {
  if (!d) return null
  const t = new Date(d).getTime()
  return Number.isNaN(t) ? null : t
}

// 一个版本/迭代版本落在轴上的时间：发了按实际发布日，没发按计划日
function nodeTs(v) {
  return ts(v.actual_release_date) ?? ts(v.planned_date)
}

/**
 * 用户**显式**指定的横轴窗口；返回 null ＝ 没指定，交给「只画有内容的时间段」。
 *
 * 这两条路不能合并：显式选了范围就该原样画出来（哪怕大半是空的），那是查看
 * 完整声明范围的唯一入路；没选时才自动收窄。合成一条的表现是"我明明选了
 * 2024 年 1 月，图却从 2026 年 3 月开始"。
 */
function explicitWindow(dataMax) {
  if (rangeMonths.value === -1) {
    const r = monthRange.value
    if (!r || !r[0] || !r[1]) return null
    const lo = new Date(r[0]); lo.setDate(1); lo.setHours(0, 0, 0, 0)
    // 结束月要含到**月末**，选「6月」却画到 6/1 会把整月的版本挡在外面
    const hi = new Date(r[1]); hi.setMonth(hi.getMonth() + 1); hi.setDate(0); hi.setHours(23, 59, 59, 999)
    return { lo: lo.getTime(), hi: hi.getTime() }
  }
  if (rangeMonths.value > 0) {
    const anchor = Math.max(dataMax, Date.now())
    const c = new Date(anchor)
    c.setMonth(c.getMonth() - rangeMonths.value)
    return { lo: c.getTime(), hi: Infinity }
  }
  return null
}

const hint = computed(() => {
  const scope = rangeMonths.value === 0
    ? '横轴已收窄到有内容的时间段（起点更早的泳道左端标 «，要看完整范围请按月份区间选）'
    : '横轴按所选时间范围铺满'
  const base = '主干大版本画成主线，分支从拉出时间点拉枝'
  if (level.value === 'major') return `${base}；当前只画大版本的起止，不画节点。${scope}`
  return `${base}；节点为${LEVEL_LABEL[level.value]}（悬停看详情），琥珀＝计划中未发布。${scope}`
})

const layout = computed(() => {
  const padL = 40
  const padR = 28
  const top = 34
  const lv = level.value

  // 1) 解析每个大版本的起止 + 节点日期
  //    **起止与节点粒度无关**：切粒度时线不能跟着挪，否则同一个大版本在两种视图里
  //    起点不一样，看着像数据变了
  const raw = props.majors.map((m) => {
    const rels = m.release_versions || []
    const anchors = []       // 定位大版本起止用的全部日期（版本 + 迭代版本）
    const relNodes = []
    const iterNodes = []
    let missing = 0
    rels.forEach((rv) => {
      const t = nodeTs(rv)
      if (t != null) {
        anchors.push(t)
        relNodes.push({
          id: 'r' + rv.id, version_no: rv.version_no, title: rv.title || '', t,
          released: ts(rv.actual_release_date) != null,
          sub: (rv.iteration_versions || []).length ? ` · ${(rv.iteration_versions || []).length} 个迭代版本` : '',
        })
      } else if (lv === 'release') missing += 1
      ;(rv.iteration_versions || []).forEach((iv) => {
        const it = nodeTs(iv)
        if (it != null) {
          anchors.push(it)
          iterNodes.push({
            id: 'i' + iv.id, version_no: iv.version_no, title: iv.title || '', t: it,
            released: ts(iv.actual_release_date) != null,
            sub: ` · 属于 ${rv.version_no}`,
          })
        } else if (lv === 'iteration') missing += 1
      })
    })
    const relTs = rels.map((rv) => ts(rv.actual_release_date)).filter((t) => t != null)
    const startT = ts(m.range_start) ?? (anchors.length ? Math.min(...anchors) : null)
    const relT = relTs.length ? Math.max(...relTs) : null   // 最近一次实际发布
    const baseEnd = ts(m.range_end) ?? (anchors.length ? Math.max(...anchors) : startT)
    const nodes = lv === 'major' ? [] : (lv === 'release' ? relNodes : iterNodes)
    nodes.sort((a, b) => a.t - b.t)
    return { m, nodes, missing, startT, baseEnd, endT: baseEnd == null ? null : baseEnd + TAIL_DAYS * 864e5, relT }
  })

  let placeable = raw.filter((r) => r.startT != null)
  const skipped = raw.filter((r) => r.startT == null).map((r) => r.m.version_no)
  if (!placeable.length) return { empty: true, skipped, nodeSkipped: 0, nodeClipped: 0 }

  // 2) 数据时间范围
  const allT = []
  placeable.forEach((r) => {
    allT.push(r.startT, r.endT ?? r.startT)
    r.nodes.forEach((n) => allT.push(n.t))
  })
  const dataMin = Math.min(...allT)
  const dataMax = Math.max(...allT)

  // 3) 横轴窗口。两条路，别合并：
  //    - **选了时间范围**（近 N 月 / 按月份区间）＝这就是窗口，一个月不多一个月不少。
  //      要看完整的声明范围就走这条——它是「全部」自动收窄之后唯一的退路。
  //    - **「全部」＝只画有内容的时间段**：一个大版本声明了三年、版本却全挤在最后
  //      半年时，从声明起点铺满会把大半张图让给空白，几个版本挤成一团谁也读不出来。
  //      收窄只是**画法**，range_start 没有被改写：起点早于窗口的泳道左端画一个 «，
  //      表示"开始时间在窗口之外"而不是被截断。
  const win = explicitWindow(dataMax)
  let clipMin
  let clipMax
  if (win) {
    clipMin = Math.max(dataMin, win.lo)
    clipMax = Math.min(dataMax, win.hi)
  } else {
    // 有节点的泳道按节点定位；一个节点都没有的泳道拿自己的起止顶上，
    // 否则它会因为"没内容"整条从图上消失
    const content = []
    placeable.forEach((r) => {
      if (r.nodes.length) r.nodes.forEach((n) => content.push(n.t))
      else { content.push(r.startT); if (r.endT != null) content.push(r.endT) }
    })
    if (content.length) {
      clipMin = Math.max(dataMin, Math.min(...content) - HEAD_PAD_DAYS * 864e5)
      // 末端仍留 TAIL_DAYS，箭头才不会正好压在窗口右边缘上
      clipMax = Math.min(dataMax, Math.max(...content) + TAIL_DAYS * 864e5)
    } else { clipMin = dataMin; clipMax = dataMax }
  }
  // 整段落在窗口之外的版本不再展示
  placeable = placeable.filter((r) => (r.endT ?? r.startT) >= clipMin && r.startT <= clipMax)
  if (!placeable.length) return { empty: true, skipped, nodeSkipped: 0, nodeClipped: 0 }

  let minT = clipMin
  let maxT = clipMax
  if (minT === maxT) { minT -= 15 * 864e5; maxT += 15 * 864e5 }
  const span = maxT - minT
  minT -= span * 0.04
  maxT += span * 0.04
  const clamp = (t) => Math.min(Math.max(t, clipMin), clipMax)
  const xOf = (t) => padL + ((clamp(t) - minT) / (maxT - minT)) * (W - padL - padR)

  // 4) 排序：主干在最上，其余按起始时间倒序
  //    主干由后端的 line 字段说了算，不再靠「起始最晚」猜——猜错的表现是
  //    时间轴画的主线和实际在主干上的大版本不是同一个，且看着完全正常
  placeable.sort((a, b) => {
    const am = a.m.line === 'master' ? 0 : 1
    const bm = b.m.line === 'master' ? 0 : 1
    if (am !== bm) return am - bm
    if (b.startT !== a.startT) return b.startT - a.startT
    return String(b.m.version_no).localeCompare(String(a.m.version_no), 'zh-Hans-CN', { numeric: true })
  })

  // 5) 图上点少的时候整体放大一档：泳道拉高、节点变粗、版本号字号变大。
  //    时间比例**一个字都不动**——放大的只是画笔。稀疏时不放大的话，整张图就是
  //    一根细线上孤零零几个小点，版本号小到得凑过去看
  const visibleNodes = placeable.reduce(
    (n, r) => n + r.nodes.filter((x) => x.t >= clipMin && x.t <= clipMax).length, 0,
  )
  const sparse = visibleNodes <= SPARSE_NODE_MAX
  const laneGap = sparse ? 88 : 64
  const nodeR = (lv === 'iteration' ? 3 : 4) + (sparse ? 2 : 0)
  const labelFS = sparse ? 11 : 9
  const labelUp = nodeR + 5
  const labelDown = nodeR + labelFS + 9
  const leadFrom = nodeR
  const leadTo = nodeR + 7

  const hasMaster = placeable.some((r) => r.m.line === 'master')
  const mainY = top + 12
  const majors = placeable.map((r, i) => {
    const color = PALETTE[i % PALETTE.length]
    const y = mainY + i * laneGap
    const startX = xOf(r.startT)
    const endX = xOf(r.endT ?? r.startT)
    // 一条主干都没标时退回「排在最前的那条」，免得整张图没有主线可挂分支
    const isMain = hasMaster ? r.m.line === 'master' : i === 0
    const clipped = r.startT < clipMin
    const labelText = (isMain ? '主干 ' : '') + (r.m.version_no || '')
    const labelW = Math.max(34, labelText.length * 8 + 14)
    let labelX = startX - labelW - 8
    if (labelX < 2) labelX = startX + 8

    // 节点标签上下交错（even=上 / odd=下），同一行内重叠则隐藏标签
    let aboveR = -1e9
    let belowR = -1e9
    const nodes = r.nodes
      .filter((n) => n.t >= clipMin && n.t <= clipMax)
      .map((n, k) => {
        const x = xOf(n.t)
        const halfW = (String(n.version_no || '').length * labelFS * 0.56) / 2
        const above = k % 2 === 0
        let showLabel = true
        if (above) {
          if (x - halfW < aboveR + 4) showLabel = false
          else aboveR = x + halfW
        } else {
          if (x - halfW < belowR + 4) showLabel = false
          else belowR = x + halfW
        }
        return { ...n, x, dateLabel: fmtDate(n.t), above, showLabel }
      })

    const out = {
      id: r.m.id, version_no: r.m.version_no, title: r.m.title || '',
      color, y, startX, endX, isMain, clipped, nodes, nodeR, labelX, labelW,
      released: r.relT != null, releaseLabel: fmtDate(r.relT), endLabel: fmtDate(r.baseEnd),
    }
    if (isMain) {
      // 起点被窗口裁掉时不画这条引入虚线：那条虚线的意思是"这之前还没开始"，
      // 而裁掉的情况恰恰相反（« 才是对的提示）
      out.preX = !clipped && startX > padL + 1 ? padL : null
    } else {
      out.branchPath = `M ${startX},${mainY} C ${startX},${mainY + 24} ${startX + 18},${y - 24} ${startX + 18},${y}`
      out.startX = startX + 18
    }
    return out
  })

  // 6) 月份网格。窗口宽的时候每月一格会糊成一片，按格数自动隔 1 / 3 / 6 个月标一次
  const monthsTotal = Math.max(1, Math.round((maxT - minT) / (30.4 * 864e5)))
  const stride = monthsTotal > 36 ? 6 : (monthsTotal > 18 ? 3 : 1)
  const months = []
  const d = new Date(minT); d.setDate(1); d.setHours(0, 0, 0, 0)
  let idx = 0
  while (d.getTime() <= maxT) {
    const t = d.getTime()
    if (t >= minT && idx % stride === 0) {
      const m = d.getMonth() + 1
      months.push({ x: xOf(t), label: m === 1 ? `${d.getFullYear()}/1` : `${m}月` })
    }
    idx += 1
    d.setMonth(d.getMonth() + 1)
  }

  const axisY = mainY + (majors.length - 1) * laneGap + 32
  const nowT = Date.now()
  const todayX = nowT >= minT && nowT <= maxT ? xOf(nowT) : null
  const nodeSkipped = placeable.reduce((n, r) => n + r.missing, 0)
  // 被时间窗口挡在外面的节点数：只筛不报的表现是"这个版本怎么不在图上"
  const nodeClipped = placeable.reduce(
    (n, r) => n + r.nodes.filter((x) => x.t < clipMin || x.t > clipMax).length, 0,
  )
  // 图例只在画节点的粒度下才有意义；它必须画进 svg 里而不是写在页面上，
  // 导出的那张图才带得走「琥珀＝还没发布」这条说明
  const showLegend = lv !== 'major'
  const legendY = axisY + 34
  const legendColor = majors.length ? majors[0].color : PALETTE[0]

  return {
    empty: false, skipped, nodeSkipped, nodeClipped, majors, months, top, axisY, todayX,
    labelFS, labelUp, labelDown, leadFrom, leadTo, sparse,
    showLegend, legendY, legendColor,
    height: axisY + (showLegend ? 46 : 24),
  }
})

// ── 导出 ────────────────────────────────────────────────────────────────
const exporting = ref(false)

function serialize() {
  const src = svgRef.value
  if (!src) return null
  const clone = src.cloneNode(true)
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  clone.setAttribute('width', String(W))
  clone.setAttribute('height', String(layout.value.height))
  clone.removeAttribute('style')
  // 白底：导出的图多半要贴进 PPT 或邮件，透明底在深色版式上就成了看不清的一团
  const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
  bg.setAttribute('x', '0'); bg.setAttribute('y', '0')
  bg.setAttribute('width', String(W)); bg.setAttribute('height', String(layout.value.height))
  bg.setAttribute('fill', '#ffffff')
  clone.insertBefore(bg, clone.firstChild)
  return new XMLSerializer().serializeToString(clone)
}

function stamp() {
  return new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19)
}

async function onExport(kind) {
  if (layout.value.empty) { ElMessage.warning('图上还没有可导出的版本'); return }
  exporting.value = true
  try {
    const xml = serialize()
    if (!xml) throw new Error('图还没画出来')
    if (kind === 'svg') {
      downloadBlob(new Blob([xml], { type: 'image/svg+xml;charset=utf-8' }), `version-timeline-${stamp()}.svg`)
      ElMessage.success('已导出 SVG')
      return
    }
    // PNG：2 倍图，贴进 PPT 放大不糊
    const scale = 2
    const h = layout.value.height
    const url = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(xml)))
    const img = new Image()
    await new Promise((resolve, reject) => {
      img.onload = resolve
      img.onerror = () => reject(new Error('图片渲染失败'))
      img.src = url
    })
    const canvas = document.createElement('canvas')
    canvas.width = W * scale
    canvas.height = h * scale
    const ctx = canvas.getContext('2d')
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'))
    if (!blob) throw new Error('导出 PNG 失败')
    downloadBlob(blob, `version-timeline-${stamp()}.png`)
    ElMessage.success('已导出 PNG')
  } catch (e) {
    ElMessage.error(e?.message || '导出失败')
  } finally {
    exporting.value = false
  }
}
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
/* 画笔（颜色 / 线宽 / 字号）全在模板的元素属性上，别搬到这儿来——scoped CSS
   跟不进导出的那份 svg，表现是页面好好的、导出来全是黑的默认色 */
.vt-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; flex-wrap: wrap; }
.vt-bar-label { font-size: 13px; color: #606266; }
.vt-bar-hint { color: #c0c4cc; font-size: 12px; margin-left: 4px; }
.vt-svg { width: 100%; min-width: 720px; display: block; overflow: visible; }
.vt-empty { color: #909399; font-size: 13px; padding: 18px 8px; }
.vt-skipped { color: #c0c4cc; font-size: 12px; padding: 2px 4px 4px; }
</style>
