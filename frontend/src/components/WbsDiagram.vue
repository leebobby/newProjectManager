<template>
  <div class="wd-wrap" v-loading="loading">
    <div class="wd-bar">
      <span class="wd-hint">
        第 1 层是<b>调试阶段</b>，箭头是推进顺序；方框第三行是<b>计划日期</b>，
        <b class="wd-late">红框</b>＝已过计划完成日还没做完。
      </span>
      <span class="wd-grow" />
      <el-button size="small" :loading="exporting" @click="onExport('png')">导出 PNG</el-button>
      <el-button size="small" :loading="exporting" @click="onExport('svg')">导出 SVG</el-button>
    </div>

    <!-- 版面（每根条 / 每个方框的 x/y/w/h 与折好的行）由服务端 wbs_diagram 算，
         这里只负责画。前端再排一次的话，页面上是 4 列、导出的 Excel 里是 5 列，
         而两边单独看都正常。 -->
    <div v-if="drawable" class="wd-scroll">
      <!-- 画笔一律写成**元素属性**，不写在 <style scoped> 里：scoped CSS 靠 data-v
           属性挂在页面 DOM 上，XMLSerializer 序列化出去的那份带不走它，表现是
           「页面上好好的，导出来全变成黑的默认色」（见 CLAUDE.md「前端约定」）。 -->
      <svg ref="svgRef" :viewBox="`0 0 ${spec.width} ${spec.height}`"
           :width="spec.width" :height="spec.height" class="wd-svg">
        <defs>
          <marker id="wd-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3"
                  orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L7,3 L0,6 z" :fill="spec.arrow_color" />
          </marker>
        </defs>

        <!-- 标题与图例画进 svg 里，导出的那张图才带得走：落单的一张没有标题
             就找不回出处（同 VersionTimeline 的图例、pptx 的页脚三件套） -->
        <text :x="spec.pad" :y="spec.pad + spec.title_px" :font-size="spec.title_px"
              font-weight="700" fill="#C7000B">{{ spec.title || 'WBS' }}</text>
        <text v-if="spec.subtitle" :x="spec.pad"
              :y="spec.pad + spec.title_px * 1.5 + spec.sub_px" :font-size="spec.sub_px"
              fill="#808080">{{ spec.subtitle }}</text>

        <line v-for="(a, i) in spec.arrows" :key="'a' + i"
              :x1="a.x1 + 6" :y1="a.y1" :x2="a.x2 - 8" :y2="a.y2"
              :stroke="spec.arrow_color" stroke-width="1.6" marker-end="url(#wd-arrow)" />

        <g v-for="(b, i) in spec.boxes" :key="'b' + i">
          <!-- 延期＝红色粗边框，**底色照旧**：底色表达的是状态（绿＝已完成、
               黄＝进行中），拿它表示延期就得二选一，而那正是要同时看到的两件事 -->
          <rect :x="b.x" :y="b.y" :width="b.w" :height="b.h" rx="3"
                :fill="b.fill" :stroke="b.stroke" :stroke-width="b.stroke_w || 1">
            <title>{{ boxTip(b) }}</title>
          </rect>
          <text v-for="(l, k) in b.lines" :key="k"
                :x="b.x + 10" :y="b.y + 7 + (k + 1) * b.line_h - b.line_h * 0.28"
                :font-size="b.font_px" :font-weight="b.bold ? 700 : 400"
                :fill="b.color">{{ l }}</text>
          <text v-if="b.meta" :x="b.x + 10"
                :y="b.y + 7 + b.lines.length * b.line_h + b.meta_h * 0.72"
                :font-size="b.meta_px" fill="#808080">{{ b.meta }}</text>
          <text v-if="b.date" :x="b.x + 10"
                :y="b.y + 7 + b.lines.length * b.line_h + (b.meta ? b.meta_h : 0) + b.meta_h * 0.72"
                :font-size="b.meta_px" :fill="b.date_color">{{ b.date }}</text>
          <template v-if="b.bar">
            <rect :x="b.x + 10" :y="b.y + b.h - 3.5 - b.bar.h"
                  :width="b.bar.track_w" :height="b.bar.h" rx="1.5" :fill="b.bar.track" />
            <rect v-if="b.bar.w > 0.5" :x="b.x + 10" :y="b.y + b.h - 3.5 - b.bar.h"
                  :width="b.bar.w" :height="b.bar.h" rx="1.5" :fill="b.bar.fill" />
          </template>
        </g>

        <!-- 图例与底注：两张图共用同一段位置 -->
        <g v-for="(lg, i) in legendPos" :key="'l' + i">
          <rect :x="lg.x" :y="spec.legend_y" :width="spec.legend_px" :height="spec.legend_px"
                :fill="lg.fill" :stroke="lg.stroke || '#BFBFBF'"
                :stroke-width="lg.stroke ? 2 : 1" />
          <text :x="lg.x + spec.legend_px + 5" :y="spec.legend_y + spec.legend_px - 1"
                :font-size="spec.legend_px" fill="#262626">{{ lg.label }}</text>
        </g>
        <text v-for="(l, i) in spec.note_lines" :key="'n' + i" :x="spec.pad"
              :y="spec.note_y + i * spec.legend_px * 1.5"
              :font-size="spec.legend_px" fill="#808080">{{ l }}</text>
      </svg>
    </div>

    <el-empty v-else-if="spec" description="这份 WBS 还没有任何工作包，框图是空的" />

    <!-- 被排除/被折叠的条数要如实摆出来：只筛不报的表现是「这行怎么不在图上」 -->
    <div v-if="warnText" class="wd-note">{{ warnText }}</div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { apiError, downloadBlob, wbsApi } from '../api'

