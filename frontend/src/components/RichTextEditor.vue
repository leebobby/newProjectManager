<template>
  <div class="rich-editor">
    <div class="toolbar" @mousedown="saveSelection">
      <el-button
        size="small"
        :type="state.bold ? 'primary' : 'default'"
        @mousedown.prevent
        @click="exec('bold')"
        title="加粗 (Ctrl+B)"
      >
        <b>B</b>
      </el-button>
      <el-select
        v-model="fontFamily"
        size="small"
        style="width: 110px"
        placeholder="字体"
        @change="applyFontFamily"
      >
        <el-option v-for="f in FONT_FAMILIES" :key="f.value" :label="f.label" :value="f.value" />
      </el-select>
      <el-select
        v-model="fontSize"
        size="small"
        style="width: 110px"
        placeholder="字号"
        @change="applyFontSize"
      >
        <el-option v-for="s in FONT_SIZES" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
      <el-button-group class="quick-colors">
        <el-button size="small" title="黑色" @mousedown.prevent @click="applyColor('#303133')">
          <span class="dot" style="background:#303133" />
        </el-button>
        <el-button size="small" title="红色" @mousedown.prevent @click="applyColor('#C7000B')">
          <span class="dot" style="background:#C7000B" />
        </el-button>
        <el-button size="small" title="蓝色" @mousedown.prevent @click="applyColor('#1565C0')">
          <span class="dot" style="background:#1565C0" />
        </el-button>
      </el-button-group>
      <el-color-picker
        v-model="color"
        size="small"
        :predefine="PREDEFINE_COLORS"
        @change="applyColor"
      />
      <el-button
        size="small"
        @mousedown.prevent
        @click="exec('removeFormat')"
        title="清除格式"
      >清除格式</el-button>
      <slot name="toolbar-extra" />
    </div>
    <div
      ref="editorRef"
      class="content"
      contenteditable="true"
      :style="{ minHeight }"
      :data-placeholder="placeholder"
      @input="onInput"
      @blur="saveSelection"
      @keyup="onSelectionChanged"
      @mouseup="onSelectionChanged"
      @paste="onPaste"
    ></div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  minHeight: { type: String, default: '100px' },
  placeholder: { type: String, default: '在此输入内容…' },
})
const emit = defineEmits(['update:modelValue'])

const editorRef = ref(null)
const fontSize = ref('')
const fontFamily = ref('')
const color = ref('')
const state = reactive({ bold: false })
let savedRange = null

const FONT_FAMILIES = [
  // 用单引号包裹，避免后端富文本清洗器（拒绝双引号）丢弃 font-family
  { label: '微软雅黑', value: "'Microsoft YaHei', 微软雅黑, sans-serif" },
  { label: '宋体', value: 'SimSun, 宋体, serif' },
]

const FONT_SIZES = [
  { label: '小 12', value: '12px' },
  { label: '正常 14', value: '14px' },
  { label: '中 16', value: '16px' },
  { label: '大 18', value: '18px' },
  { label: '超大 22', value: '22px' },
  { label: '巨大 28', value: '28px' },
]
const PREDEFINE_COLORS = [
  '#303133', '#C7000B', '#1565C0',
  '#606266', '#909399',
  '#409EFF', '#67C23A', '#E6A23C', '#F56C6C',
]

onMounted(() => {
  if (editorRef.value) {
    editorRef.value.innerHTML = props.modelValue || ''
    editorRef.value.focus()
    placeCaretAtEnd(editorRef.value)
  }
})

watch(() => props.modelValue, (v) => {
  if (editorRef.value && editorRef.value.innerHTML !== (v || '')) {
    editorRef.value.innerHTML = v || ''
  }
})

function placeCaretAtEnd(el) {
  const range = document.createRange()
  range.selectNodeContents(el)
  range.collapse(false)
  const sel = window.getSelection()
  sel.removeAllRanges()
  sel.addRange(range)
}

function onInput() {
  emit('update:modelValue', editorRef.value.innerHTML)
}

function saveSelection() {
  const sel = window.getSelection()
  if (!sel || sel.rangeCount === 0) return
  const range = sel.getRangeAt(0)
  if (editorRef.value && editorRef.value.contains(range.commonAncestorContainer)) {
    savedRange = range.cloneRange()
  }
}

function restoreSelection() {
  if (!savedRange) {
    editorRef.value?.focus()
    return false
  }
  editorRef.value?.focus()
  const sel = window.getSelection()
  sel.removeAllRanges()
  sel.addRange(savedRange)
  return true
}

function onSelectionChanged() {
  saveSelection()
  try { state.bold = document.queryCommandState('bold') } catch { state.bold = false }
}

function exec(cmd, value = null) {
  restoreSelection()
  try { document.execCommand('styleWithCSS', false, true) } catch {}
  document.execCommand(cmd, false, value)
  onInput()
  onSelectionChanged()
}

function applyFontSize(px) {
  if (!px) return
  restoreSelection()
  wrapSelectionStyle('fontSize', px)
  onInput()
  fontSize.value = ''
}

function applyFontFamily(family) {
  if (!family) return
  restoreSelection()
  wrapSelectionStyle('fontFamily', family)
  onInput()
  fontFamily.value = ''
}

function applyColor(hex) {
  if (!hex) return
  exec('foreColor', hex)
}

function wrapSelectionStyle(prop, val) {
  const sel = window.getSelection()
  if (!sel || sel.rangeCount === 0) return
  const range = sel.getRangeAt(0)
  if (range.collapsed) return
  const span = document.createElement('span')
  span.style[prop] = val
  try {
    span.appendChild(range.extractContents())
    range.insertNode(span)
    sel.removeAllRanges()
    const newRange = document.createRange()
    newRange.selectNodeContents(span)
    sel.addRange(newRange)
    savedRange = newRange.cloneRange()
  } catch {}
}

function onPaste(e) {
  e.preventDefault()
  const text = (e.clipboardData || window.clipboardData).getData('text/plain') || ''
  document.execCommand('insertText', false, text)
}

defineExpose({
  focus: () => editorRef.value?.focus(),
  getHtml: () => editorRef.value?.innerHTML || '',
})
</script>

<style scoped>
.rich-editor {
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
  background: #fff;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  background: #fafbfc;
  border-bottom: 1px solid #ebeef5;
  flex-wrap: wrap;
}
.quick-colors .dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 2px;
  vertical-align: middle;
}
.content {
  padding: 10px 12px;
  outline: none;
  line-height: 1.65;
  font-size: 14px;
  color: #303133;
  font-family: '微软雅黑', 'Microsoft YaHei', sans-serif;
  word-break: break-word;
  white-space: pre-wrap;
}
.content[contenteditable="true"]:empty::before {
  content: attr(data-placeholder);
  color: #c0c4cc;
  pointer-events: none;
}
</style>
