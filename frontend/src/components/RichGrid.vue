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
      <el-button size="small" :disabled="!isBodySel" :type="selBold ? 'primary' : ''" @click="toggleBold">
        <b>B</b> 加粗
      </el-button>
      <el-button-group>
        <el-button size="small" :disabled="!isBodySel" @click="setColor('')">
          <span class="swatch" style="background:#303133" /> 黑
        </el-button>
        <el-button size="small" :disabled="!isBodySel" @click="setColor('#C7000B')">
          <span class="swatch" style="background:#C7000B" /> 红
        </el-button>
        <el-button size="small" :disabled="!isBodySel" @click="setColor('#1565C0')">
          <span class="swatch" style="background:#1565C0" /> 蓝
        </el-button>
      </el-button-group>
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
          v-if="isBodySel && selColType === 'select'"
          v-model="selColOptionsText"
          size="small"
          class="rg-optinput"
          placeholder="下拉选项，逗号分隔"
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
            :style="{ textAlign: h.align || 'center' }"
            @click="editable && selectCell('header', 0, hi)"
          >
            <input
              v-if="editable"
              v-model="h.text"
              class="rg-input bold"
              :style="{ textAlign: h.align || 'center' }"
              placeholder="表头"
              @input="emitUpdate"
            />
            <span v-else>{{ h.text }}</span>
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
            :style="{ textAlign: cell.align || 'left', color: cell.color || '#303133', fontWeight: cell.bold ? 700 : 400 }"
            @click="editable && selectCell('body', ri, ci)"
          >
            <template v-if="editable">
              <el-select
                v-if="colTypeAt(ci) === 'select'"
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
                :style="{ textAlign: cell.align || 'left', color: cell.color || '#303133', fontWeight: cell.bold ? 700 : 400 }"
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
 *  - 单元格对齐（左 / 居中）
 *  - 正文单元格字体颜色（黑 / 红 / 蓝）
 *  - 删除行 / 删除列组
 *
 * 数据模型（v-model 双向绑定整个 grid 对象）：
 *   {
 *     title: string,
 *     headers: [{ text, colspan, align }],   // sum(colspan) === 正文列数
 *     rows: [ [{ text, align, color, bold }, ...], ... ],
 *     colWidths:  [number, ...],             // 长度 = 正文列数
 *     colTypes:   ['text'|'select'|'date', ...],  // 每个物理列的输入格式
 *     colOptions: [ [string, ...], ... ],    // 下拉列的候选项（其余列为 []）
 *   }
 * 兼容旧格式：headers 为 string[]、rows 为 string[][]（由父级 normalize）；
 * 旧数据无 colTypes/colOptions 时按 'text' / [] 补齐。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

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
  return sel.value.type === 'header' ? '已选中表头' : '已选中正文单元格'
})

// —— 列格式：每个物理列可设 文本 / 下拉 / 日期 ——
// colTypes[i]、colOptions[i] 与 colWidths 一样，长度 = 正文列数
const COL_TYPES = [
  { value: 'text', label: '文本' },
  { value: 'select', label: '下拉' },
  { value: 'date', label: '日期' },
]
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
function setColor(color) {
  const s = sel.value
  if (!s || s.type !== 'body') return
  model.value.rows[s.r][s.c].color = color
  emitUpdate()
}

// —— 加粗（正文单元格；表头本就恒为粗体）——
const selBold = computed(() => {
  const s = sel.value
  return s?.type === 'body' ? !!model.value.rows[s.r]?.[s.c]?.bold : false
})
function toggleBold() {
  const s = sel.value
  if (!s || s.type !== 'body') return
  const cell = model.value.rows[s.r][s.c]
  cell.bold = !cell.bold
  emitUpdate()
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
