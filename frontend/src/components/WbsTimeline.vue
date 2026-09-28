<template>
  <div class="wt-wrap" v-loading="loading">
    <div class="wt-bar">
      <span class="wt-hint">
        横轴是<b>真日期</b>；任务编号、名称和进度直接写在框内，框里套的是下一层。
        有前置关系的任务用箭头连接。<b class="wt-late">红框</b>＝已过计划完成日还没做完。
      </span>
      <span class="wt-grow" />
      <el-button size="small" :loading="exporting" @click="onExport('png')">导出 PNG</el-button>
      <el-button size="small" :loading="exporting" @click="onExport('svg')">导出 SVG</el-button>
    </div>

    <!-- 版面（每一行、每个框的 x/y/w/h）由服务端 wbs_timeline 算，这里只负责画。
         前端再排一次的话，同一份 WBS 在页面上和导出的 PNG 里框的位置不一样，
         而两边单独看都正常（见 CLAUDE.md「WBS · 导出与调试框图」）。 -->
    <div v-if="drawable" class="wt-scroll">
      <!-- 画笔一律写成**元素属性**，不写在 <style scoped> 里：scoped CSS 靠 data-v
           属性挂在页面 DOM 上，XMLSerializer 序列化出去的那份带不走它，表现是
           「页面上好好的，导出来全变成黑的默认色」 -->
      <svg ref="svgRef" :viewBox="`0 0 ${spec.width} ${spec.height}`"
           :width="spec.width" :height="spec.height" class="wt-svg">
        <defs>
          <marker id="wt-arrow" viewBox="0 0 10 10" refX="9" refY="5"
                  markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#606266" />
          </marker>
        </defs>
        <!-- bands 保留为空数组以兼容旧版版面协议。 -->
        <rect v-for="(b, i) in spec.bands" :key="'z' + i"
              :x="b.x" :y="b.y" :width="b.w" :height="b.h" :fill="b.fill" />

        <line v-for="(g, i) in spec.grid" :key="'g' + i"
              :x1="g.x" :y1="g.y1" :x2="g.x" :y2="g.y2" :stroke="g.color" stroke-width="1" />
        <line v-for="(l, i) in spec.lines" :key="'l' + i"
              :x1="l.x1" :y1="l.y1" :x2="l.x2" :y2="l.y2" :stroke="l.color" :stroke-width="l.w" />
        <text v-for="(t, i) in spec.ticks" :key="'t' + i"
              :x="t.label_x" :y="spec.top - 20" font-size="11" fill="#808080">{{ t.label }}</text>

        <!-- 框按行的顺序画：父框先画、子框压在上面，这就是「框里套框」看得见的原因 -->
        <g v-for="(b, i) in spec.boxes" :key="'b' + i">
          <rect :x="b.x" :y="b.y" :width="b.w" :height="b.h" :rx="b.rx"
                :fill="b.fill" :stroke="b.stroke" :stroke-width="b.stroke_w">
            <title>{{ b.tip }}</title>
          </rect>
          <template v-if="b.bar">
            <rect :x="b.bar.x" :y="b.bar.y" :width="b.bar.track_w" :height="b.bar.h"
                  rx="1.2" :fill="b.bar.track" />
            <rect v-if="b.bar.w > 0.5" :x="b.bar.x" :y="b.bar.y" :width="b.bar.w"
                  :height="b.bar.h" rx="1.2" :fill="b.bar.fill" />
          </template>
          <text :x="b.label_x" :y="b.label_y" :font-size="b.label_px"
                :font-weight="b.label_bold ? 700 : 400" :fill="b.label_color">{{ b.label }}</text>
          <text v-if="b.meta" :x="b.meta_x" :y="b.meta_y" :font-size="b.meta_px"
                :fill="b.meta_color">{{ b.meta }}</text>
        </g>

        <!-- 依赖线压在父级底色上；折线路由避开框内文字，只在终点接触任务框。 -->
        <polyline v-for="(a, i) in spec.arrows" :key="'a' + i"
                  :points="a.points.map(p => p.join(',')).join(' ')" fill="none"
                  :stroke="a.color" stroke-width="1.5" marker-end="url(#wt-arrow)" />

        <!-- 今天：整张图唯一一处红 -->
        <line :x1="spec.today.x" :y1="spec.today.y1" :x2="spec.today.x" :y2="spec.today.y2"
              :stroke="spec.today.color" stroke-width="1.5" />
        <rect :x="spec.today.pill_x" :y="spec.today.pill_y" :width="spec.today.pill_w"
              :height="spec.today.pill_h" :rx="spec.today.pill_h / 2" :fill="spec.today.color" />
        <text :x="spec.today.x" :y="spec.today.text_y" :font-size="spec.today.pill_px"
              font-weight="700" text-anchor="middle" fill="#FFFFFF">{{ spec.today.label }}</text>

        <!-- 图例与底注画进图里：导出的那张图经常被单独截进别的材料，
             落单的一张没有说明就找不回出处（这张图刻意不画标题，出处写在底注第一行） -->
        <g v-for="(lg, i) in spec.legend" :key="'lg' + i">
          <rect :x="lg.x" :y="spec.legend_y" :width="spec.legend_px" :height="spec.legend_px"
                :fill="lg.fill" :stroke="lg.stroke || '#BFBFBF'"
                :stroke-width="lg.stroke ? 2 : 1" />
          <text :x="lg.x + spec.legend_px + 5" :y="spec.legend_y + spec.legend_px - 1"
                :font-size="spec.legend_px" fill="#262626">{{ lg.label }}</text>
        </g>
        <text v-for="(l, i) in spec.note_lines" :key="'n' + i" :x="spec.pad"
              :y="spec.note_y + i * spec.legend_px * 1.6"
              :font-size="spec.legend_px" fill="#808080">{{ l }}</text>
      </svg>
    </div>

    <el-empty v-else-if="spec" description="这份 WBS 还没有任何工作包，A 图是空的" />

    <!-- 被折叠 / 排不上时间轴 / 没画进去的条数要如实摆出来：
         只筛不报的表现是「这行怎么不在图上」 -->
    <div v-if="warnText" class="wt-note">{{ warnText }}</div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { apiError, downloadBlob, wbsApi } from '../api'
