<template>
  <div>
    <!-- Project tabs -->
    <el-tabs v-model="activeTab" @tab-change="onTabChange" class="project-tabs">
      <el-tab-pane
        v-for="proj in projects"
        :key="proj.id"
        :label="proj.name"
        :name="String(proj.id)"
      />
      <el-tab-pane label="现场调试版本" name="debug" />
    </el-tabs>

    <DebugVersionPanel v-if="activeTab === 'debug'" />

    <template v-else>
    <VersionTimeline v-if="majorVersions.length" :majors="majorVersions" />

    <el-card shadow="never">
      <div class="toolbar">
        <el-button v-if="isAdmin" type="primary" :icon="Plus" @click="openCreateMajor">新增大版本</el-button>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
        <span class="tip">大版本约 1.5 个月一个，迭代版本约每周一个</span>
      </div>

      <el-table
        :data="majorVersions"
        v-loading="loading"
        row-key="id"
        border
        stripe
        style="width: 100%"
        :default-sort="{ prop: 'version_no', order: 'ascending' }"
      >
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="expand-area">
              <div class="expand-header">
                <span class="expand-title">迭代版本（共 {{ row.iteration_versions?.length || 0 }} 个）</span>
                <el-button
                  v-if="isAdmin"
                  size="small"
                  type="primary"
                  :icon="Plus"
                  @click.stop="openCreateIter(row)"
                >
                  新增迭代版本
                </el-button>
              </div>
              <el-table
                :data="row.iteration_versions || []"
                border
                size="small"
                style="width: 100%"
                :default-sort="{ prop: 'version_no', order: 'ascending' }"
              >
                <el-table-column prop="version_no" label="版本号" width="130" sortable
                  :sort-method="(a, b) => naturalCompare(a.version_no, b.version_no)" />
                <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
                <el-table-column prop="planned_date" label="预计发布日期" width="150" sortable>
                  <template #default="{ row: ir }">{{ fmtDate(ir.planned_date) }}</template>
                </el-table-column>
                <el-table-column label="合入需求" width="100" align="center">
                  <template #default="{ row: ir }">
                    <el-button link type="primary" size="small" @click.stop="openMerge(ir)">查看</el-button>
                  </template>
                </el-table-column>
                <el-table-column v-if="isAdmin" label="操作" width="140" fixed="right">
                  <template #default="{ row: ir }">
                    <el-button size="small" @click.stop="openEditIter(ir)">编辑</el-button>
                    <el-button size="small" type="danger" @click.stop="onDeleteIter(ir)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="version_no" label="版本号" width="120" sortable
          :sort-method="(a, b) => naturalCompare(a.version_no, b.version_no)" />
        <el-table-column prop="title" label="标题" min-width="160" sortable
          :sort-method="(a, b) => naturalCompare(a.title, b.title)" />
        <el-table-column prop="description" label="版本说明" min-width="200" show-overflow-tooltip />
        <el-table-column label="版本范围" width="230">
          <template #default="{ row }">
            <span v-if="row.range_start || row.range_end">
              {{ fmtDate(row.range_start) }} ~ {{ fmtDate(row.range_end) }}
            </span>
            <span v-else style="color:#c0c4cc">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="actual_release_date" label="实际发布" width="120" sortable>
          <template #default="{ row }">
            <el-tag v-if="row.actual_release_date" type="success" size="small">
              {{ fmtDate(row.actual_release_date) }}
            </el-tag>
            <span v-else style="color:#c0c4cc">待发布</span>
          </template>
        </el-table-column>
        <el-table-column label="迭代数" width="70" align="center">
          <template #default="{ row }">
            <el-tag type="info" size="small">{{ row.iteration_versions?.length || 0 }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin" label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEditMajor(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="onDeleteMajor(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    </template>

    <!-- Major version dialog -->
    <el-dialog
      v-model="majorDialogVisible"
      :title="editingMajor ? '编辑大版本' : '新增大版本'"
      width="600px"
      @closed="editingMajor = null"
    >
      <el-form :model="majorForm" label-width="110px">
        <el-form-item label="版本号" required>
          <el-input v-model="majorForm.version_no" placeholder="例如 V2.5" />
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="majorForm.title" placeholder="例如 春季正式版" />
        </el-form-item>
        <el-form-item label="版本说明">
          <el-input v-model="majorForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="版本范围开始">
          <el-date-picker
            v-model="majorForm.range_start"
            type="date"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="版本范围结束">
          <el-date-picker
            v-model="majorForm.range_end"
            type="date"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="实际发布时间">
          <el-date-picker
            v-model="majorForm.actual_release_date"
            type="date"
            value-format="YYYY-MM-DDTHH:mm:ss"
            placeholder="发布后填写"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="majorDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSubmitMajor">保存</el-button>
      </template>
    </el-dialog>

    <!-- 合入需求查看对话框 -->
    <VersionMergeDialog
      v-model="mergeVisible"
      :version-id="mergeVersion.id"
      :version-no="mergeVersion.version_no"
      :version-title="mergeVersion.title"
    />

    <!-- Iteration version dialog -->
    <el-dialog
      v-model="iterDialogVisible"
      :title="editingIter ? '编辑迭代版本' : '新增迭代版本'"
      width="520px"
      @closed="editingIter = null"
    >
      <el-form :model="iterForm" label-width="110px">
        <el-form-item label="版本号" required>
          <el-input v-model="iterForm.version_no" placeholder="例如 V2.5.1" />
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="iterForm.title" placeholder="例如 第1迭代" />
        </el-form-item>
        <el-form-item label="预计发布日期">
          <el-date-picker
            v-model="iterForm.planned_date"
            type="date"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="iterDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSubmitIter">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { majorVersionApi, roadmapApi } from '../api'
import { fmtDate, naturalCompare } from '../utils/format'
import { auth } from '../store/auth'
import VersionTimeline from '../components/VersionTimeline.vue'
import DebugVersionPanel from '../components/DebugVersionPanel.vue'
import VersionMergeDialog from '../components/VersionMergeDialog.vue'

const isAdmin = auth.isAdmin

const projects = ref([])
const activeTab = ref('debug')   // 默认若无项目则停留在「客户面调试版本」
const majorVersions = ref([])
const loading = ref(false)

// 合入需求查看对话框（按迭代版本看其关联的产品/领域需求）
const mergeVisible = ref(false)
const mergeVersion = ref({ id: null, version_no: '', title: '' })
function openMerge(ir) {
  mergeVersion.value = { id: ir.id, version_no: ir.version_no, title: ir.title }
  mergeVisible.value = true
}

// major version dialog
const majorDialogVisible = ref(false)
const editingMajor = ref(null)
const majorForm = reactive(defaultMajorForm())

// iteration version dialog
const iterDialogVisible = ref(false)
const editingIter = ref(null)
const currentMajorId = ref(null)
const iterForm = reactive(defaultIterForm())

function defaultMajorForm() {
  return {
    version_no: '',
    title: '',
    description: '',
    range_start: null,
    range_end: null,
    actual_release_date: null,
  }
}

function defaultIterForm() {
  return {
    version_no: '',
    title: '',
    planned_date: null,
  }
}

async function loadProjects() {
  try {
    const { data } = await roadmapApi.listProjects(true)
    projects.value = data
    if (data.length > 0 && activeTab.value === 'debug') {
      activeTab.value = String(data[0].id)
    }
    load()
  } catch (e) {
    ElMessage.error('加载项目列表失败')
  }
}

async function load() {
  // 「客户面调试版本」tab 由 DebugVersionPanel 自行加载，这里不拉大版本
  if (activeTab.value === 'debug') { majorVersions.value = []; return }
  loading.value = true
  try {
    const { data } = await majorVersionApi.list(Number(activeTab.value))
    majorVersions.value = data
  } catch (e) {
    ElMessage.error('加载版本失败')
  } finally {
    loading.value = false
  }
}

function onTabChange() {
  load()
}

// ===== Major version CRUD =====
function openCreateMajor() {
  editingMajor.value = null
  Object.assign(majorForm, defaultMajorForm())
  majorDialogVisible.value = true
}

function openEditMajor(row) {
  editingMajor.value = row
  Object.assign(majorForm, {
    version_no: row.version_no,
    title: row.title,
    description: row.description,
    range_start: row.range_start,
    range_end: row.range_end,
    actual_release_date: row.actual_release_date,
  })
  majorDialogVisible.value = true
}

async function onSubmitMajor() {
  if (!majorForm.version_no.trim()) {
    ElMessage.warning('版本号不能为空')
    return
  }
  try {
    const projectId = Number(activeTab.value)
    if (editingMajor.value) {
      await majorVersionApi.update(editingMajor.value.id, majorForm)
      ElMessage.success('已更新')
    } else {
      await majorVersionApi.create({ ...majorForm, project_id: projectId })
      ElMessage.success('已创建')
    }
    majorDialogVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function onDeleteMajor(row) {
  await ElMessageBox.confirm(
    `确认删除大版本「${row.version_no}」及其所有迭代版本吗？`,
    '警告',
    { type: 'warning' }
  )
  try {
    await majorVersionApi.remove(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

// ===== Iteration version CRUD =====
function openCreateIter(majorRow) {
  editingIter.value = null
  currentMajorId.value = majorRow.id
  const nextSort = (majorRow.iteration_versions?.length || 0)
  Object.assign(iterForm, { ...defaultIterForm(), sort_order: nextSort })
  iterDialogVisible.value = true
}

function openEditIter(row) {
  editingIter.value = row
  Object.assign(iterForm, {
    version_no: row.version_no,
    title: row.title,
    planned_date: row.planned_date,
  })
  iterDialogVisible.value = true
}

async function onSubmitIter() {
  if (!iterForm.version_no.trim()) {
    ElMessage.warning('版本号不能为空')
    return
  }
  try {
    if (editingIter.value) {
      await majorVersionApi.updateIterVersion(editingIter.value.id, iterForm)
      ElMessage.success('已更新')
    } else {
      await majorVersionApi.createIterVersion({
        ...iterForm,
        major_version_id: currentMajorId.value,
        sort_order: iterForm.sort_order ?? 0,
      })
      ElMessage.success('已创建')
    }
    iterDialogVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function onDeleteIter(row) {
  await ElMessageBox.confirm(`确认删除迭代版本「${row.version_no}」吗？`, '提示', { type: 'warning' })
  try {
    await majorVersionApi.removeIterVersion(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

onMounted(loadProjects)
</script>

<style scoped>
.project-tabs {
  margin-bottom: 0;
}
.toolbar {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.tip {
  margin-left: auto;
  color: #909399;
  font-size: 12px;
}
.expand-area {
  padding: 12px 20px 12px 40px;
  background: #fafafa;
}
.expand-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.expand-title {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
}
</style>
