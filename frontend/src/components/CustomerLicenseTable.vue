<template>
  <section class="license-block" v-loading="loading">
    <div class="license-head">
      <b>License 管理</b><span class="hint">型号与机台总览同步 · 更新文件保留历史版本</span>
      <div class="actions">
        <CustomerLicenseOptions v-if="canEdit" size="small" @saved="config = $event" />
        <el-button v-if="canEdit" size="small" type="primary" plain @click="openEditor()">新增 License</el-button>
        <el-button size="small" @click="load">刷新</el-button>
      </div>
    </div>
    <div class="machine-model">总览型号：<el-tag size="small">{{ machine.model || '未设置' }}</el-tag>
      <HistoryActions entity="customer_machine" :entity-id="machine.id" link label="型号变更历史" />
    </div>
    <el-table :data="pageRows" border stripe size="small" empty-text="暂无 License，请新增授权信息" row-key="id">
      <el-table-column label="机台类型" min-width="145">
        <template #default>
          <el-select :model-value="machine.model" aria-label="机台类型" :disabled="!canEdit || modelSaving" :persistent="false"
                     filterable @visible-change="v => v && loadOptions()" @change="value => changeModel(value)">
            <el-option v-for="v in choices(licenseFields[0], machine.model)" :key="v" :value="v" :label="v" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="ToolID（网元名称）" min-width="175">
        <template #default="{ row }"><el-input v-model="row.tool_id" aria-label="ToolID（网元名称）" :disabled="!canEdit || busy === row.id" @change="v => saveCell(row, 'tool_id', v)" /></template>
      </el-table-column>
      <el-table-column label="UUID" min-width="245">
        <template #default="{ row }"><el-input v-model="row.uuid" aria-label="UUID" :disabled="!canEdit || busy === row.id" @change="v => saveCell(row, 'uuid', v)" /></template>
      </el-table-column>
      <el-table-column v-for="field in licenseFields.slice(1)" :key="field.key" :label="field.label" :min-width="field.multiple ? 210 : 155">
        <template #default="{ row }">
          <el-select v-model="row[field.key]" :aria-label="field.label" :multiple="field.multiple" :disabled="!canEdit || busy === row.id"
                     filterable clearable collapse-tags collapse-tags-tooltip :persistent="false" style="width: 100%"
                     @visible-change="v => v && loadOptions()" @change="v => saveCell(row, field.key, field.multiple ? v : (v || ''))">
            <el-option v-for="v in choices(field, row[field.key])" :key="v" :value="v" :label="v" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="License 文件" min-width="265">
        <template #default="{ row }">
          <template v-if="row.file_version">
            <div class="file-name">{{ row.file_name }} <el-tag size="small" type="success">V{{ row.file_version }}</el-tag></div>
            <div class="hint">{{ bytes(row.file_size) }} · {{ row.uploaded_by }} · {{ date(row.uploaded_at) }}</div>
            <el-button link type="primary" size="small" @click="download(row)">下载当前文件</el-button>
          </template>
          <span v-else class="hint">待上传</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="245" fixed="right">
        <template #default="{ row }">
          <el-button v-if="canEdit" link type="primary" @click="openUpload(row)">{{ row.file_version ? '更新文件' : '上传文件' }}</el-button>
          <el-button v-if="canEdit" link type="primary" @click="openEditor(row)">编辑</el-button>
          <el-button link type="primary" @click="openHistory(row)">变更历史</el-button>
          <el-button v-if="canEdit" link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination v-if="rows.length > 10" v-model:current-page="page" :page-size="10" :total="rows.length" layout="total, prev, pager, next" />

    <el-dialog v-model="editor.visible" :title="editor.row ? '编辑 License' : '新增 License'" width="600px" append-to-body :close-on-click-modal="false">
      <el-form label-width="125px">
        <el-form-item label="机台类型"><el-input :model-value="machine.model || '未设置'" disabled /><span class="hint">与机台总览共用，可在表格中修改。</span></el-form-item>
        <el-form-item label="ToolID（网元名称）"><el-input v-model="editor.form.tool_id" aria-label="ToolID（网元名称）" maxlength="256" /></el-form-item>
        <el-form-item label="UUID"><el-input v-model="editor.form.uuid" aria-label="UUID" maxlength="256" /></el-form-item>
        <el-form-item v-for="field in licenseFields.slice(1)" :key="field.key" :label="field.label">
          <el-select v-model="editor.form[field.key]" :aria-label="field.label" :multiple="field.multiple" filterable clearable style="width:100%" :persistent="false">
            <el-option v-for="v in choices(field, editor.form[field.key])" :key="v" :value="v" :label="v" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="editor.form.remark" type="textarea" maxlength="10000" /></el-form-item>
        <el-form-item v-if="!editor.row" label="License 文件">
          <el-upload :key="editor.key" :auto-upload="false" :limit="1" :on-change="f => editor.file = f.raw" :on-remove="() => editor.file = null">
            <el-button>选择文件</el-button><template #tip><div class="hint">可以先填写授权信息，再上传文件。</div></template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="editor.visible = false">取消</el-button><el-button type="primary" :loading="editor.saving" @click="saveEditor">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="upload.visible" title="上传 License 新版本" width="540px" append-to-body :close-on-click-modal="false">
      <el-alert title="新文件成为当前版本，旧版文件与当时的授权信息会保留。" type="info" :closable="false" />
      <el-upload :key="upload.key" drag :auto-upload="false" :limit="1" :on-change="f => upload.file = f.raw" :on-remove="() => upload.file = null" style="margin-top:16px">
        <div>点击选择或拖入 License 文件</div>
      </el-upload>
      <el-input v-model="upload.note" type="textarea" placeholder="本次变更说明" maxlength="10000" style="margin-top:12px" />
      <template #footer><el-button @click="upload.visible = false">取消</el-button><el-button type="primary" :loading="upload.saving" @click="saveUpload">上传新版本</el-button></template>
    </el-dialog>

    <el-drawer v-model="history.visible" title="License 变更历史" size="min(900px, 95vw)" append-to-body>
      <div v-loading="history.loading">
        <p class="hint">历史文件和授权快照为上传时的内容，后续修改不影响旧记录。</p>
        <HistoryActions v-if="history.row" entity="machine_license" :entity-id="history.row.id" label="查看字段修改记录" />
        <el-table :data="history.files" border size="small" highlight-current-row @current-change="row => history.selected = row" style="margin-top:16px" empty-text="尚未上传文件">
          <el-table-column label="版本" width="65"><template #default="{ row }">V{{ row.file_version }}</template></el-table-column>
          <el-table-column prop="file_name" label="文件名" min-width="170" />
          <el-table-column prop="uploaded_by" label="上传人" width="90" />
          <el-table-column label="上传时间" width="160"><template #default="{ row }">{{ date(row.uploaded_at) }}</template></el-table-column>
          <el-table-column prop="note" label="变更说明" min-width="120" />
          <el-table-column label="操作" width="75"><template #default="{ row }"><el-button link type="primary" @click="download(history.row, row)">下载</el-button></template></el-table-column>
        </el-table>
        <template v-if="history.selected">
          <h4>V{{ history.selected.file_version }} 授权信息快照</h4>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="机台类型">{{ history.selected.snapshot.model || '—' }}</el-descriptions-item>
            <el-descriptions-item label="ToolID（网元名称）">{{ history.selected.snapshot.tool_id || '—' }}</el-descriptions-item>
            <el-descriptions-item label="UUID">{{ history.selected.snapshot.uuid || '—' }}</el-descriptions-item>
            <el-descriptions-item v-for="field in licenseFields.slice(1)" :key="field.key" :label="field.label">
              {{ field.multiple ? (history.selected.snapshot[field.key] || []).join('、') || '—' : history.selected.snapshot[field.key] || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="备注">{{ history.selected.snapshot.remark || '—' }}</el-descriptions-item>
          </el-descriptions>
        </template>
      </div>
    </el-drawer>
  </section>
</template>
<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { apiError, configApi, customerStatusApi, downloadBlob, licenseApi } from '../api'
import { licenseChoices, licenseFields } from '../utils/licenseFields'
import CustomerLicenseOptions from './CustomerLicenseOptions.vue'
import HistoryActions from './HistoryActions.vue'
const props = defineProps({ machine: { type: Object, required: true }, canEdit: Boolean })
const emit = defineEmits(['machine-changed'])
const rows = ref([]), config = ref({}), loading = ref(false), busy = ref(null), page = ref(1), modelSaving = ref(false)
const pageRows = computed(() => rows.value.slice((page.value - 1) * 10, page.value * 10))
const editor = reactive({ visible: false, row: null, form: {}, file: null, key: 0, saving: false })
const upload = reactive({ visible: false, row: null, file: null, key: 0, note: '', saving: false })
const history = reactive({ visible: false, row: null, files: [], selected: null, loading: false })
const choices = (field, current) => licenseChoices(config.value, field, current)
const bytes = n => n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} KB`
const date = value => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '—'
async function loadOptions() {
  try { config.value = (await configApi.get()).data }
  catch (e) { ElMessage.error(apiError(e, '加载客户面配置失败')) }
}
async function load() {
  loading.value = true
  try {
    rows.value = (await licenseApi.list(props.machine.id)).data
    page.value = Math.min(page.value, Math.max(1, Math.ceil(rows.value.length / 10)))
  } catch (e) { ElMessage.error(apiError(e, '加载 License 失败')) }
  finally { loading.value = false }
}
watch(() => props.machine.id, () => { page.value = 1; load(); loadOptions() }, { immediate: true })
async function saveCell(row, key, value) {
  busy.value = row.id
  try { Object.assign(row, (await licenseApi.update(row.id, { version: row.version, [key]: value })).data) }
  catch (e) {
    if (e.response?.status !== 409) ElMessage.error(apiError(e, '保存 License 失败'))
    await load()
  } finally { busy.value = null }
}
async function changeModel(value) {
  if (value === props.machine.model) return
  modelSaving.value = true
  try {
    const { data } = await customerStatusApi.update(props.machine.id, { version: props.machine.version, model: value })
    emit('machine-changed', data)
    await load()
    ElMessage.success('机台总览与所有 License 的型号已同步')
  } catch (e) {
    if (e.response?.status !== 409) ElMessage.error(apiError(e, '更新型号失败'))
    // 409 后回源，避免父机台版本一直过期。
    try {
      const all = (await customerStatusApi.list()).data
      const current = all.find(m => m.id === props.machine.id)
      if (current) emit('machine-changed', current)
    } catch { /* 保留当前页面，允许手工刷新 */ }
  } finally { modelSaving.value = false }
}
function openEditor(row = null) {
  Object.assign(editor, { visible: true, row, file: null, key: editor.key + 1,
    form: { tool_id: row?.tool_id || '', uuid: row?.uuid || '', throughput_package: row?.throughput_package || '',
      algorithm: row?.algorithm || '', optional_features: [...(row?.optional_features || [])], remark: row?.remark || '' } })
  loadOptions()
}
async function saveEditor() {
  editor.saving = true
  const form = { ...editor.form, throughput_package: editor.form.throughput_package || '', algorithm: editor.form.algorithm || '' }
  try {
    if (editor.row) await licenseApi.update(editor.row.id, { ...form, version: editor.row.version })
    else await licenseApi.create({ machine_status_id: props.machine.id, metadata: form, file: editor.file })
    editor.visible = false
    await load()
    ElMessage.success('License 已保存')
  } catch (e) {
    if (e.response?.status !== 409) ElMessage.error(apiError(e, '保存 License 失败'))
    else { editor.visible = false; await load() }
  } finally { editor.saving = false }
}
function openUpload(row) { Object.assign(upload, { visible: true, row, file: null, key: upload.key + 1, note: '' }) }
async function saveUpload() {
  if (!upload.file) return ElMessage.warning('请选择 License 文件')
  upload.saving = true
  try {
    await licenseApi.uploadVersion(upload.row.id, { version: upload.row.version, file: upload.file, note: upload.note })
    upload.visible = false
    await load()
    ElMessage.success('新版本已上传，历史文件已保留')
  } catch (e) {
    if (e.response?.status !== 409) ElMessage.error(apiError(e, '上传失败'))
    else { upload.visible = false; await load() }
  } finally { upload.saving = false }
}
async function openHistory(row) {
  Object.assign(history, { visible: true, row, files: [], selected: null, loading: true })
  try {
    history.files = (await licenseApi.files(row.id)).data
    history.selected = history.files[0] || null
  } catch (e) { ElMessage.error(apiError(e, '加载历史失败')) }
  finally { history.loading = false }
}
async function download(row, file = null) {
  try {
    const resp = file ? await licenseApi.downloadVersion(row.id, file.id) : await licenseApi.download(row.id)
    downloadBlob(resp.data, file?.file_name || row.file_name)
  } catch (e) { ElMessage.error(apiError(e, '下载失败')) }
}
async function remove(row) {
  try { await ElMessageBox.confirm('删除此授权及全部历史文件？文件更新请使用“更新文件”以保留历史。', '删除 License', { type: 'warning' }) }
  catch { return }
  try { await licenseApi.remove(row.id); await load(); ElMessage.success('已删除') }
  catch (e) { ElMessage.error(apiError(e, '删除失败')) }
}
</script>
<style scoped>
.license-block { border: 1px solid #e4e7ed; border-radius: 4px; margin-top: 16px; overflow: hidden; }
.license-head { background: #fafbfc; border-bottom: 1px solid #e4e7ed; padding: 10px 12px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.actions { margin-left: auto; display: flex; gap: 8px; flex-wrap: wrap; }
.actions :deep(.el-button + .el-button) { margin-left: 0; }
.machine-model { padding: 10px 12px; display: flex; align-items: center; gap: 8px; font-size: 12px; }
.hint { color: #909399; font-size: 12px; }
.file-name { overflow-wrap: anywhere; }
.license-block :deep(.el-input), .license-block :deep(.el-select) { width: 100%; }
.el-pagination { padding: 12px; justify-content: flex-end; }
</style>
