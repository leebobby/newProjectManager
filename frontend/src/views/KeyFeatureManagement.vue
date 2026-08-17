<template>
  <div class="kf-page">
    <el-card shadow="never">
      <div class="toolbar">
        <el-input v-model="q" placeholder="搜索特性名 / 责任人 / 简介" clearable size="small" style="width:240px" :prefix-icon="Search" />
        <div class="legend">
          <span v-for="s in FEATURE_STATUSES" :key="s" class="legend-item">
            <i class="dot" :style="{ background: featureColor(s) }" />{{ s }}
          </span>
        </div>
        <div class="toolbar-right">
          <span class="muted">共 {{ filteredRows.length }} 个特性</span>
          <el-button size="small" type="primary" :icon="Plus" @click="addRow">新增特性</el-button>
        </div>
      </div>

      <el-table :data="filteredRows" v-loading="loading" border size="small" max-height="calc(100vh - 240px)">
        <el-table-column type="index" label="序号" width="58" align="center" fixed="left" />
        <el-table-column label="特性名称" min-width="150" fixed="left">
          <template #default="{ row }">
            <EditableCell :value="row.name" placeholder="填写特性名" @save="(v) => save(row, { name: v })" />
          </template>
        </el-table-column>

        <el-table-column label="需求度量" align="center">
          <el-table-column label="总SR" width="82" align="center">
            <template #default="{ row }"><EditableCell :value="String(row.total_sr || 0)" @save="(v) => saveNum(row, 'total_sr', v)" /></template>
          </el-table-column>
          <el-table-column label="已验收" width="82" align="center">
            <template #default="{ row }"><EditableCell :value="String(row.accepted_sr || 0)" @save="(v) => saveNum(row, 'accepted_sr', v)" /></template>
          </el-table-column>
          <el-table-column label="已转测" width="82" align="center">
            <template #default="{ row }"><EditableCell :value="String(row.to_test_sr || 0)" @save="(v) => saveNum(row, 'to_test_sr', v)" /></template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="责任人" align="center">
          <el-table-column label="FO" width="100" align="center">
            <template #default="{ row }"><EditableCell :value="row.fo" placeholder="—" @save="(v) => save(row, { fo: v })" /></template>
          </el-table-column>
          <el-table-column label="特性SE" width="100" align="center">
            <template #default="{ row }"><EditableCell :value="row.se" placeholder="—" @save="(v) => save(row, { se: v })" /></template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="特性内容" align="center">
          <el-table-column label="特性简介" min-width="200">
            <template #default="{ row }"><EditableCell :value="row.intro" multiline placeholder="点击填写简介" @save="(v) => save(row, { intro: v })" /></template>
          </el-table-column>
          <el-table-column label="附件 / 链接" width="200">
            <template #default="{ row }">
              <div class="att-cell">
                <span v-for="a in row.attachments" :key="a.id" class="att-chip" @click="openAtt(row, a)">
                  <el-icon><Link v-if="a.kind === 'link'" /><Document v-else /></el-icon>
                  <span class="att-name">{{ a.name }}</span>
                  <el-icon class="att-x" @click.stop="removeAtt(row, a)"><Close /></el-icon>
                </span>
                <el-button link type="primary" size="small" :icon="Plus" @click="openAttDialog(row)">添加</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="交付 & 关键问题" align="center">
          <el-table-column label="特性点灯" width="150" align="center">
            <template #default="{ row }">
              <span class="stat-dot" :style="{ background: featureColor(row.status) }" />
              <el-select :model-value="row.status" size="small" style="width:104px" @change="(v) => save(row, { status: v })">
                <el-option v-for="s in FEATURE_STATUSES" :key="s" :value="s" :label="s">
                  <span class="stat-dot" :style="{ background: featureColor(s) }" />{{ s }}
                </el-option>
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="客户面关键问题" min-width="180">
            <template #default="{ row }">
              <div class="issue-cell">
                <EditableCell :value="row.issue_feature" placeholder="关联问题单特性名" @save="(v) => save(row, { issue_feature: v })" />
                <el-button v-if="row.issue_feature" link type="primary" size="small" :icon="TopRight"
                           title="到问题单管理查看该特性的问题" @click="gotoIssues(row.issue_feature)" />
              </div>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="引用机台" width="90" align="center">
          <template #default="{ row }">
            <el-tooltip v-if="row.machine_ids && row.machine_ids.length" :content="`被 ${row.machine_ids.length} 台机台引用`" placement="top">
              <span class="ref-badge">{{ row.machine_ids.length }}</span>
            </el-tooltip>
            <span v-else class="muted">0</span>
          </template>
        </el-table-column>

        <el-table-column v-if="isAdmin" label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" :icon="Delete" @click="onDelete(row)" />
          </template>
        </el-table-column>

        <template #empty><div class="empty-hint">暂无关键特性，点「新增特性」开始。</div></template>
      </el-table>
    </el-card>

    <!-- 附件/链接管理 -->
    <el-dialog v-model="attVisible" title="附件 / 链接" width="480px">
      <div v-if="attRow">
        <div class="att-list">
          <div v-for="a in attRow.attachments" :key="a.id" class="att-row">
            <el-icon><Link v-if="a.kind === 'link'" /><Document v-else /></el-icon>
            <span class="att-name" @click="openAtt(attRow, a)">{{ a.name }}</span>
            <el-button link type="danger" size="small" :icon="Delete" @click="removeAtt(attRow, a)" />
          </div>
          <div v-if="!attRow.attachments.length" class="muted">暂无附件</div>
        </div>
        <el-divider>上传文件</el-divider>
        <el-upload :auto-upload="false" :show-file-list="false" :on-change="(f) => onUpload(attRow, f)">
          <el-button size="small" :icon="Upload" :loading="uploading">选择文件上传</el-button>
        </el-upload>
        <el-divider>添加链接</el-divider>
        <div class="link-form">
          <el-input v-model="linkName" size="small" placeholder="名称（可选）" style="width:140px" />
          <el-input v-model="linkUrl" size="small" placeholder="https://..." style="flex:1" />
          <el-button size="small" type="primary" :loading="addingLink" @click="onAddLink(attRow)">添加</el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElInput, ElMessage, ElMessageBox } from 'element-plus'
