<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" :icon="Plus" @click="openCreate">新增产品需求</el-button>
      <el-button :icon="Upload" type="warning" @click="openImport">批量导入</el-button>
      <el-button :icon="Refresh" @click="load">刷新</el-button>
      <el-button v-if="isAdmin" :icon="Setting" @click="openFeatureDialog">管理所属特性</el-button>
      <el-select
        v-model="filterUserId"
        placeholder="按特性角色筛选"
        clearable
        filterable
        size="small"
        style="width: 200px"
      >
        <el-option
          v-for="u in userOptions"
          :key="u.id"
          :value="u.id"
          :label="`${u.full_name || u.username}${u.emp_no ? ' (' + u.emp_no + ')' : ''}`"
        />
      </el-select>
      <span class="tip">共 {{ filteredList.length }}/{{ list.length }} 条；特性 FO/SE/TFO 任一命中即匹配</span>
    </div>

    <el-table :data="filteredList" v-loading="loading" border stripe style="width: 100%">
      <el-table-column prop="seq" label="序号" width="70" align="center" fixed="left" />
      <el-table-column label="需求编号" width="160" fixed="left">
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
      <el-table-column label="需求标题" min-width="240" fixed="left">
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

      <el-table-column label="计划交付版本" width="170">
        <template #default="{ row }">
          <EditSelectCell
            :value="row.planned_version"
            :display-text="row.planned_version || ''"
            clearable
            filterable
            allow-create
            placeholder="选择或输入"
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

      <el-table-column label="所属特性" width="150">
        <template #default="{ row }">
          <EditSelectCell
            :value="row.feature"
            :display-text="row.feature || ''"
            clearable
            filterable
            allow-create
            placeholder="选择或输入"
            @change="(v) => onFieldChange(row, 'feature', v)"
          >
            <el-option v-for="f in features" :key="f" :label="f" :value="f" />
          </EditSelectCell>
        </template>
      </el-table-column>

      <el-table-column
        v-for="col in USER_COLS"
        :key="col.field"
        :label="col.label"
        :width="col.width"
      >
        <template #default="{ row }">
          <EditSelectCell
            :value="row[col.fkField] || row[col.field] || null"
            :display-text="row[col.field] || ''"
            clearable
            filterable
            allow-create
            placeholder="选择或输入"
            @change="(v) => onUserColChange(row, col, v)"
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

      <el-table-column
        v-for="col in BASIC_TEXT_COLS"
        :key="col.field"
        :label="col.label"
        :width="col.width"
        :min-width="col.minWidth"
      >
        <template #default="{ row }">
          <el-input
            v-if="isEditing(row, col.field)"
            v-model="row[col.field]"
            size="small"
            autofocus
            @blur="commit(row, col.field)"
            @keyup.enter="commit(row, col.field)"
            @keyup.esc="cancel(row, col.field)"
          />
          <div v-else class="editable-cell" @dblclick="startEdit(row, col.field)">
            {{ row[col.field] || '—' }}
          </div>
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
              <el-option v-for="s in PROGRESS_STATUSES" :key="s" :label="s" :value="s" />
            </EditSelectCell>
          </template>
        </el-table-column>

        <el-table-column
          v-for="col in METRIC_COLS"
          :key="col.field"
          :label="col.label"
          :width="col.width"
          :min-width="col.minWidth"
        >
          <template #default="{ row }">
            <el-input
              v-if="isEditing(row, col.field)"
              v-model="row[col.field]"
              size="small"
              autofocus
              :type="col.textarea ? 'textarea' : 'text'"
              :rows="col.textarea ? 2 : undefined"
              @blur="commit(row, col.field)"
              @keyup.enter.ctrl="commit(row, col.field)"
              @keyup.esc="cancel(row, col.field)"
            />
            <div v-else class="editable-cell" @dblclick="startEdit(row, col.field)">
              {{ row[col.field] || '—' }}
            </div>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">完整编辑</el-button>
          <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 完整编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑产品需求' : '新增产品需求'" width="720px" top="5vh">
      <el-form :model="form" label-width="110px">
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
        <el-form-item label="优先级">
          <el-select v-model="form.priority" style="width: 100%">
            <el-option v-for="p in PRIORITIES" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="所属特性">
          <el-select
            v-model="form.feature"
            clearable
            filterable
            allow-create
            placeholder="选择或输入"
            style="width: 100%"
          >
            <el-option v-for="f in features" :key="f" :label="f" :value="f" />
          </el-select>
        </el-form-item>
        <el-form-item v-for="col in USER_COLS" :key="col.field" :label="col.label">
          <el-select
            :model-value="formUserPicks[col.field]"
            clearable
            filterable
            allow-create
            placeholder="选择 User 或手填姓名"
            style="width: 100%"
            @change="(v) => onFormUserColChange(col, v)"
          >
            <el-option
              v-for="u in userOptions"
              :key="u.id"
              :value="u.id"
              :label="u.full_name || u.username"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-for="col in BASIC_TEXT_COLS" :key="col.field" :label="col.label">
          <el-input v-model="form[col.field]" :type="col.field === 'code_areas' ? 'textarea' : 'text'" :rows="col.field === 'code_areas' ? 2 : undefined" />
        </el-form-item>
        <el-form-item v-for="col in PROGRESS_COLS" :key="col.field" :label="col.label">
          <el-select v-model="form[col.field]" style="width: 100%">
            <el-option v-for="s in PROGRESS_STATUSES" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item v-for="col in METRIC_COLS" :key="col.field" :label="col.label">
          <el-input v-model="form[col.field]" :type="col.textarea ? 'textarea' : 'text'" :rows="col.textarea ? 2 : undefined" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入 -->
    <el-dialog v-model="importVisible" title="批量导入产品需求" width="520px">
      <p class="import-tip">
        1. 先下载模板，按格式填写产品需求清单；<br />
        2. 表头列名请勿改动；进展列填「未开始/进行中/已完成/已延期/已变更/不涉及」，优先级填 P0/P1/P2/P3（旧高/中/低导入时自动转换）；<br />
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

    <!-- 所属特性管理 -->
    <el-dialog v-model="featureDialog.visible" title="管理所属特性" width="460px">
      <div class="feature-tip">所属特性下拉值来自项目级配置文件，所有用户共享。一行一个，支持空行删除。</div>
      <div v-for="(f, i) in featureDialog.list" :key="i" class="feature-row">
        <el-input v-model="featureDialog.list[i]" size="small" placeholder="特性名称" />
        <el-button size="small" :icon="Delete" link type="danger" @click="featureDialog.list.splice(i, 1)" />
      </div>
      <el-button :icon="Plus" link type="primary" @click="featureDialog.list.push('')">+ 添加一行</el-button>
      <template #footer>
        <el-button @click="featureDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="featureDialog.saving" @click="onSaveFeatures">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Download, Plus, Refresh, Setting, Upload, UploadFilled } from '@element-plus/icons-vue'
