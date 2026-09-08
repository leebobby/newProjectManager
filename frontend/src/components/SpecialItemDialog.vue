<template>
  <el-dialog
    :model-value="modelValue"
    :title="(item ? '编辑' : '新增') + (kind === 'task' ? '事务' : '风险/问题')"
    width="520px"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form :model="form" label-width="100px">
      <el-form-item :label="kind === 'task' ? '事务内容' : '问题内容'">
        <RichTextEditor v-model="form.content" min-height="90px" placeholder="支持加粗 / 字号 / 颜色" />
      </el-form-item>
      <el-form-item :label="kind === 'task' ? '当前进展' : '应对措施'">
        <RichTextEditor v-model="form.progress" min-height="70px" placeholder="支持加粗 / 字号 / 颜色" />
      </el-form-item>
      <el-form-item label="责任人">
        <el-input v-model="form.owner" />
      </el-form-item>
      <el-form-item label="计划闭环时间">
        <el-input v-model="form.planned_close_date" placeholder="YYYY-MM-DD 或自由文本" />
      </el-form-item>
      <el-form-item label="当前状态">
        <el-radio-group v-model="form.status">
          <el-radio value="open">Open</el-radio>
          <el-radio value="closed">Closed</el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
/**
 * 专项的「事务 / 风险」行编辑框。**详情页与总览页共用这一份**。
 *
 * 两处各写一份表单的表现是：加一个字段只加在其中一页上，另一页保存时
 * `exclude_unset` 那一侧把它当成"没传"，于是在这一页填的值到那一页一保存就没了，
 * 而两边看着都对。所以字段清单只在这儿列一次。
 */
import { reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import RichTextEditor from './RichTextEditor.vue'
import { specialApi, apiError } from '../api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  kind: { type: String, default: 'risk' },     // task | risk
  specialId: { type: [Number, String], default: null },
  item: { type: Object, default: null },       // null＝新增
})
const emit = defineEmits(['update:modelValue', 'saved'])

function blank() {
  return { content: '', progress: '', owner: '', planned_close_date: '', status: 'open' }
}

const form = reactive(blank())
const saving = ref(false)

watch(
  () => [props.modelValue, props.item],
  ([open]) => {
    if (!open) return
    const src = props.item || blank()
    Object.assign(form, blank(), {
      content: src.content || '',
      progress: src.progress || '',
      owner: src.owner || '',
      planned_close_date: src.planned_close_date || '',
      status: src.status || 'open',
    })
  },
  { immediate: true },
)

async function onSave() {
  saving.value = true
  try {
    if (props.item) {
      const api = props.kind === 'task' ? specialApi.updateTask : specialApi.updateRisk
      await api(props.item.id, { ...form })
    } else {
      const api = props.kind === 'task' ? specialApi.createTask : specialApi.createRisk
      await api(props.specialId, { ...form })
    }
    emit('update:modelValue', false)
    emit('saved')
    ElMessage.success('已保存')
  } catch (e) {
    // 409/423（他人持编辑锁）由 api/index.js 的拦截器统一弹提示
    if (![409, 423].includes(e?.response?.status)) ElMessage.error(apiError(e, '保存失败'))
  } finally {
    saving.value = false
  }
}
</script>
