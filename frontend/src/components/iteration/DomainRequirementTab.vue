<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" :icon="Plus" @click="openCreate">新增需求</el-button>
      <el-button :icon="Upload" type="warning" @click="openImport">批量导入</el-button>
      <el-button :icon="Refresh" @click="load">刷新</el-button>
      <el-select
        v-model="filterGroupId"
        placeholder="按 PL 组筛选"
        clearable
        filterable
        size="small"
        style="width: 200px"
      >
        <el-option
          v-for="g in plGroups"
          :key="g.id"
          :value="g.id"
          :label="`${g.parent_name || '—'} / ${g.name}`"
        />
      </el-select>
      <el-select
        v-model="filterOwnerId"
        placeholder="按责任人筛选"
        clearable
        filterable
        size="small"
        style="width: 180px"
      >
        <el-option
          v-for="u in userOptions"
          :key="u.id"
          :value="u.id"
          :label="`${u.full_name || u.username}${u.emp_no ? ' (' + u.emp_no + ')' : ''}`"
        />
      </el-select>
      <span class="tip">共 {{ filteredList.length }}/{{ list.length }} 条；基础列双击编辑，进展/责任人/PL组直接下拉</span>
    </div>

    <el-table :data="filteredList" v-loading="loading" border stripe style="width: 100%">
      <el-table-column prop="seq" label="序号" width="70" align="center" />
      <el-table-column label="需求编号" width="160">
        <template #default="{ row }">
          <el-input
            v-if="isEditing(row, 'req_no')"
            v-model="row.req_no"
            size="small"
            autofocus
            @blur="commit(row, 'req_no')"
            @keyup.enter="commit(row, 'req_no')"
            @keyup.esc="cancel(row, 'req_no')"
          />
          <div v-else class="editable-cell" @dblclick="startEdit(row, 'req_no')">
            <el-link v-if="row.req_url" :href="row.req_url" type="primary" target="_blank">
              {{ row.req_no || '（点此查看）' }}
            </el-link>
            <span v-else>{{ row.req_no || '—' }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="需求标题" min-width="240">
        <template #default="{ row }">
          <el-input
            v-if="isEditing(row, 'title')"
            v-model="row.title"
            size="small"
            autofocus
            @blur="commit(row, 'title')"
            @keyup.enter="commit(row, 'title')"
            @keyup.esc="cancel(row, 'title')"
          />
          <div v-else class="editable-cell" @dblclick="startEdit(row, 'title')">
            {{ row.title || '—' }}
          </div>
        </template>
      </el-table-column>
      <el-table-column label="责任人" width="150">
        <template #default="{ row }">
          <EditSelectCell
            :value="row.owner_user_id || row.owner || null"
            :display-text="row.owner || ''"
            clearable
            filterable
            allow-create
            placeholder="选择或输入"
            @change="(v) => onOwnerChange(row, v)"
          >
            <el-option
              v-for="u in userOptions"
              :key="u.id"
              :value="u.id"
              :label="u.full_name || u.username"
            >
              <span>{{ u.full_name || u.username }}</span>
              <span v-if="u.emp_no" style="color:#909399; margin-left:6px; font-size:12px">{{ u.emp_no }}</span>
            </el-option>
          </EditSelectCell>
        </template>
      </el-table-column>
      <el-table-column label="PL组" width="170">
        <template #default="{ row }">
          <EditSelectCell
            :value="row.group_id || row.owner_group || null"
            :display-text="row.owner_group || ''"
            clearable
            filterable
            allow-create
            placeholder="选择或输入"
            @change="(v) => onGroupChange(row, v)"
          >
            <el-option
              v-for="g in plGroups"
              :key="g.id"
              :value="g.id"
              :label="g.name"
            >
              <span>{{ g.name }}</span>
              <span v-if="g.parent_name" style="color:#909399; margin-left:6px; font-size:12px">{{ g.parent_name }}</span>
            </el-option>
          </EditSelectCell>
        </template>
      </el-table-column>
      <el-table-column label="优先级" width="100" align="center">
        <template #default="{ row }">
          <EditSelectCell
            :value="row.priority"
            :display-text="row.priority || ''"
            placeholder="—"
            @change="(v) => onFieldChange(row, 'priority', v)"
          >
            <el-option v-for="p in PRIORITIES" :key="p" :label="p" :value="p" />
          </EditSelectCell>
        </template>
      </el-table-column>
      <el-table-column label="计划交付版本" width="170">
        <template #default="{ row }">
          <EditSelectCell
            :value="row.planned_version"
            :display-text="row.planned_version || ''"
            clearable
            filterable
            allow-create
            placeholder="选择或输入版本"
            @change="(v) => onFieldChange(row, 'planned_version', v)"
          >
            <el-option-group
              v-for="group in versionGroups"
              :key="group.label"
              :label="group.label"
            >
              <el-option
                v-for="ver in group.options"
                :key="ver.id"
                :label="ver.version_no"
                :value="ver.version_no"
              >
                <span>{{ ver.version_no }}</span>
                <span v-if="ver.title" style="color:#909399; margin-left:6px; font-size:12px">{{ ver.title }}</span>
              </el-option>
            </el-option-group>
          </EditSelectCell>
        </template>
      </el-table-column>

      <el-table-column label="交付进展跟踪" align="center">
        <el-table-column
          v-for="col in PROGRESS_COLS"
          :key="col.field"
          :label="col.label"
          width="110"
          align="center"
        >
          <template #default="{ row }">
            <EditSelectCell
              :value="row[col.field]"
              :display-text="row[col.field] || ''"
              :tone="progressTone(row[col.field])"
              placeholder="—"
              @change="(v) => onFieldChange(row, col.field, v)"
            >
              <el-option
                v-for="s in PROGRESS_STATUSES"
                :key="s"
                :label="s"
                :value="s"
              />
            </EditSelectCell>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="版本质量统计" align="center">
        <el-table-column label="合入链接" width="150">
          <template #default="{ row }">
            <div class="merge-links">
              <template v-if="splitLinks(row.merge_links).length">
                <el-link
                  v-for="(lk, i) in splitLinks(row.merge_links)"
                  :key="i"
                  :href="lk"
                  type="primary"
                  target="_blank"
                  class="merge-link"
                >链接{{ i + 1 }}</el-link>
              </template>
              <span v-else class="num-empty">—</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="代码量" width="96" align="center">
          <template #default="{ row }">
            <el-input
              :model-value="row.code_volume"
              size="small"
              type="number"
              placeholder="—"
              @change="(v) => onNumChange(row, 'code_volume', v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="自验证用例数" width="110" align="center">
          <template #default="{ row }">
            <el-input
              :model-value="row.self_test_case_count"
              size="small"
              type="number"
              placeholder="—"
              @change="(v) => onNumChange(row, 'self_test_case_count', v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="转测问题单" width="96" align="center">
          <template #default="{ row }">
            <el-input
              :model-value="row.post_test_issue_count"
              size="small"
              type="number"
              placeholder="—"
              @change="(v) => onNumChange(row, 'post_test_issue_count', v)"
            />
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="备注" min-width="180">
        <template #default="{ row }">
          <el-input
            v-if="isEditing(row, 'remark')"
            v-model="row.remark"
            size="small"
            autofocus
            type="textarea"
            :rows="2"
            @blur="commit(row, 'remark')"
            @keyup.enter.ctrl="commit(row, 'remark')"
            @keyup.esc="cancel(row, 'remark')"
          />
          <div v-else class="editable-cell" @dblclick="startEdit(row, 'remark')">
            <el-tag v-if="row.remark" type="warning" size="small" effect="plain" class="remark-tag">变更</el-tag>
            <span :class="row.remark ? 'remark-text' : 'remark-empty'">{{ row.remark || '—' }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">完整编辑</el-button>
          <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑需求' : '新增需求'" width="640px">
      <el-form :model="form" label-width="120px">
        <el-form-item label="序号">
          <el-input-number v-model="form.seq" :min="0" />
        </el-form-item>
        <el-form-item label="需求编号">
          <el-input v-model="form.req_no" />
        </el-form-item>
        <el-form-item label="需求超链接">
          <el-input v-model="form.req_url" placeholder="https://..." />
        </el-form-item>
        <el-form-item label="需求标题">
          <el-input v-model="form.title" />
        </el-form-item>
        <el-form-item label="责任人">
          <el-select
            v-model="formOwnerPick"
            clearable
            filterable
            allow-create
            placeholder="选择 User 或手填姓名"
            style="width: 100%"
            @change="onFormOwnerChange"
          >
            <el-option
              v-for="u in userOptions"
              :key="u.id"
              :value="u.id"
              :label="u.full_name || u.username"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="PL组">
          <el-select
            v-model="formGroupPick"
            clearable
            filterable
            allow-create
            placeholder="选择 PL 组或手填"
            style="width: 100%"
            @change="onFormGroupChange"
          >
            <el-option
              v-for="g in plGroups"
              :key="g.id"
              :value="g.id"
              :label="g.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="form.priority" style="width: 100%">
            <el-option v-for="p in PRIORITIES" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="计划交付版本">
          <el-select
            v-model="form.planned_version"
            clearable
            filterable
            allow-create
            placeholder="选择或输入版本"
            style="width: 100%"
          >
            <el-option-group
              v-for="group in versionGroups"
              :key="group.label"
              :label="group.label"
            >
              <el-option
                v-for="ver in group.options"
                :key="ver.id"
                :label="ver.version_no"
                :value="ver.version_no"
              >
                <span>{{ ver.version_no }}</span>
                <span v-if="ver.title" style="color:#909399; margin-left:6px; font-size:12px">{{ ver.title }}</span>
              </el-option>
            </el-option-group>
          </el-select>
        </el-form-item>
        <el-form-item v-for="col in PROGRESS_COLS" :key="col.field" :label="col.label">
          <el-select v-model="form[col.field]" style="width: 100%">
            <el-option v-for="s in PROGRESS_STATUSES" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-divider content-position="left">版本质量统计</el-divider>
        <el-form-item label="合入链接">
          <el-input
            v-model="form.merge_links"
            type="textarea"
            :rows="3"
            placeholder="支持多个，每行一个链接"
          />
        </el-form-item>
        <el-form-item label="代码量(行)">
          <el-input-number v-model="form.code_volume" :min="0" :controls="false" style="width: 160px" />
        </el-form-item>
        <el-form-item label="自验证用例数">
          <el-input-number v-model="form.self_test_case_count" :min="0" :controls="false" style="width: 160px" />
        </el-form-item>
        <el-form-item label="转测后问题单数量">
          <el-input-number v-model="form.post_test_issue_count" :min="0" :controls="false" style="width: 160px" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="如有变更，请说明……" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="importVisible" title="批量导入需求" width="520px">
      <p class="import-tip">
        1. 先下载模板，按格式填写需求清单；<br />
        2. 表头列名请勿改动；进展列填写「未开始/进行中/已完成/已延期/已变更/不涉及」；<br />
        3. 上传 .xlsx 文件，系统将批量创建到当前迭代下。
      </p>
      <el-button :icon="Download" link type="primary" @click="onDownloadTemplate">
        下载导入模板 (.xlsx)
      </el-button>

      <el-divider />

      <el-upload
        ref="uploadRef"
        :auto-upload="false"
        :limit="1"
        :on-exceed="onExceed"
        :on-change="onFileChange"
        :show-file-list="true"
        accept=".xlsx"
        drag
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽 .xlsx 文件到此，或<em>点击选择</em></div>
      </el-upload>

      <div v-if="importResult" class="import-result">
        <el-alert
          :title="`成功导入 ${importResult.created} 条`"
          :type="importResult.errors?.length ? 'warning' : 'success'"
          :description="importResult.errors?.length ? importResult.errors.join('\n') : '无错误'"
          show-icon
          :closable="false"
        />
      </div>

      <template #footer>
        <el-button @click="importVisible = false">关闭</el-button>
        <el-button type="primary" :loading="importing" :disabled="!importFile" @click="onSubmitImport">
          开始导入
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Plus, Refresh, Upload, UploadFilled } from '@element-plus/icons-vue'
import { downloadBlob, iterationRequirementApi, resourceGroupApi, userApi } from '../../api'
import EditSelectCell from '../EditSelectCell.vue'

const props = defineProps({
  iterationId: { type: Number, required: true },
  versionGroups: { type: Array, default: () => [] },
})

const PROGRESS_COLS = [
  { field: 'progress_walkthrough', label: '需求串讲' },
  { field: 'progress_reverse', label: '反串讲' },
  { field: 'progress_stc', label: 'STC设计' },
  { field: 'progress_coding', label: '编码' },
  { field: 'progress_bbit', label: 'BBIT' },
  { field: 'progress_clarify', label: '转测澄清' },
]
const PROGRESS_STATUSES = ['未开始', '进行中', '已完成', '已延期', '已变更', '不涉及']
const PRIORITIES = ['P0', 'P1', 'P2', 'P3']

// 进展着色：已完成→绿、已延期→红，其余默认（仅着色单元格本身）
function progressTone(v) {
  if (v === '已完成') return 'success'
  if (v === '已延期') return 'danger'
  return ''
}

const list = ref([])
const userOptions = ref([])
const plGroups = ref([])
const filterOwnerId = ref(null)
const filterGroupId = ref(null)
const loading = ref(false)
const dialogVisible = ref(false)
const editing = ref(null)
const form = reactive(defaultForm())
const formOwnerPick = ref(null)   // 完整编辑里的责任人 select 值
const formGroupPick = ref(null)
const editingCell = ref(null)

const filteredList = computed(() => {
  return list.value.filter((r) => {
    if (filterOwnerId.value && r.owner_user_id !== filterOwnerId.value) return false
    if (filterGroupId.value && r.group_id !== filterGroupId.value) return false
    return true
  })
})

function findUserByName(name) {
  if (!name) return null
  return userOptions.value.find(
    (u) => u.full_name === name || u.username === name || u.emp_no === name
  ) || null
}
function findGroupByName(name) {
  if (!name) return null
  return plGroups.value.find((g) => g.name === name || g.code === name) || null
}

const importVisible = ref(false)
const importing = ref(false)
const importFile = ref(null)
const importResult = ref(null)
const uploadRef = ref(null)

function defaultForm() {
  return {
    seq: 0,
    req_no: '',
    req_url: '',
    title: '',
    owner: '',
    owner_user_id: null,
    owner_group: '',
    group_id: null,
    priority: 'P2',
    planned_version: '',
    target_version_id: null,
    progress_walkthrough: '未开始',
    progress_reverse: '未开始',
    progress_stc: '未开始',
    progress_coding: '未开始',
    progress_bbit: '未开始',
    progress_clarify: '未开始',
    merge_links: '',
    code_volume: null,
    self_test_case_count: null,
    post_test_issue_count: null,
    remark: '',
  }
}

function splitLinks(text) {
  if (!text) return []
  return String(text)
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean)
}