const props = defineProps({
  planId: { type: [String, Number], required: true },
  maxDepth: { type: [String, Number], default: null },
})

const spec = ref(null)
const loading = ref(false)
const exporting = ref(false)
const svgRef = ref(null)

const drawable = computed(() => (spec.value?.box_count || 0) > 0)
const warnText = computed(() => {
  const s = spec.value
  if (!s) return ''
  const p = []
  if (s.folded) p.push(`只画到第 ${s.max_depth} 层，另有 ${s.folded} 行在更深的层级上没有画出来；它们的工期仍然算在上级方框的汇总里。`)
  if (s.skipped) p.push(`另有 ${s.skipped} 行没画进图里（整份 WBS 太大，全画出来每个方框细得看不见）。上面的表格是全量的。`)
  return p.join(' ')
})
// 图例横着排：每一项的起点按前一项的**文字宽度**推。宽度估算与服务端
// wbs_diagram._text_w 同款（全角 1.0 em、西文 0.55 em），两边不一样的话
// 页面上的图例会和导出的 PNG 错开一段
function textW(s, size) {
  let w = 0
  for (const ch of String(s || '')) w += ch.charCodeAt(0) > 0x2E7F ? size : size * 0.55
  return w
}
const legendPos = computed(() => {
  const s = spec.value
  if (!s?.legend) return []
  let x = s.pad
  return s.legend.map((it) => {
    const at = x
    x += s.legend_px + 6 + textW(it.label, s.legend_px) + 16
    return { ...it, x: at }
  })
})

// 方框里的字是**折过行、可能截断**的，悬停给全的那一份
function boxTip(b) {
  const bits = [b.lines.join(''), b.meta, b.date].filter(Boolean)
  if (b.overdue) bits.push(`已过计划完成日 ${b.overdue_days} 天，状态还不是「已完成」`)
  return bits.join('\n')
}

async function load() {
  if (!props.planId) return
  loading.value = true
  try {
    const { data } = await wbsApi.diagram(props.planId, props.maxDepth)
    spec.value = data
  } catch (e) {
    ElMessage.error(apiError(e, '加载调试框图失败'))
  } finally {
    loading.value = false
  }
}
watch(() => [props.planId, props.maxDepth], load, { immediate: true })
defineExpose({ reload: load })

function serialize() {
  const src = svgRef.value
  if (!src) return null
  const clone = src.cloneNode(true)
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  clone.removeAttribute('class')
  // 白底：导出的图多半要贴进 PPT 或邮件，透明底在深色版式上就成了看不清的一团
  const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
  bg.setAttribute('x', '0'); bg.setAttribute('y', '0')
  bg.setAttribute('width', String(spec.value.width))
  bg.setAttribute('height', String(spec.value.height))
  bg.setAttribute('fill', '#ffffff')
  clone.insertBefore(bg, clone.firstChild)
  return new XMLSerializer().serializeToString(clone)
}

function stamp() {
  return new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19)
}

async function onExport(kind) {
  if (!drawable.value) { ElMessage.warning('图上还没有可导出的内容'); return }
  exporting.value = true
  const base = 'wbs-diagram'
  try {
    const xml = serialize()
    if (!xml) throw new Error('图还没画出来')
    if (kind === 'svg') {
      downloadBlob(new Blob([xml], { type: 'image/svg+xml;charset=utf-8' }), `${base}-${stamp()}.svg`)
      ElMessage.success('已导出 SVG')
      return
    }
    const scale = 2   // 2 倍图，贴进 PPT 放大不糊
    const url = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(xml)))
    const img = new Image()
    await new Promise((resolve, reject) => {
      img.onload = resolve
      img.onerror = () => reject(new Error('图片渲染失败'))
      img.src = url
    })
    const canvas = document.createElement('canvas')
    canvas.width = spec.value.width * scale
    canvas.height = spec.value.height * scale
    const ctx = canvas.getContext('2d')
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'))
    if (!blob) throw new Error('导出 PNG 失败')
    downloadBlob(blob, `${base}-${stamp()}.png`)
    ElMessage.success('已导出 PNG')
  } catch (e) {
    ElMessage.error(e?.message || '导出失败')
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.wd-wrap { background: #fff; border: 1px solid #ebeef5; border-radius: 6px; padding: 10px 12px 12px; }
.wd-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
.wd-hint { color: #909399; font-size: 12px; }
.wd-grow { flex: 1 1 auto; }
/* 图比屏幕宽是常态，让它自己横向滚，别让整页跟着横向滚
   ——那样表头和工具栏都跟着跑出去了 */
.wd-scroll { overflow-x: auto; }
.wd-svg { display: block; }
.wd-note { margin-top: 8px; background: #fdf6ec; border-left: 3px solid #E6A23C;
  border-radius: 3px; padding: 6px 10px; color: #8a6d3b; font-size: 12px; }
</style>