import { configApi, downloadBlob, productRequirementApi, userApi } from '../../api'
import { auth } from '../../store/auth'
import EditSelectCell from '../EditSelectCell.vue'

const props = defineProps({
  iterationId: { type: Number, required: true },
  versionGroups: { type: Array, default: () => [] },
})

const isAdmin = auth.isAdmin

// 与后端 enums.PRIORITIES 保持一致（已与领域需求统一为 P0-P3）
const PRIORITIES = ['P0', 'P1', 'P2', 'P3']
const PROGRESS_STATUSES = ['未开始', '进行中', '已完成', '已延期', '已变更', '不涉及']

// 进展着色：已完成→绿、已延期→红，其余默认（仅着色单元格本身）
function progressTone(v) {
  if (v === '已完成') return 'success'
  if (v === '已延期') return 'danger'
  return ''
}

// 特性角色列（FK 化）：fkField 是后端 FK 字段名
const USER_COLS = [
  { field: 'feature_fo',  fkField: 'feature_fo_user_id',  label: '特性FO',  width: 140 },
  { field: 'feature_se',  fkField: 'feature_se_user_id',  label: '特性SE',  width: 140 },
  { field: 'feature_tfo', fkField: 'feature_tfo_user_id', label: '特性TFO', width: 140 },
]

// 其它自由文本列
const BASIC_TEXT_COLS = [
  { field: 'code_areas', label: '涉及代码领域', minWidth: 180 },
]

// 交付进展跟踪 > 状态下拉列
const PROGRESS_COLS = [
  { field: 'progress_walkthrough', label: '需求串讲' },
  { field: 'progress_reverse', label: '反串讲' },
  { field: 'progress_domain', label: '领域串讲' },
  { field: 'progress_coding', label: '编码' },
  { field: 'progress_joint_debug', label: '联调验证' },
  { field: 'progress_clarify', label: '转测澄清' },
  { field: 'progress_test_result', label: '测试结论' },
]

// 交付进展跟踪 > 度量/风险 自由文本列
const METRIC_COLS = [
  { field: 'estimated_loc', label: '预估代码量', width: 110 },
  { field: 'actual_loc', label: '实际代码量', width: 110 },
  { field: 'actual_effort', label: '实际工作量', width: 110 },
  { field: 'key_risks', label: '关键风险', minWidth: 200, textarea: true },
]

const list = ref([])
const features = ref([])
const userOptions = ref([])
const filterUserId = ref(null)
const loading = ref(false)
const dialogVisible = ref(false)
const editing = ref(null)
const form = reactive(defaultForm())
const formUserPicks = reactive({ feature_fo: null, feature_se: null, feature_tfo: null })
const editingCell = ref(null)

const featureDialog = reactive({ visible: false, saving: false, list: [] })