import { Close, Delete, Document, Link, Plus, Search, TopRight, Upload } from '@element-plus/icons-vue'
import { downloadBlob, keyFeatureApi } from '../api'
import { auth } from '../store/auth'
import { FEATURE_STATUSES, featureColor } from '../utils/featureStatus'

const router = useRouter()
const isAdmin = auth.isAdmin

const rows = ref([])
const loading = ref(false)
const q = ref('')

const EditableCell = defineComponent({
  props: { value: String, placeholder: { type: String, default: '点击填写' }, multiline: { type: Boolean, default: false } },
  emits: ['save'],
  setup(props, { emit }) {
    const editing = ref(false)
    const draft = ref('')
    const start = () => { draft.value = props.value || ''; editing.value = true }
    const commit = () => { editing.value = false; if (draft.value !== (props.value || '')) emit('save', draft.value) }
    return () => editing.value
      ? h(ElInput, {
          modelValue: draft.value, size: 'small', autofocus: true,
          type: props.multiline ? 'textarea' : 'text',
          autosize: props.multiline ? { minRows: 1, maxRows: 6 } : false,
          'onUpdate:modelValue': (v) => { draft.value = v },
          onBlur: commit,
          onKeyup: (e) => { if (e.key === 'Enter' && !props.multiline) commit(); if (e.key === 'Escape') editing.value = false },
        })
      : h('span', { class: [props.value ? 'cell-text' : 'cell-text muted', props.multiline ? 'cell-multiline' : ''], onClick: start },
          props.value || props.placeholder)
  },
})

const filteredRows = computed(() => {
  if (!q.value.trim()) return rows.value
  const kw = q.value.trim().toLowerCase()
  return rows.value.filter(r =>
    (r.name || '').toLowerCase().includes(kw)
    || (r.fo || '').toLowerCase().includes(kw)
    || (r.se || '').toLowerCase().includes(kw)
    || (r.intro || '').toLowerCase().includes(kw))
})

async function reload() {
  loading.value = true
  try { rows.value = (await keyFeatureApi.list()).data }
  catch (e) { ElMessage.error(e.response?.data?.detail || '加载失败') }
  finally { loading.value = false }
}

async function save(row, patch) {
  try {
    const { data } = await keyFeatureApi.update(row.id, { version: row.version, ...patch })
    replaceRow(data)
  } catch (e) {
    if (e.response?.status === 409) ElMessage.warning('该特性已被他人修改，已刷新')
    else ElMessage.error(e.response?.data?.detail || '保存失败')
    reload()
  }
}
function saveNum(row, key, v) {
  const n = Math.max(0, parseInt(v, 10) || 0)
  save(row, { [key]: n })
}
function replaceRow(data) {
  const i = rows.value.findIndex(r => r.id === data.id)
  if (i >= 0) rows.value[i] = data
}

