<template>
  <!-- 激活态：挂载真正的 el-select（含全部选项），自动聚焦并展开下拉 -->
  <el-select
    v-if="active"
    ref="selRef"
    :model-value="value"
    :clearable="clearable"
    :filterable="filterable"
    :allow-create="allowCreate"
    :placeholder="placeholder"
    automatic-dropdown
    size="small"
    style="width: 100%"
    @change="onChange"
    @visible-change="onVisible"
  >
    <slot />
  </el-select>

  <!-- 空闲态：仅渲染轻量文本，避免 80 行 × 多列同时挂载 el-select 拖慢首屏 -->
  <div v-else :class="['edit-select-cell', tone ? 'tone-' + tone : '']" @click="activate">
    <span class="esc-text" :class="{ 'esc-empty': isEmpty }">
      <slot name="display">{{ isEmpty ? placeholder : displayText }}</slot>
    </span>
    <el-icon class="esc-caret"><ArrowDown /></el-icon>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'

const props = defineProps({
  // 绑定值（可能是 FK id 或自由字符串）
  value: { default: null },
  // 空闲态展示文本
  displayText: { type: String, default: '' },
  clearable: { type: Boolean, default: false },
  filterable: { type: Boolean, default: false },
  allowCreate: { type: Boolean, default: false },
  placeholder: { type: String, default: '选择' },
  // 空闲态着色：'success'（绿，如已完成）/ 'danger'（红，如已延期）/ ''（默认）
  tone: { type: String, default: '' },
})
const emit = defineEmits(['change'])

const active = ref(false)
const selRef = ref(null)
const isEmpty = computed(() => props.displayText === '' || props.displayText == null)

function activate() {
  active.value = true
  // automatic-dropdown：聚焦即展开下拉，单击体验与原内联 select 一致
  nextTick(() => selRef.value?.focus())
}
function onChange(v) {
  emit('change', v)
  active.value = false
}
function onVisible(visible) {
  // 关闭下拉（选中 / 点空白 / Esc）即退出编辑态，回到轻量文本
  if (!visible) active.value = false
}
</script>

<style scoped>
.edit-select-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  min-height: 24px;
  padding: 1px 6px;
  border-radius: 4px;
  cursor: pointer;
}
/* 状态着色（仅着色当前单元格，不影响整行）；放在 :hover 之前，hover 时蓝色编辑提示优先 */
.edit-select-cell.tone-success { background: #f0f9eb; color: #529b2e; font-weight: 600; }
.edit-select-cell.tone-danger { background: #fef0f0; color: #c45656; font-weight: 600; }
.edit-select-cell:hover {
  background: #f0f7ff;
  outline: 1px dashed #c6e2ff;
}
.esc-text {
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.esc-empty { color: #c0c4cc; }
.esc-caret {
  flex: 0 0 auto;
  font-size: 12px;
  color: #c7cad0;
}
.edit-select-cell.tone-success .esc-caret { color: #95d475; }
.edit-select-cell.tone-danger .esc-caret { color: #f89898; }
.edit-select-cell:hover .esc-caret { color: #909399; }
</style>
