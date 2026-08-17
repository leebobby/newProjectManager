<template>
  <table v-if="model.headers.length || model.rows.length" class="formation-table">
    <thead>
      <tr>
        <th v-for="(h, ci) in model.headers" :key="'h' + ci">
          <input
            v-if="editable"
            v-model="model.headers[ci]"
            class="cell-input bold"
            placeholder="列标题"
            @input="emitUpdate"
          />
          <span v-else>{{ h }}</span>
          <button
            v-if="editable && model.headers.length > 1"
            class="del-btn col"
            type="button"
            @click="removeCol(ci)"
            title="删除此列"
          >×</button>
        </th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="(row, ri) in model.rows" :key="'r' + ri">
        <td v-for="(_, ci) in model.headers" :key="'c' + ri + '-' + ci">
          <input
            v-if="editable"
            v-model="model.rows[ri][ci]"
            class="cell-input"
            @input="emitUpdate"
          />
          <span v-else>{{ model.rows[ri][ci] }}</span>
          <button
            v-if="editable && ci === model.headers.length - 1"
            class="del-btn row"
            type="button"
            @click="removeRow(ri)"
            title="删除此行"
          >×</button>
        </td>
      </tr>
    </tbody>
  </table>
</template>

<script setup>
/**
 * 通用网格编辑器：headers + rows[][] 的二维文本表。
 * 通过 v-model 双向绑定整个 grid 对象（{headers, rows, ...others}）。
 */
import { computed } from 'vue'

const props = defineProps({
  modelValue: {
    type: Object,
    required: true,
  },
  editable: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

// 用 computed 始终读取最新 props.modelValue：父级在切换专项时会整体替换
// 该对象，若用 `const model = props.modelValue` 捕获一次会导致旧数据串台。
const model = computed(() => props.modelValue)

function emitUpdate() {
  emit('update:modelValue', model.value)
}

function removeCol(ci) {
  model.value.headers.splice(ci, 1)
  model.value.rows.forEach(r => r.splice(ci, 1))
  emitUpdate()
}

function removeRow(ri) {
  model.value.rows.splice(ri, 1)
  emitUpdate()
}
</script>

<style scoped>
.formation-table {
  border-collapse: collapse;
  width: 100%;
}
.formation-table th, .formation-table td {
  border: 1px solid #dcdfe6;
  padding: 4px 6px;
  min-width: 100px;
  height: 32px;
  position: relative;
  vertical-align: middle;
}
.formation-table th {
  background: #f5f7fa;
  font-weight: 600;
}
.cell-input {
  border: none;
  outline: none;
  width: 100%;
  background: transparent;
  font-size: 13px;
}
.cell-input.bold { font-weight: 600; text-align: center; }
.del-btn {
  position: absolute;
  border: none;
  background: transparent;
  color: #f56c6c;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}
.del-btn.col {
  right: 2px;
  top: 50%;
  transform: translateY(-50%);
}
.del-btn.row {
  right: -22px;
  top: 50%;
  transform: translateY(-50%);
}
.del-btn:hover { color: #c45656; }
</style>