const filteredList = computed(() => {
  if (!filterUserId.value) return list.value
  const uid = filterUserId.value
  return list.value.filter((r) =>
    r.feature_fo_user_id === uid ||
    r.feature_se_user_id === uid ||
    r.feature_tfo_user_id === uid
  )
})

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
    planned_version: '',
    target_version_id: null,
    priority: 'P2',
    feature: '',
    feature_fo: '',
    feature_fo_user_id: null,
    feature_se: '',
    feature_se_user_id: null,
    feature_tfo: '',
    feature_tfo_user_id: null,
    code_areas: '',
    progress_walkthrough: '未开始',
    progress_reverse: '未开始',
    progress_domain: '未开始',
    progress_coding: '未开始',
    progress_joint_debug: '未开始',
    progress_clarify: '未开始',
    progress_test_result: '未开始',
    estimated_loc: '',
    actual_loc: '',
    actual_effort: '',
    key_risks: '',
  }
}

async function load() {
  loading.value = true
  try {
    const { data } = await productRequirementApi.list(props.iterationId)
    list.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

async function loadFeatures() {
  try {
    const { data } = await configApi.get()
    features.value = Array.isArray(data.product_features) ? data.product_features : []
  } catch { features.value = [] }
}

async function loadUserOptions() {
  try {
    const { data } = await userApi.options({ include_inactive: false })
    userOptions.value = data
  } catch { userOptions.value = [] }
}

function openCreate() {
  editing.value = null
  Object.assign(form, defaultForm())
  form.seq = (list.value.length || 0) + 1
  formUserPicks.feature_fo = null
  formUserPicks.feature_se = null
  formUserPicks.feature_tfo = null
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, row)
  for (const col of USER_COLS) {
    formUserPicks[col.field] = row[col.fkField] || row[col.field] || null
  }
  dialogVisible.value = true
}

function onFormUserColChange(col, v) {
  if (typeof v === 'number') {
    const u = userOptions.value.find((x) => x.id === v)
    formUserPicks[col.field] = v
    form[col.fkField] = v
    form[col.field] = u ? (u.full_name || u.username) : ''
  } else {
    formUserPicks[col.field] = v || null
    form[col.fkField] = null
    form[col.field] = v || ''
  }
}

async function onSubmit() {
  try {
    if (editing.value) {
      await productRequirementApi.update(editing.value.id, { ...form, version: editing.value.version })
      ElMessage.success('已更新')
      dialogVisible.value = false
      load()
    } else {
      await productRequirementApi.create({ ...form, iteration_id: props.iterationId })
      ElMessage.success('已创建')
      dialogVisible.value = false
      load()
    }
  } catch (e) {
    if (e.response?.status !== 409) ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function onDelete(row) {
  await ElMessageBox.confirm(`确认删除产品需求「${row.req_no || row.title}」吗？`, '提示', { type: 'warning' })
  await productRequirementApi.remove(row.id)
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
    const { data } = await productRequirementApi.update(row.id, { [field]: newVal, version: row.version })
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
    const { data } = await productRequirementApi.update(row.id, { [field]: value, version: row.version })
    row[field] = value
    row.version = data.version
  } catch (e) {
    row[field] = original
    if (e.response?.status !== 409) ElMessage.error(e.response?.data?.detail || '保存失败')
    else load()
  }
}

async function onUserColChange(row, col, value) {
  const payload = { version: row.version }
  if (typeof value === 'number') {
    const u = userOptions.value.find((x) => x.id === value)
    payload[col.fkField] = value
    payload[col.field] = u ? (u.full_name || u.username) : ''
  } else if (value) {
    payload[col.fkField] = null
    payload[col.field] = value
  } else {
    payload[col.fkField] = null
    payload[col.field] = ''
  }
  const snapshot = { [col.field]: row[col.field], [col.fkField]: row[col.fkField] }
  Object.assign(row, payload)
  try {
    const { data } = await productRequirementApi.update(row.id, payload)
    row.version = data.version
  } catch (e) {
    Object.assign(row, snapshot)
    if (e.response?.status !== 409) ElMessage.error(e.response?.data?.detail || '保存失败')
    else load()
  }
}

// 批量导入
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
    const resp = await productRequirementApi.importTemplate()
    downloadBlob(resp.data, 'iteration-product-requirements-template.xlsx')
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
    const { data } = await productRequirementApi.importExcel(props.iterationId, importFile.value)
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

// 特性管理
function openFeatureDialog() {
  featureDialog.list = [...features.value]
  featureDialog.visible = true
}

async function onSaveFeatures() {
  featureDialog.saving = true
  try {
    const clean = featureDialog.list.map(s => (s || '').trim()).filter(Boolean)
    // 去重保持原顺序
    const seen = new Set()
    const dedup = []
    for (const v of clean) if (!seen.has(v)) { seen.add(v); dedup.push(v) }
    await configApi.save({ product_features: dedup })
    features.value = dedup
    featureDialog.visible = false
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    featureDialog.saving = false
  }
}

defineExpose({ load })

onMounted(() => {
  load()
  loadFeatures()
  loadUserOptions()
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
  word-break: break-word;
}
.feature-tip {
  color: #606266;
  font-size: 12px;
  margin-bottom: 10px;
  line-height: 1.6;
}
.feature-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
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
