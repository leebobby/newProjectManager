<template>
  <div class="editable-text">
    <!-- 展示态 -->
    <div
      v-if="!editing"
      class="display"
      :class="{ readonly: !editable, empty: !value, rich }"
      @click="onEnter"
    >
      <template v-if="value">
        <div v-if="rich" class="text rich-display" v-html="value" />
        <span v-else class="text">{{ value }}</span>
      </template>
      <span v-else class="ph">{{ placeholder }}</span>
    </div>

    <!-- 编辑态：纯文本 -->
    <div v-else-if="!rich" class="edit">
      <el-input
        v-model="draft"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 10 }"
        :placeholder="placeholder"
        @keydown.ctrl.enter.prevent="save"
        @keydown.meta.enter.prevent="save"
      />
      <div class="actions">
        <el-button size="small" type="primary" @click="save">保存 (Ctrl+Enter)</el-button>
        <el-button size="small" @click="cancel">取消</el-button>
      </div>
    </div>

    <!-- 编辑态：富文本 -->
    <div v-else class="edit">
      <RichTextEditor v-model="draft" :placeholder="placeholder" />
      <div class="actions">
        <el-button size="small" type="primary" @click="save">保存</el-button>
        <el-button size="small" @click="cancel">取消</el-button>
        <span class="hint">支持加粗 / 字号 / 颜色，粘贴自动转为纯文本</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import RichTextEditor from './RichTextEditor.vue'

const props = defineProps({
  value: { type: String, default: '' },
  editable: { type: Boolean, default: true },
  placeholder: { type: String, default: '点击编辑...' },
  rich: { type: Boolean, default: false },
})
const emit = defineEmits(['save'])

const editing = ref(false)
const draft = ref('')

function onEnter() {
  if (!props.editable) return
  draft.value = props.value || ''
  editing.value = true
}

function save() {
  emit('save', draft.value)
  editing.value = false
}

function cancel() {
  editing.value = false
}
</script>

<style scoped>
.display {
  cursor: text;
  padding: 8px 10px;
  border-radius: 4px;
  border: 1px dashed transparent;
  min-height: 48px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.display.rich {
  white-space: normal;
}
.display.rich .rich-display {
  white-space: pre-wrap;
  word-break: break-word;
}
.display:hover:not(.readonly) {
  background: #f0f7ff;
  border-color: #c6e2ff;
}
.display.readonly {
  cursor: default;
}
.display .ph {
  color: #c0c4cc;
}
.actions {
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.actions .hint {
  color: #909399;
  font-size: 12px;
}
</style>
