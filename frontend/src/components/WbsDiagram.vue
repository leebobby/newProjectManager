<template>
  <div class="wd-wrap" v-loading="loading">
    <div class="wd-bar">
      <span class="wd-hint">
        第 1 层是<b>调试阶段</b>，箭头是推进顺序；每一列底下按层级缩进摆它的子任务，越深一层字越小。
      </span>
      <span class="wd-grow" />
      <el-button size="small" :loading="exporting" @click="onExport('png')">导出 PNG</el-button>
      <el-button size="small" :loading="exporting" @click="onExport('svg')">导出 SVG</el-button>
    </div>

    <!-- 版面（每个方框的 x/y/w/h 与折好的行）由服务端 wbs_diagram 算，
         这里只负责画。前端再排一次的话，页面上是 4 列、导出的 Excel 里是 5 列，
         而两边单独看都正常。 -->
    <div v-if="spec && spec.box_count" class="wd-scroll">
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
              font-weight="700" fill="#C7000B">{{ spec.title || 'WBS 调试框图' }}</text>
        <text v-if="spec.subtitle" :x="spec.pad"
              :y="spec.pad + spec.title_px * 1.5 + spec.sub_px" :font-size="spec.sub_px"
              fill="#808080">{{ spec.subtitle }}</text>

        <line v-for="(a, i) in spec.arrows" :key="'a' + i"
              :x1="a.x1 + 6" :y1="a.y1" :x2="a.x2 - 8" :y2="a.y2"
              :stroke="spec.arrow_color" stroke-width="1.6" marker-end="url(#wd-arrow)" />

        <g v-for="(b, i) in spec.boxes" :key="'b' + i">
          <rect :x="b.x" :y="b.y" :width="b.w" :height="b.h" rx="3"
                :fill="b.fill" :stroke="b.stroke" stroke-width="1" />
          <text v-for="(ln, k) in b.lines" :key="k"
                :x="b.x + 10" :y="b.y + 7 + (k + 1) * b.line_h - b.line_h * 0.28"
                :font-size="b.font_px" :font-weight="b.bold ? 700 : 400"
                :fill="b.color">{{ ln }}</text>
          <text v-if="b.meta" :x="b.x + 10"
                :y="b.y + 7 + b.lines.length * b.line_h + b.meta_h * 0.72"
                :font-size="b.meta_px" fill="#808080">{{ b.meta }}</text>
        </g>

        <g v-for="(lg, i) in legendPos" :key="'l' + i">
          <rect :x="lg.x" :y="spec.legend_y" :width="spec.legend_px" :height="spec.legend_px"
                :fill="lg.fill" stroke="#BFBFBF" stroke-width="1" />
          <text :x="lg.x + spec.legend_px + 5" :y="spec.legend_y + spec.legend_px - 1"
                :font-size="spec.legend_px" fill="#262626">{{ lg.label }}</text>
        </g>
        <text :x="spec.pad" :y="spec.legend_y + spec.legend_px * 2.1"
              :font-size="spec.legend_px" fill="#808080">{{ footNote }}</text>
      </svg>
    </div>

    <el-empty v-else-if="spec" description="这份 WBS 还没有任何工作包，框图是空的" />

    <!-- 画不下的条数要如实摆出来：只筛不报的表现是「这个阶段怎么不在图上」 -->
    <div v-if="spec && spec.skipped" class="wd-note">
      另有 <b>{{ spec.skipped }}</b> 行没画进图里（整份 WBS 太大，全画出来每个方框细得看不见）。
      上面的表格是全量的。
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { apiError, downloadBlob, wbsApi } from '../api'

const props = defineProps({ planId: { type: [String, Number], required: true } })

const spec = ref(null)
const loading = ref(false)
const exporting = ref(false)
const svgRef = ref(null)

// 图例横着排：每一项的起点要按前一项的**文字宽度**推。宽度估算与服务端
// wbs_diagram._text_w 同款（全角 1.0 em、西文 0.55 em），两边不一样的话
// 页面上的图例会和导出的 PNG 错开一段
function textW(s, size) {
  let w = 0
  for (const ch of String(s || '')) w += ch.charCodeAt(0) > 0x2E7F ? size : size * 0.55
  return w
}
const legendPos = computed(() => {
  if (!spec.value) return []
  let x = spec.value.pad
  return spec.value.legend.map((it) => {
    const at = x
    x += spec.value.legend_px + 6 + textW(it.label, spec.value.legend_px) + 16
    return { ...it, x: at }
  })
})
const footNote = computed(() => {
  if (!spec.value) return ''
  let s = '第 1 层＝调试阶段，箭头是推进顺序；越深一层字越小。'
  if (spec.value.wrapped) s += '阶段一行摆不下，折到了下一段（段与段之间不画箭头）。'
  if (spec.value.skipped) s += `另有 ${spec.value.skipped} 行没画进图里。`
  return s
})

async function load() {
  if (!props.planId) return
  loading.value = true
  try {
    const { data } = await wbsApi.diagram(props.planId)
    spec.value = data
  } catch (e) {
    ElMessage.error(apiError(e, '加载调试框图失败'))
  } finally {
    loading.value = false
  }
}
watch(() => props.planId, load, { immediate: true })
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
  if (!spec.value?.box_count) { ElMessage.warning('图上还没有可导出的内容'); return }
  exporting.value = true
  try {
    const xml = serialize()
    if (!xml) throw new Error('图还没画出来')
    if (kind === 'svg') {
      downloadBlob(new Blob([xml], { type: 'image/svg+xml;charset=utf-8' }), `wbs-diagram-${stamp()}.svg`)
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
    downloadBlob(blob, `wbs-diagram-${stamp()}.png`)
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
.wd-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.wd-hint { color: #909399; font-size: 12px; }
.wd-hint b { color: #606266; }
.wd-grow { flex: 1 1 auto; }
/* 图比屏幕宽是常态（阶段一多就横着铺），让它自己横向滚，
   别让整页跟着横向滚——那样表头和工具栏都跟着跑出去了 */
.wd-scroll { overflow-x: auto; }
.wd-svg { display: block; }
.wd-note { margin-top: 8px; background: #fdf6ec; border-left: 3px solid #E6A23C;
  border-radius: 3px; padding: 6px 10px; color: #8a6d3b; font-size: 12px; }
</style>
