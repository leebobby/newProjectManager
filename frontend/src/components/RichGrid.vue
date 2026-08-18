<template>
  <div class="rich-grid">
    <!-- 编辑工具条 -->
    <div v-if="editable" class="rg-toolbar">
      <span class="rg-tip">{{ selDesc }}</span>
      <el-button-group>
        <el-button size="small" :disabled="!sel" @click="setAlign('left')">左对齐</el-button>
        <el-button size="small" :disabled="!sel" @click="setAlign('center')">居中</el-button>
        <el-button size="small" :disabled="!sel" @click="setAlign('right')">右对齐</el-button>
      </el-button-group>
      <el-button-group>
        <el-button size="small" :disabled="!sel" :type="selFlag('bold') ? 'primary' : ''" @click="toggleFlag('bold')">
          <b>B</b>
        </el-button>
        <el-button size="small" :disabled="!sel" :type="selFlag('italic') ? 'primary' : ''" @click="toggleFlag('italic')">
          <i>I</i>
        </el-button>
        <el-button size="small" :disabled="!sel" :type="selFlag('underline') ? 'primary' : ''" @click="toggleFlag('underline')">
          <u>U</u>
        </el-button>
      </el-button-group>
      <el-select v-model="selFont" size="small" :disabled="!sel" class="rg-fontsel" placeholder="字体">
        <el-option v-for="f in FONTS" :key="f.value" :label="f.label" :value="f.value" />
      </el-select>
      <el-select v-model="selSize" size="small" :disabled="!sel" class="rg-sizesel" placeholder="字号">
        <el-option v-for="z in FONT_SIZES" :key="z.value" :label="z.label" :value="z.value" />
      </el-select>
      <span class="rg-fmt">
        <span class="rg-tip">字色</span>
        <el-color-picker
          v-model="selColor"
          size="small"
          :disabled="!isBodySel"
          :predefine="PREDEFINE_TEXT_COLORS"
        />
        <span class="rg-tip">底色</span>
        <el-select v-model="selBg" size="small" :disabled="!isBodySel" class="rg-bgsel">
          <el-option v-for="b in CELL_BGS" :key="b.value" :label="b.label" :value="b.value">
            <span class="swatch" :style="{ background: b.value || '#fff', border: '1px solid #dcdfe6' }" />
            {{ b.label }}
          </el-option>
        </el-select>
      </span>
      <el-button size="small" :disabled="!sel" @click="clearFormat">清除格式</el-button>
      <el-button size="small" :disabled="!isHeaderSel" @click="mergeHeader">合并表头→</el-button>
      <el-button size="small" :disabled="!canSplit" @click="splitHeader">拆分表头</el-button>
      <span class="rg-fmt">
        <span class="rg-tip">列格式</span>
        <el-select
          v-model="selColType"
          size="small"
          :disabled="!isBodySel"
          class="rg-typesel"
          placeholder="选列"
        >
          <el-option v-for="t in COL_TYPES" :key="t.value" :label="t.label" :value="t.value" />
        </el-select>
        <el-input
          v-if="isBodySel && (selColType === 'select' || selColType === 'light')"
          v-model="selColOptionsText"
          size="small"
          class="rg-optinput"
          :placeholder="selColType === 'light' ? '点灯取值，逗号分隔' : '下拉选项，逗号分隔'"
        />
      </span>
      <div class="spacer" />
      <el-button-group>
        <el-button size="small" @click="insertRow('above')">↑插入行</el-button>
        <el-button size="small" @click="insertRow('below')">↓插入行</el-button>
        <el-button size="small" type="danger" plain :disabled="!isBodySel" @click="deleteSelRow">删除行</el-button>
      </el-button-group>
      <el-button-group>
        <el-button size="small" @click="insertCol('left')">←插入列</el-button>
        <el-button size="small" @click="insertCol('right')">→插入列</el-button>
        <el-button size="small" type="danger" plain :disabled="!sel" @click="deleteSelCol">删除列</el-button>
      </el-button-group>
    </div>

    <table class="rg-table">
      <colgroup>
        <col v-for="(w, i) in displayWidths" :key="'col' + i" :style="{ width: w + 'px' }" />
      </colgroup>
      <thead>
        <tr>
          <th
            v-for="(h, hi) in model.headers"
            :key="'h' + hi"
            :colspan="h.colspan || 1"
            :class="{ selected: isSel('header', hi) }"
            :style="headerStyle(h)"
            @click="editable && selectCell('header', 0, hi)"
          >
            <input
              v-if="editable"
              v-model="h.text"
              class="rg-input bold"
              :style="headerStyle(h)"
              placeholder="表头"
              @input="emitUpdate"
            />
            <span v-else :style="headerStyle(h)">{{ h.text }}</span>
            <button
              v-if="editable && model.headers.length > 1"
              class="rg-del col"
              type="button"
              title="删除该列组"
              @click.stop="removeHeader(hi)"
            >×</button>
            <!-- 拖动改列宽（作用于该列组最右侧的物理列） -->
            <span
              v-if="editable"
              class="rg-resizer"
              title="拖动调整列宽"
              @mousedown.stop.prevent="startResize($event, hi)"
              @click.stop
            />
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, ri) in model.rows" :key="'r' + ri">
          <td
            v-for="(cell, ci) in row"
            :key="'c' + ri + '-' + ci"
            :class="{ selected: isSel('body', ri, ci) }"
            :style="cellStyle(cell, ci)"
            @click="editable && selectCell('body', ri, ci)"
          >
            <template v-if="editable">
              <el-select
                v-if="isChoiceCol(ci)"
                v-model="cell.text"
                size="small"
                clearable
                class="rg-field"
                @change="emitUpdate"
              >
                <el-option v-for="opt in colOptionsAt(ci)" :key="opt" :label="opt" :value="opt" />
              </el-select>
              <el-date-picker
                v-else-if="colTypeAt(ci) === 'date'"
                v-model="cell.text"
                type="date"
                value-format="YYYY-MM-DD"
                size="small"
                class="rg-field"
                @change="emitUpdate"
              />
              <input
                v-else
                v-model="cell.text"
                class="rg-input"
                :style="inputStyle(cell, ci)"
                @input="emitUpdate"
              />
            </template>
            <span v-else>{{ cell.text }}</span>
            <button
              v-if="editable && ci === row.length - 1 && model.rows.length > 1"
              class="rg-del row"
              type="button"
              title="删除此行"
              @click.stop="removeRow(ri)"
            >×</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