import { serializeSvg, stamp, svgBlob, svgToPngBlob } from '../utils/svgExport'

const props = defineProps({
  planId: { type: [String, Number], required: true },
  maxDepth: { type: [String, Number], default: null },
})

const spec = ref(null)
const loading = ref(false)
const exporting = ref(false)
const svgRef = ref(null)

const drawable = computed(() => (spec.value?.row_count || 0) > 0)
const warnText = computed(() => {
  const s = spec.value
  if (!s) return ''
  const p = []
  if (s.undated) p.push(`有 ${s.undated} 行没填计划完成日，已放在时间轴起点并在框内标明。`)
  if (s.folded) p.push(`只画到第 ${s.max_depth} 层，另有 ${s.folded} 行折在上级框里（名字后面的 +N）；它们的工期仍然算在上级框的汇总里。`)
  if (s.skipped) p.push(`另有 ${s.skipped} 行没画进图里（整份 WBS 太大），按整段阶段截的。上面的表格是全量的。`)
  return p.join(' ')
})

async function load() {
  if (!props.planId) return
  loading.value = true
  try {
    const { data } = await wbsApi.timeline(props.planId, props.maxDepth)
    spec.value = data
  } catch (e) {
    ElMessage.error(apiError(e, '加载 A 图失败'))
  } finally {
    loading.value = false
  }
}
watch(() => [props.planId, props.maxDepth], load, { immediate: true })
defineExpose({ reload: load })

async function onExport(kind) {
  if (!drawable.value) { ElMessage.warning('图上还没有可导出的内容'); return }
  exporting.value = true
  const base = `wbs-a-${stamp()}`
  try {
    const xml = serializeSvg(svgRef.value, spec.value.width, spec.value.height)
    if (!xml) throw new Error('图还没画出来')
    if (kind === 'svg') {
      downloadBlob(svgBlob(xml), `${base}.svg`)
      ElMessage.success('已导出 SVG')
      return
    }
    downloadBlob(await svgToPngBlob(xml, spec.value.width, spec.value.height), `${base}.png`)
    ElMessage.success('已导出 PNG')
  } catch (e) {
    ElMessage.error(e?.message || '导出失败')
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.wt-wrap { background: #fff; }
.wt-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
.wt-hint { color: #909399; font-size: 12px; line-height: 1.6; max-width: 62%; }
.wt-late { color: #F56C6C; }
.wt-grow { flex: 1 1 auto; }
/* 图比屏幕宽是常态，让它自己横向滚，别让整页跟着横向滚 */
.wt-scroll { overflow-x: auto; border: 1px solid #ebeef5; border-radius: 6px; }
.wt-svg { display: block; }
.wt-note { margin-top: 8px; background: #fdf6ec; border-left: 3px solid #E6A23C;
  border-radius: 3px; padding: 6px 10px; color: #8a6d3b; font-size: 12px; line-height: 1.7; }
</style>