async function addRow() {
  try {
    const { data } = await keyFeatureApi.create({ name: '', status: '分析' })
    rows.value.push(data)
  } catch (e) { ElMessage.error(e.response?.data?.detail || '新增失败') }
}

async function onDelete(row) {
  try { await ElMessageBox.confirm(`确认删除特性「${row.name || '该条'}」吗？`, '提示', { type: 'warning' }) }
  catch { return }
  try {
    await keyFeatureApi.remove(row.id)
    rows.value = rows.value.filter(r => r.id !== row.id)
    ElMessage.success('已删除')
  } catch (e) { ElMessage.error(e.response?.data?.detail || '删除失败') }
}

function gotoIssues(feature) {
  router.push({ path: '/issues', query: { feature } })
}

// ── 附件 ──
const attVisible = ref(false)
const attRow = ref(null)
const uploading = ref(false)
const addingLink = ref(false)
const linkName = ref('')
const linkUrl = ref('')

function openAttDialog(row) {
  attRow.value = row
  linkName.value = ''
  linkUrl.value = ''
  attVisible.value = true
}

async function openAtt(row, a) {
  if (a.kind === 'link') { window.open(a.url, '_blank'); return }
  try {
    const resp = await keyFeatureApi.downloadAttachment(row.id, a.stored)
    downloadBlob(resp.data, a.name)
  } catch { ElMessage.error('下载失败') }
}

async function onUpload(row, uploadFile) {
  const file = uploadFile?.raw
  if (!file) return
  uploading.value = true
  try {
    const { data } = await keyFeatureApi.uploadAttachment(row.id, file)
    row.attachments = data.attachments
    replaceRow(row)
    ElMessage.success('已上传')
  } catch (e) { ElMessage.error(e.response?.data?.detail || '上传失败') }
  finally { uploading.value = false }
}

async function onAddLink(row) {
  if (!linkUrl.value.trim()) { ElMessage.warning('请填写链接'); return }
  addingLink.value = true
  try {
    const { data } = await keyFeatureApi.addLink(row.id, linkName.value.trim(), linkUrl.value.trim())
    row.attachments = data.attachments
    replaceRow(row)
    linkName.value = ''
    linkUrl.value = ''
  } catch (e) { ElMessage.error(e.response?.data?.detail || '添加失败') }
  finally { addingLink.value = false }
}

async function removeAtt(row, a) {
  try {
    const { data } = await keyFeatureApi.removeAttachment(row.id, a.id)
    row.attachments = data.attachments
    replaceRow(row)
  } catch (e) { ElMessage.error(e.response?.data?.detail || '删除失败') }
}

onMounted(reload)
</script>

<style scoped>
.kf-page { display: flex; flex-direction: column; gap: 14px; }
.toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.toolbar-right { display: flex; align-items: center; gap: 8px; margin-left: auto; }
.muted { color: #909399; font-size: 13px; }
.empty-hint { color: #909399; padding: 24px 0; }

.legend { display: flex; align-items: center; gap: 12px; font-size: 12px; color: #606266; }
.legend-item { display: inline-flex; align-items: center; }
.legend .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; }

.stat-dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
:deep(.cell-text) { cursor: pointer; display: inline-block; min-height: 20px; min-width: 30px; }
:deep(.cell-text:hover) { color: #409eff; }
:deep(.cell-multiline) { white-space: pre-wrap; line-height: 1.5; }

.att-cell { display: flex; flex-direction: column; gap: 3px; align-items: flex-start; }
.att-chip {
  display: inline-flex; align-items: center; gap: 3px; max-width: 100%;
  background: #f0f2f5; border-radius: 4px; padding: 1px 6px; font-size: 12px; cursor: pointer;
}
.att-chip:hover { background: #e6f0ff; }
.att-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 110px; }
.att-x { color: #c0c4cc; }
.att-x:hover { color: #f56c6c; }

.issue-cell { display: flex; align-items: center; gap: 4px; }
.ref-badge {
  display: inline-block; min-width: 20px; padding: 0 6px; border-radius: 10px;
  background: #ecf5ff; color: #409eff; font-size: 12px; line-height: 18px;
}

.att-list { display: flex; flex-direction: column; gap: 6px; }
.att-row { display: flex; align-items: center; gap: 8px; }
.att-row .att-name { cursor: pointer; color: #409eff; max-width: 320px; }
.link-form { display: flex; align-items: center; gap: 8px; }
</style>