/**
 * 富表格编辑器：在 FormationGrid 基础上增加
 *  - 表头合并 / 拆分（colspan）
 *  - 单元格格式：对齐 / 字体 / 字号 / 粗斜下划线 / 字色 / 底色
 *  - 删除行 / 删除列组
 *
 * 格式作用于**当前选中的单元格**（先点格子再点按钮），表头也能设字体与字号，
 * 但字色/底色不跟——表头恒为灰底粗体，让它单格变色只会把表头看散。
 * 字体与字号存 key 不存 CSS 串，词表见 utils/gridFormat.js（后端 enums 有同一份）。
 *
 * 数据模型（v-model 双向绑定整个 grid 对象）：
 *   {
 *     title: string,
 *     headers: [{ text, colspan, align, font, size, bold, italic, underline }],
 *     rows: [ [{ text, align, color, bg, bold, italic, underline, font, size }, ...], ... ],
 *     colWidths:  [number, ...],             // 长度 = 正文列数
 *     colTypes:   ['text'|'select'|'date'|'light', ...],  // 每个物理列的输入格式
 *     colOptions: [ [string, ...], ... ],    // 下拉/点灯列的候选项（其余列为 []）
 *   }
 * light（点灯）＝取值受限的下拉 + 按取值给整格上红黄绿底色，词表见 utils/gridLight.js；
 * 后端在周报 HTML 与 Excel 里用同一套映射着色（enums.GRID_LIGHT_COLORS）。
 * 兼容旧格式：headers 为 string[]、rows 为 string[][]（由父级 normalize）；
 * 旧数据无 colTypes/colOptions 时按 'text' / [] 补齐。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { LIGHT_DEFAULT_OPTIONS, lightStyle } from '../utils/gridLight'
import { CELL_BGS, FONTS, FONT_SIZES, formatStyle, normFont, normSize } from '../utils/gridFormat'

const DEFAULT_W = 130

const props = defineProps({
  modelValue: { type: Object, required: true },
  editable: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

// 直接引用 props.modelValue（保持对父级替换的响应式）
const model = computed(() => props.modelValue)

const sel = ref(null) // { type:'header'|'body', r, c }

const isBodySel = computed(() => sel.value?.type === 'body')
const isHeaderSel = computed(() => sel.value?.type === 'header')
const canSplit = computed(
  () => isHeaderSel.value && (model.value.headers[sel.value.c]?.colspan || 1) > 1,
)
const selDesc = computed(() => {
  if (!sel.value) return '点击单元格后可设置对齐 / 颜色 / 合并表头 / 列格式'
  return sel.value.type === 'header' ? '已选中表头（字色/底色不适用）' : '已选中正文单元格'
})

// —— 列格式：每个物理列可设 文本 / 下拉 / 日期 ——
// colTypes[i]、colOptions[i] 与 colWidths 一样，长度 = 正文列数
const COL_TYPES = [
  { value: 'text', label: '文本' },
  { value: 'select', label: '下拉' },
  { value: 'date', label: '日期' },
  { value: 'light', label: '点灯' },
]
// 点灯列＝取值受限的下拉 + 按取值给整格上底色，故两者共用编辑控件
function isChoiceCol(ci) {
  const t = colTypeAt(ci)
  return t === 'select' || t === 'light'
}
function cellStyle(cell, ci) {
  const base = { textAlign: 'left', color: '#303133', ...formatStyle(cell) }
  // 点灯列的着色覆盖单元格自身的字色/底色/对齐：整列口径一致才看得出灯
  return colTypeAt(ci) === 'light' ? { ...base, ...(lightStyle(cell.text) || {}) } : base
}
// 表头：字体/字号/粗斜下划线跟随，字色与底色由表头样式统一决定
function headerStyle(h) {
  const { color, background, ...rest } = formatStyle(h)
  return { textAlign: 'center', ...rest }
}
// 编辑态的 input 要和只读态看起来一样，否则「保存后字变了」
// 背景与对齐已由 td 承担，input 自身只需继承字形（transparent 底 + 100% 宽）
function inputStyle(cell, ci) {
  const { background, ...rest } = cellStyle(cell, ci)
  return rest
}
function colTypeAt(ci) {
  const t = model.value.colTypes
  return (Array.isArray(t) && t[ci]) || 'text'
}
function colOptionsAt(ci) {
  const o = model.value.colOptions
  return Array.isArray(o) && Array.isArray(o[ci]) ? o[ci] : []
}
function ensureColMeta() {
  const n = bodyColCount()
  if (!Array.isArray(model.value.colTypes)) model.value.colTypes = []
  if (!Array.isArray(model.value.colOptions)) model.value.colOptions = []
  const t = model.value.colTypes
  const o = model.value.colOptions
  while (t.length < n) t.push('text')
  if (t.length > n) t.length = n
  while (o.length < n) o.push([])
  if (o.length > n) o.length = n
}
// 列格式作用于当前选中的正文单元格所在物理列
const selPhysCol = computed(() => (sel.value?.type === 'body' ? sel.value.c : -1))
const selColType = computed({
  get: () => (selPhysCol.value >= 0 ? colTypeAt(selPhysCol.value) : 'text'),
  set: (v) => {
    if (selPhysCol.value < 0) return
    ensureColMeta()
    model.value.colTypes[selPhysCol.value] = v
    // 切成点灯列时没有候选项就给一份红黄绿，否则下拉是空的、看不出该填什么
    if (v === 'light' && !colOptionsAt(selPhysCol.value).length) {
      model.value.colOptions[selPhysCol.value] = [...LIGHT_DEFAULT_OPTIONS]
    }
    emitUpdate()
  },
})
const selColOptionsText = computed({
  get: () => (selPhysCol.value >= 0 ? colOptionsAt(selPhysCol.value).join('，') : ''),
  set: (v) => {
    if (selPhysCol.value < 0) return
    ensureColMeta()
    model.value.colOptions[selPhysCol.value] =
      String(v).split(/[，,]/).map((s) => s.trim()).filter(Boolean)
    emitUpdate()
  },
})

function emitUpdate() {
  emit('update:modelValue', model.value)
}

function selectCell(type, r, c) {
  sel.value = { type, r, c }
}
function isSel(type, r, c = 0) {
  const s = sel.value
  if (!s || s.type !== type) return false
  return type === 'header' ? s.c === c : s.r === r && s.c === c
}

function bodyColCount() {
  return model.value.headers.reduce((n, h) => n + (h.colspan || 1), 0)
}

// —— 列宽：colgroup 渲染 + 拖动 ——
// 始终返回长度 = 正文列数的宽度数组（旧数据缺省按 DEFAULT_W 补齐）
const displayWidths = computed(() => {
  const n = bodyColCount()
  const w = model.value.colWidths || []
  return Array.from({ length: n }, (_, i) => Number(w[i]) || DEFAULT_W)
})
function ensureWidths() {
  if (!Array.isArray(model.value.colWidths)) model.value.colWidths = []
  const w = model.value.colWidths
  const n = bodyColCount()
  while (w.length < n) w.push(DEFAULT_W)
  if (w.length > n) w.length = n
}
function lastPhysCol(hi) {
  return groupOffset(hi) + (model.value.headers[hi].colspan || 1) - 1
}
let resizing = null
function startResize(e, hi) {
  ensureWidths()
  const col = lastPhysCol(hi)
  resizing = { col, startX: e.clientX, startW: model.value.colWidths[col] || DEFAULT_W }
  window.addEventListener('mousemove', onResize)
  window.addEventListener('mouseup', stopResize)
}
function onResize(e) {
  if (!resizing) return
  model.value.colWidths[resizing.col] = Math.max(48, resizing.startW + (e.clientX - resizing.startX))
}
function stopResize() {
  window.removeEventListener('mousemove', onResize)
  window.removeEventListener('mouseup', stopResize)
  if (resizing) {
    resizing = null
    emitUpdate()
  }
}
onMounted(() => { ensureWidths(); ensureColMeta() })
onBeforeUnmount(stopResize)

function setAlign(align) {
  const s = sel.value
  if (!s) return
  if (s.type === 'header') model.value.headers[s.c].align = align
  else model.value.rows[s.r][s.c].align = align
  emitUpdate()
}
// —— 单元格格式：一律作用于「当前选中的那一格」——
// 表头与正文格共用同一套字段名，故取到对象后按同样的方式改，
// 只有字色/底色限正文（表头恒为灰底，单格变色会把表头看散）。
const PREDEFINE_TEXT_COLORS = [
  '#303133', '#C7000B', '#1565C0', '#67C23A', '#E6A23C', '#909399', '#F56C6C',
]

function selCell() {
  const s = sel.value
  if (!s) return null
  return s.type === 'header' ? model.value.headers[s.c] : model.value.rows[s.r]?.[s.c]
}

function setOnSel(patch, bodyOnly = false) {
  const s = sel.value
  if (!s || (bodyOnly && s.type !== 'body')) return
  const cell = selCell()
  if (!cell) return
  Object.assign(cell, patch)
  emitUpdate()
}

function selFlag(name) {
  return !!selCell()?.[name]
}
function toggleFlag(name) {
  const cell = selCell()
  if (!cell) return
  setOnSel({ [name]: !cell[name] })
}

const selFont = computed({
  get: () => normFont(selCell()?.font),
  set: (v) => setOnSel({ font: normFont(v) }),
})
const selSize = computed({
  get: () => normSize(selCell()?.size),
  set: (v) => setOnSel({ size: normSize(v) }),
})
const selColor = computed({
  get: () => selCell()?.color || '',
  set: (v) => setOnSel({ color: v || '' }, true),
})
const selBg = computed({
  get: () => selCell()?.bg || '',
  set: (v) => setOnSel({ bg: v || '' }, true),
})

function clearFormat() {
  setOnSel({ color: '', bg: '', bold: false, italic: false, underline: false,
             font: '', size: '' })
}

function mergeHeader() {
  const s = sel.value
  if (!s || s.type !== 'header') return
  const hs = model.value.headers
  if (s.c >= hs.length - 1) return // 已是最后一个
  hs[s.c].colspan = (hs[s.c].colspan || 1) + (hs[s.c + 1].colspan || 1)
  hs.splice(s.c + 1, 1)
  emitUpdate()
}
function splitHeader() {
  const s = sel.value
  if (!s || s.type !== 'header') return
  const hs = model.value.headers
  const span = hs[s.c].colspan || 1
  if (span <= 1) return
  hs[s.c].colspan = 1
  const extra = []
  for (let i = 1; i < span; i++) extra.push({ text: '', colspan: 1, align: 'center' })
  hs.splice(s.c + 1, 0, ...extra)
  emitUpdate()
}

function newCell() {
  return { text: '', align: 'left', color: '' }
}
// 选中单元格所属的表头组下标（正文列 → 覆盖它的表头组）
function selGroupIndex() {
  const s = sel.value
  if (!s) return -1
  if (s.type === 'header') return s.c
  let acc = 0
  const hs = model.value.headers
  for (let i = 0; i < hs.length; i++) {
    const span = hs[i].colspan || 1
    if (s.c < acc + span) return i
    acc += span
  }
  return hs.length - 1
}
function groupOffset(gi) {
  let offset = 0
  for (let i = 0; i < gi; i++) offset += model.value.headers[i].colspan || 1
  return offset
}

// —— 行：指定位置插入 / 删除 ——
function insertRow(pos) {
  const n = bodyColCount() || 1
  const row = Array.from({ length: n }, newCell)
  const s = sel.value
  let at
  if (s && s.type === 'body') at = pos === 'above' ? s.r : s.r + 1
  else at = pos === 'above' ? 0 : model.value.rows.length
  model.value.rows.splice(at, 0, row)
  emitUpdate()
}
function deleteSelRow() {
  const s = sel.value
  if (!s || s.type !== 'body') return
  if (model.value.rows.length <= 1) return
  model.value.rows.splice(s.r, 1)
  sel.value = null
  emitUpdate()
}
function removeRow(ri) {
  if (model.value.rows.length <= 1) return
  model.value.rows.splice(ri, 1)
  if (sel.value?.type === 'body') sel.value = null
  emitUpdate()
}

// —— 列：指定位置插入 / 删除 ——
function insertCol(side) {
  const hs = model.value.headers
  const gi = selGroupIndex()
  let headerAt, bodyAt
  if (gi < 0) {
    headerAt = hs.length
    bodyAt = bodyColCount()
  } else {
    const offset = groupOffset(gi)
    headerAt = side === 'left' ? gi : gi + 1
    bodyAt = side === 'left' ? offset : offset + (hs[gi].colspan || 1)
  }
  hs.splice(headerAt, 0, { text: '新列', colspan: 1, align: 'center' })
  model.value.rows.forEach(r => r.splice(bodyAt, 0, newCell()))
  ensureWidths()
  model.value.colWidths.splice(bodyAt, 0, DEFAULT_W)
  ensureColMeta()
  model.value.colTypes.splice(bodyAt, 0, 'text')
  model.value.colOptions.splice(bodyAt, 0, [])
  emitUpdate()
}
function deleteSelCol() {
  const gi = selGroupIndex()
  if (gi >= 0) removeHeader(gi)
}
function removeHeader(hi) {
  const hs = model.value.headers
  if (hs.length <= 1) return
  const offset = groupOffset(hi)
  const span = hs[hi].colspan || 1
  hs.splice(hi, 1)
  model.value.rows.forEach(r => r.splice(offset, span))
  ensureWidths()
  model.value.colWidths.splice(offset, span)
  ensureColMeta()
  model.value.colTypes.splice(offset, span)
  model.value.colOptions.splice(offset, span)
  sel.value = null
  emitUpdate()
}
</script>

<style scoped>
.rich-grid { font-family: '微软雅黑', 'Microsoft YaHei', sans-serif; overflow-x: auto; }
.rg-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 6px 8px;
  background: #fafbfc;
  border: 1px solid #ebeef5;
  border-bottom: none;
}
.rg-toolbar .spacer { flex: 1; }
.rg-tip { font-size: 12px; color: #909399; }
.rg-fmt { display: inline-flex; align-items: center; gap: 6px; }
.rg-typesel { width: 92px; }
.rg-fontsel { width: 108px; }
.rg-sizesel { width: 96px; }
.rg-bgsel { width: 100px; }
.rg-optinput { width: 200px; }
/* 单元格内的下拉 / 日期控件铺满列宽 */
.rg-table td :deep(.rg-field) { width: 100%; }
.rg-table td :deep(.el-input__wrapper) { padding: 0 6px; box-shadow: none; }
.rg-table td :deep(.el-select__wrapper) { min-height: 26px; }
.swatch {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  vertical-align: middle;
  margin-right: 2px;
}
.rg-table {
  border-collapse: collapse;
  /* 固定布局：列宽由 colgroup 控制，可拖动 */
  table-layout: fixed;
  width: max-content;
  min-width: 100%;
}
.rg-table th, .rg-table td {
  border: 1px solid #dcdfe6;
  padding: 4px 6px;
  height: 32px;
  position: relative;
  vertical-align: middle;
  overflow: hidden;
}
.rg-table th { background: #f5f7fa; font-weight: 700; }
/* 表头加粗并与本页 el-table 表头（16px）一致，避免新增表格表头显得偏细 */
.rg-table th .rg-input, .rg-table th > span { font-weight: 700; font-size: 16px; }
.rg-table th.selected, .rg-table td.selected {
  outline: 2px solid #C7000B;
  outline-offset: -2px;
}
.rg-input {
  border: none;
  outline: none;
  width: 100%;
  background: transparent;
  font-size: 13px;
  font-family: inherit;
  color: inherit;
}
.rg-input.bold { font-weight: 700; }
.rg-del {
  position: absolute;
  border: none;
  background: transparent;
  color: #f56c6c;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}
.rg-del.col { right: 10px; top: 2px; }
.rg-del.row { right: -22px; top: 50%; transform: translateY(-50%); }
.rg-del:hover { color: #c45656; }
.rg-resizer {
  position: absolute;
  top: 0;
  right: -3px;
  width: 7px;
  height: 100%;
  cursor: col-resize;
  user-select: none;
  z-index: 3;
}
.rg-resizer:hover { background: rgba(199, 0, 11, 0.25); }
</style>
