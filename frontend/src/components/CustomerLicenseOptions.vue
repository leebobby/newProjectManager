<template>
  <el-button :size="size" :icon="Setting" @click="open">客户面信息配置</el-button>
  <el-dialog v-model="visible" title="客户面信息配置" width="680px" append-to-body>
    <el-alert title="机台类型与总览型号、新增机台共用；其他选项用于 License 管理。正在使用的选项不能删除。" type="info" :closable="false" />
    <el-form v-loading="loading" label-width="125px" style="margin-top: 20px">
      <el-form-item v-for="field in licenseFields" :key="field.key" :label="field.label">
        <el-select v-model="draft[field.config]" :aria-label="field.label + '配置'" multiple filterable allow-create default-first-option
                   placeholder="输入选项后回车添加" style="width: 100%" :persistent="false">
          <el-option v-for="value in draft[field.config]" :key="value" :value="value" :label="value" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="loading" @click="save">保存配置</el-button>
    </template>
  </el-dialog>
</template>
<script setup>
import { reactive, ref } from 'vue'
import { Setting } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { apiError, configApi } from '../api'
import { licenseFields } from '../utils/licenseFields'
defineProps({ size: { type: String, default: 'default' } })
const emit = defineEmits(['saved'])
const visible = ref(false), loading = ref(false), saving = ref(false)
const draft = reactive({})
async function open() {
  visible.value = true
  loading.value = true
  try {
    const { data } = await configApi.get()
    for (const field of licenseFields) draft[field.config] = [...(data[field.config] || [])]
  } catch (e) { ElMessage.error(apiError(e, '加载客户面配置失败')) }
  finally { loading.value = false }
}
async function save() {
  saving.value = true
  try {
    const { data } = await configApi.save({ ...draft })
    visible.value = false
    emit('saved', data)
    ElMessage.success('客户面信息配置已保存')
  } catch (e) { ElMessage.error(apiError(e, '保存配置失败')) }
  finally { saving.value = false }
}
</script>