async function load() {
  loading.value = true
  try {
    const { data } = await iterationRequirementApi.list(props.iterationId)
    list.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

async function loadOptions() {
  try {
    const [{ data: us }, { data: gs }] = await Promise.all([
      userApi.options({ include_inactive: false }),
      resourceGroupApi.list({ kind: 'pl' }),
    ])
    userOptions.value = us
    plGroups.value = gs
  } catch { /* 下拉为空不阻塞 */ }
}

function openCreate() {
  editing.value = null
  Object.assign(form, defaultForm())
  form.seq = (list.value.length || 0) + 1
  formOwnerPick.value = null
  formGroupPick.value = null
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, row)
  formOwnerPick.value = row.owner_user_id || row.owner || null
  formGroupPick.value = row.group_id || row.owner_group || null
  dialogVisible.value = true
}

function onFormOwnerChange(v) {
  if (typeof v === 'number') {
    const u = userOptions.value.find((x) => x.id === v)
    form.owner_user_id = v
    form.owner = u ? (u.full_name || u.username) : ''
    // 自动带出该用户所属 PL 组（同步 select 显示值 formGroupPick）
    if (u && u.group_id) {
      form.group_id = u.group_id
      form.owner_group = u.group_name || ''
      formGroupPick.value = u.group_id
    }
  } else {
    // 手填字符串：清掉 FK，保留字符串
    form.owner_user_id = null
    form.owner = v || ''
  }
}
function onFormGroupChange(v) {
  if (typeof v === 'number') {
    const g = plGroups.value.find((x) => x.id === v)
    form.group_id = v
    form.owner_group = g ? g.name : ''
  } else {
    form.group_id = null
    form.owner_group = v || ''
  }
}

async function onSubmit() {
  try {
    if (editing.value) {
      await iterationRequirementApi.update(editing.value.id, form)
      ElMessage.success('已更新')
      dialogVisible.value = false
      load()
    } else {
      await iterationRequirementApi.create({ ...form, iteration_id: props.iterationId })
      ElMessage.success('已创建')
      dialogVisible.value = false
      load()
    }
  } catch (e) {
    if (e.response?.status !== 409) ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function onDelete(row) {
  await ElMessageBox.confirm(`确认删除需求「${row.req_no || row.title}」吗？`, '提示', { type: 'warning' })
  await iterationRequirementApi.remove(row.id)
  ElMessage.success('已删除')
  load()
}

function isEditing(row, field) {
  return editingCell.value && editingCell.value.id === row.id && editingCell.value.field === field
}

function startEdit(row, field) {
  editingCell.value = { id: row.id, field, original: row[field] }
}

function cancel(row, field) {
  if (!editingCell.value) return
  row[field] = editingCell.value.original
  editingCell.value = null
}

async function commit(row, field) {
  if (!editingCell.value) return
  const original = editingCell.value.original
  const newVal = row[field]
  editingCell.value = null
  if (newVal === original) return
  try {
    const { data } = await iterationRequirementApi.update(row.id, { [field]: newVal, version: row.version })
    row.version = data.version
    ElMessage.success('已保存')
  } catch (e) {
    row[field] = original
    if (e.response?.status !== 409) ElMessage.error(e.response?.data?.detail || '保存失败')
    else load()
  }
}

async function onFieldChange(row, field, value) {
  const original = row[field]
  if (value === original) return
  try {
    const { data } = await iterationRequirementApi.update(row.id, { [field]: value, version: row.version })
    row[field] = value
    row.version = data.version
  } catch (e) {
    row[field] = original
    if (e.response?.status !== 409) ElMessage.error(e.response?.data?.detail || '保存失败')
    else load()
  }
}

async function onNumChange(row, field, v) {
  const newVal = v === '' || v === null || v === undefined ? null : Number(v)
  if (newVal !== null && Number.isNaN(newVal)) {
    ElMessage.warning('请输入数字')
    return
  }
  await onFieldChange(row, field, newVal)
}

async function onOwnerChange(row, value) {
  // value 可能是 user.id (number) 或 手输的姓名 (string)
  const payload = { version: row.version }
  if (typeof value === 'number') {
    const u = userOptions.value.find((x) => x.id === value)
    payload.owner_user_id = value
    payload.owner = u ? (u.full_name || u.username) : ''
    // 选中真实用户时自动带出其所属 PL 组（仅当该用户已挂组）
    if (u && u.group_id) {
      payload.group_id = u.group_id
      payload.owner_group = u.group_name || ''
    }
  } else if (value) {
    payload.owner_user_id = null
    payload.owner = value
  } else {
    payload.owner_user_id = null
    payload.owner = ''
  }
  const snapshot = {
    owner: row.owner, owner_user_id: row.owner_user_id,
    owner_group: row.owner_group, group_id: row.group_id,
  }
  Object.assign(row, payload)
  try {
    const { data } = await iterationRequirementApi.update(row.id, payload)
    row.version = data.version
  } catch (e) {
    Object.assign(row, snapshot)
    if (e.response?.status !== 409) ElMessage.error(e.response?.data?.detail || '保存失败')
    else load()
  }
}

async function onGroupChange(row, value) {
  const payload = { version: row.version }
  if (typeof value === 'number') {
    const g = plGroups.value.find((x) => x.id === value)
    payload.group_id = value
    payload.owner_group = g ? g.name : ''
  } else if (value) {
    payload.group_id = null
    payload.owner_group = value
  } else {
    payload.group_id = null
    payload.owner_group = ''
  }
  const snapshot = { owner_group: row.owner_group, group_id: row.group_id }
  Object.assign(row, payload)
  try {
    const { data } = await iterationRequirementApi.update(row.id, payload)
    row.version = data.version
  } catch (e) {
    Object.assign(row, snapshot)
    if (e.response?.status !== 409) ElMessage.error(e.response?.data?.detail || '保存失败')
    else load()
  }
}

function openImport() {
  importFile.value = null
  importResult.value = null
  importVisible.value = true
  if (uploadRef.value) uploadRef.value.clearFiles?.()
}

function onExceed() {
  ElMessage.warning('一次仅可上传一个文件，请先移除已选文件')
}

function onFileChange(file) {
  importFile.value = file.raw
  importResult.value = null
}

async function onDownloadTemplate() {
  try {
    const resp = await iterationRequirementApi.importTemplate()
    downloadBlob(resp.data, 'iteration-requirements-template.xlsx')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '下载失败')
  }
}

async function onSubmitImport() {
  if (!importFile.value) {
    ElMessage.warning('请先选择 .xlsx 文件')
    return
  }
  importing.value = true
  try {
    const { data } = await iterationRequirementApi.importExcel(props.iterationId, importFile.value)
    importResult.value = data
    if (data.created > 0) {
      ElMessage.success(`成功导入 ${data.created} 条`)
      load()
    } else {
      ElMessage.warning('未导入任何数据')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  } finally {
    importing.value = false
  }
}

defineExpose({ load })

onMounted(() => {
  load()
  loadOptions()
})
</script>

<style scoped>
.toolbar {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.tip {
  margin-left: auto;
  color: #909399;
  font-size: 12px;
}
.editable-cell {
  cursor: text;
  min-height: 22px;
  white-space: pre-wrap;
}
.remark-tag {
  margin-right: 6px;
}
.remark-text { color: #e6a23c; }
.remark-empty { color: #c0c4cc; }
.merge-links {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.4;
}
.merge-link { font-size: 12px; }
.num-empty { color: #c0c4cc; }
.import-tip {
  color: #606266;
  line-height: 1.7;
  font-size: 13px;
  margin: 0 0 8px 0;
}
.import-result {
  margin-top: 12px;
}
.import-result :deep(.el-alert__description) {
  white-space: pre-wrap;
}
</style>
