<template>
  <div class="roadmap-manage">
    <el-row :gutter="16">
      <!-- 项目列表 -->
      <el-col :span="6">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <span><el-icon><Guide /></el-icon> 项目列表</span>
              <el-button type="primary" size="small" :icon="Plus" @click="openProjectCreate">新增</el-button>
            </div>
          </template>
          <div v-if="projectsLoading" class="hint">加载中…</div>
          <div v-else-if="!projects.length" class="hint">暂无项目，请点击「新增」</div>
          <div v-else class="project-list">
            <div
              v-for="p in projects"
              :key="p.id"
              class="project-item"
              :class="{ active: selectedId === p.id, inactive: !p.is_active }"
              @click="selectProject(p.id)"
            >
              <div class="row">
                <div class="name">{{ p.name }}</div>
                <el-tag size="small" :type="p.granularity === 'month' ? 'warning' : 'primary'" effect="plain">
                  {{ p.granularity === 'month' ? '月度' : '季度' }}
                </el-tag>
              </div>
              <div class="meta">
                <span v-if="p.year">{{ p.year }} 年</span>
                <span v-if="!p.is_active" class="off">已隐藏</span>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 项目详情：阶段 + 里程碑 -->
      <el-col :span="18">
        <el-card v-if="!selected" shadow="never">
          <el-empty description="请选择左侧项目，或点击「新增」创建" />
        </el-card>

        <template v-else>
          <el-card shadow="never" class="detail-card">
            <template #header>
              <div class="card-head">
                <span><el-icon><Folder /></el-icon> {{ selected.name }}</span>
                <div>
                  <el-button size="small" :icon="EditPen" @click="openProjectEdit">编辑项目</el-button>
                  <el-button size="small" type="danger" :icon="Delete" @click="onDeleteProject">删除项目</el-button>
                </div>
              </div>
            </template>
            <el-descriptions :column="3" size="small" border>
              <el-descriptions-item label="描述">{{ selected.description || '—' }}</el-descriptions-item>
              <el-descriptions-item label="年份">{{ selected.year || '—' }}</el-descriptions-item>
              <el-descriptions-item label="精度">
                {{ selected.granularity === 'month' ? '月度' : '季度' }}
              </el-descriptions-item>
              <el-descriptions-item label="是否展示">
                <el-tag size="small" :type="selected.is_active ? 'success' : 'info'">
                  {{ selected.is_active ? '展示' : '隐藏' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="排序">{{ selected.sort_order ?? 0 }}</el-descriptions-item>
            </el-descriptions>
          </el-card>

          <!-- 阶段 -->
          <el-card shadow="never" class="detail-card">
            <template #header>
              <div class="card-head">
                <span><el-icon><Histogram /></el-icon> 阶段（顶部块）</span>
                <el-button size="small" type="primary" :icon="Plus" @click="openPhaseCreate">新增阶段</el-button>
              </div>
            </template>
            <el-table :data="selected.phases || []" border stripe size="small" empty-text="暂无阶段">
              <el-table-column type="index" label="#" width="50" align="center" />
              <el-table-column prop="name" label="名称" width="140" />
              <el-table-column label="颜色" width="80">
                <template #default="{ row }">
                  <span class="color-chip" :style="{ background: row.color }" />
                  <span class="color-text">{{ row.color }}</span>
                </template>
              </el-table-column>
              <el-table-column label="时间范围" width="180" align="center">
                <template #default="{ row }">
                  {{ row.start_year }}.{{ row.start_month }} — {{ row.end_year }}.{{ row.end_month }}
                </template>
              </el-table-column>
              <el-table-column prop="core_products" label="核心产品" width="160" show-overflow-tooltip />
              <el-table-column prop="goal" label="目标" min-width="220" show-overflow-tooltip>
                <template #default="{ row }">
                  <span class="multiline">{{ row.goal || '—' }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="sort_order" label="排序" width="70" align="center" />
              <el-table-column label="操作" width="140" fixed="right">
                <template #default="{ row }">
                  <el-button size="small" @click="openPhaseEdit(row)">编辑</el-button>
                  <el-button size="small" type="danger" @click="onDeletePhase(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>

          <!-- 里程碑 -->
          <el-card shadow="never" class="detail-card">
            <template #header>
              <div class="card-head">
                <span><el-icon><Flag /></el-icon> 里程碑（时间轴下方卡片）</span>
                <el-button size="small" type="primary" :icon="Plus" @click="openMilestoneCreate">新增里程碑</el-button>
              </div>
            </template>
            <el-table :data="selected.milestones || []" border stripe size="small" empty-text="暂无里程碑">
              <el-table-column type="index" label="#" width="50" align="center" />
              <el-table-column label="时间" width="130" align="center">
                <template #default="{ row }">{{ row.year }} 年 {{ row.month }} 月</template>
              </el-table-column>
              <el-table-column prop="title" label="产品/版本（蓝框）" width="200" />
              <el-table-column prop="description" label="描述" min-width="280">
                <template #default="{ row }">
                  <span class="multiline">{{ row.description || '—' }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="sort_order" label="排序" width="70" align="center" />
              <el-table-column label="操作" width="140" fixed="right">
                <template #default="{ row }">
                  <el-button size="small" @click="openMilestoneEdit(row)">编辑</el-button>
                  <el-button size="small" type="danger" @click="onDeleteMilestone(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>

          <!-- 预览 -->
          <el-card shadow="never" class="detail-card">
            <template #header>
              <span><el-icon><View /></el-icon> 实时预览</span>
            </template>
            <RoadmapTimeline :project="selected" />
          </el-card>
        </template>
      </el-col>
    </el-row>

    <!-- 项目 新增/编辑 -->
    <el-dialog v-model="projectDlg" :title="projectEditing ? '编辑项目' : '新增项目'" width="520px">
      <el-form :model="projectForm" label-width="90px">
        <el-form-item label="名称">
          <el-input v-model="projectForm.name" placeholder="例如：战略型产品路线图" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="projectForm.description" placeholder="可选" />
        </el-form-item>
        <el-form-item label="年份">
          <el-input-number v-model="projectForm.year" :min="2000" :max="2100" controls-position="right" />
        </el-form-item>
        <el-form-item label="精度">
          <el-radio-group v-model="projectForm.granularity">
            <el-radio value="quarter">季度</el-radio>
            <el-radio value="month">月度</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="projectForm.sort_order" :min="0" controls-position="right" />
        </el-form-item>
        <el-form-item label="是否展示">
          <el-switch v-model="projectForm.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="projectDlg = false">取消</el-button>
        <el-button type="primary" @click="onSaveProject">保存</el-button>
      </template>
    </el-dialog>

    <!-- 阶段 新增/编辑 -->
    <el-dialog v-model="phaseDlg" :title="phaseEditing ? '编辑阶段' : '新增阶段'" width="600px">
      <el-form :model="phaseForm" label-width="100px">
        <el-form-item label="名称">
          <el-input v-model="phaseForm.name" placeholder="例如：启动阶段" />
        </el-form-item>
        <el-form-item label="主色">
          <div class="color-row">
            <el-color-picker v-model="phaseForm.color" />
            <el-button
              v-for="c in PRESET_COLORS"
              :key="c"
              size="small"
              class="color-preset"
              :style="{ background: c }"
              @click="phaseForm.color = c"
            />
          </div>
        </el-form-item>
        <el-form-item label="起始时间">
          <el-input-number v-model="phaseForm.start_year" :min="1900" :max="2200" controls-position="right" />
          <span class="dash">年</span>
          <el-input-number v-model="phaseForm.start_month" :min="1" :max="12" controls-position="right" />
          <span class="dash">月</span>
        </el-form-item>
        <el-form-item label="结束时间">
          <el-input-number v-model="phaseForm.end_year" :min="1900" :max="2200" controls-position="right" />
          <span class="dash">年</span>
          <el-input-number v-model="phaseForm.end_month" :min="1" :max="12" controls-position="right" />
          <span class="dash">月</span>
        </el-form-item>
        <el-form-item label="目标">
          <el-input
            v-model="phaseForm.goal"
            type="textarea"
            :rows="3"
            placeholder="每行一条，比如：&#10;1. 第一个目标&#10;2. 第二个目标"
          />
        </el-form-item>
        <el-form-item label="核心产品">
          <el-input v-model="phaseForm.core_products" placeholder="例如：AFKGoo、Sharaly" />
        </el-form-item>
        <el-form-item label="应用场景">
          <el-input
            v-model="phaseForm.scenarios"
            type="textarea"
            :rows="2"
            placeholder="每行一条"
          />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="phaseForm.sort_order" :min="0" controls-position="right" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="phaseDlg = false">取消</el-button>
        <el-button type="primary" @click="onSavePhase">保存</el-button>
      </template>
    </el-dialog>

    <!-- 里程碑 新增/编辑 -->
    <el-dialog v-model="msDlg" :title="msEditing ? '编辑里程碑' : '新增里程碑'" width="520px">
      <el-form :model="msForm" label-width="100px">
        <el-form-item label="时间">
          <el-input-number v-model="msForm.year" :min="1900" :max="2200" controls-position="right" />
          <span class="dash">年</span>
          <el-input-number v-model="msForm.month" :min="1" :max="12" controls-position="right" />
          <span class="dash">月</span>
        </el-form-item>
        <el-form-item label="产品/版本">
          <el-input v-model="msForm.title" placeholder="蓝框中的文字，可留空" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="msForm.description"
            type="textarea"
            :rows="3"
            placeholder="每行一条，比如：&#10;产品 MRD、技术新底盘"
          />
        </el-form-item>
        <el-form-item label="同月排序">
          <el-input-number v-model="msForm.sort_order" :min="0" controls-position="right" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="msDlg = false">取消</el-button>
        <el-button type="primary" @click="onSaveMilestone">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, EditPen, Delete, Guide, Folder, Histogram, Flag, View } from '@element-plus/icons-vue'
import { roadmapApi } from '../api'
import RoadmapTimeline from './RoadmapTimeline.vue'

const PRESET_COLORS = ['#67C23A', '#409EFF', '#F56C6C', '#E6A23C', '#909399', '#8E7AD8']

const projects = ref([])
const projectsLoading = ref(false)
const selectedId = ref(null)

const selected = computed(() => projects.value.find((p) => p.id === selectedId.value) || null)

// ----- Project dialog state -----
const projectDlg = ref(false)
const projectEditing = ref(null)
const projectForm = reactive(defaultProjectForm())
function defaultProjectForm() {
  return {
    name: '',
    description: '',
    year: new Date().getFullYear(),
    granularity: 'quarter',
    sort_order: 0,
    is_active: true,
  }
}

// ----- Phase dialog state -----
const phaseDlg = ref(false)
const phaseEditing = ref(null)
const phaseForm = reactive(defaultPhaseForm())
function defaultPhaseForm() {
  const y = new Date().getFullYear()
  return {
    name: '',
    color: '#409EFF',
    start_year: y,
    start_month: 1,
    end_year: y,
    end_month: 3,
    goal: '',
    core_products: '',
    scenarios: '',
    sort_order: 0,
    version: 0,
  }
}

// ----- Milestone dialog state -----
const msDlg = ref(false)
const msEditing = ref(null)
const msForm = reactive(defaultMsForm())
function defaultMsForm() {
  return {
    year: new Date().getFullYear(),
    month: 1,
    title: '',
    description: '',
    sort_order: 0,
  }
}

async function loadProjects(keepSelection = true) {
  projectsLoading.value = true
  try {
    const { data } = await roadmapApi.listProjects(true) // 后台展示包含未启用
    projects.value = data
    if (keepSelection && selectedId.value) {
      if (!projects.value.some((p) => p.id === selectedId.value)) {
        selectedId.value = projects.value[0]?.id || null
      }
    } else if (!selectedId.value) {
      selectedId.value = projects.value[0]?.id || null
    }
  } catch (e) {
    ElMessage.error('加载项目失败')
  } finally {
    projectsLoading.value = false
  }
}

function selectProject(id) {
  selectedId.value = id
}

// ----- Project actions -----
function openProjectCreate() {
  projectEditing.value = null
  Object.assign(projectForm, defaultProjectForm())
  projectDlg.value = true
}
function openProjectEdit() {
  if (!selected.value) return
  projectEditing.value = selected.value
  Object.assign(projectForm, {
    name: selected.value.name,
    description: selected.value.description,
    year: selected.value.year,
    granularity: selected.value.granularity,
    sort_order: selected.value.sort_order ?? 0,
    is_active: selected.value.is_active,
  })
  projectDlg.value = true
}
async function onSaveProject() {
  if (!projectForm.name?.trim()) {
    ElMessage.warning('请填写项目名称')
    return
  }
  try {
    if (projectEditing.value) {
      const { data } = await roadmapApi.updateProject(projectEditing.value.id, projectForm)
      ElMessage.success('已更新')
      selectedId.value = data.id
    } else {
      const { data } = await roadmapApi.createProject(projectForm)
      ElMessage.success('已创建')
      selectedId.value = data.id
    }
    projectDlg.value = false
    await loadProjects()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}
async function onDeleteProject() {
  if (!selected.value) return
  await ElMessageBox.confirm(
    `确认删除项目「${selected.value.name}」？相关阶段和里程碑会一并删除。`,
    '提示',
    { type: 'warning' }
  )
  try {
    await roadmapApi.removeProject(selected.value.id)
    ElMessage.success('已删除')
    selectedId.value = null
    await loadProjects(false)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

// ----- Phase actions -----
function openPhaseCreate() {
  if (!selected.value) return
  phaseEditing.value = null
  const base = defaultPhaseForm()
  if (selected.value.year) {
    base.start_year = selected.value.year
    base.end_year = selected.value.year
  }
  Object.assign(phaseForm, base)
  phaseDlg.value = true
}
function openPhaseEdit(row) {
  phaseEditing.value = row
  Object.assign(phaseForm, {
    name: row.name,
    color: row.color || '#409EFF',
    start_year: row.start_year,
    start_month: row.start_month,
    end_year: row.end_year,
    end_month: row.end_month,
    goal: row.goal || '',
    core_products: row.core_products || '',
    scenarios: row.scenarios || '',
    sort_order: row.sort_order ?? 0,
    version: row.version ?? 0,
  })
  phaseDlg.value = true
}
async function onSavePhase() {
  if (!selected.value) return
  if (!phaseForm.name?.trim()) {
    ElMessage.warning('请填写阶段名称')
    return
  }
  const startAbs = phaseForm.start_year * 12 + (phaseForm.start_month - 1)
  const endAbs = phaseForm.end_year * 12 + (phaseForm.end_month - 1)
  if (endAbs < startAbs) {
    ElMessage.warning('结束时间不能早于起始时间')
    return
  }
  try {
    if (phaseEditing.value) {
      await roadmapApi.updatePhase(phaseEditing.value.id, phaseForm)
      ElMessage.success('已更新')
      phaseDlg.value = false
      await loadProjects()
    } else {
      await roadmapApi.createPhase({ ...phaseForm, project_id: selected.value.id })
      ElMessage.success('已创建')
      phaseDlg.value = false
      await loadProjects()
    }
  } catch (e) {
    if (e.response?.status !== 409) ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}
async function onDeletePhase(row) {
  await ElMessageBox.confirm(`确认删除阶段「${row.name}」？`, '提示', { type: 'warning' })
  try {
    await roadmapApi.removePhase(row.id)
    ElMessage.success('已删除')
    await loadProjects()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

// ----- Milestone actions -----
function openMilestoneCreate() {
  if (!selected.value) return
  msEditing.value = null
  const base = defaultMsForm()
  if (selected.value.year) base.year = selected.value.year
  Object.assign(msForm, base)
  msDlg.value = true
}
function openMilestoneEdit(row) {
  msEditing.value = row
  Object.assign(msForm, {
    year: row.year,
    month: row.month,
    title: row.title || '',
    description: row.description || '',
    sort_order: row.sort_order ?? 0,
  })
  msDlg.value = true
}
async function onSaveMilestone() {
  if (!selected.value) return
  try {
    if (msEditing.value) {
      await roadmapApi.updateMilestone(msEditing.value.id, msForm)
      ElMessage.success('已更新')
    } else {
      await roadmapApi.createMilestone({ ...msForm, project_id: selected.value.id })
      ElMessage.success('已创建')
    }
    msDlg.value = false
    await loadProjects()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}
async function onDeleteMilestone(row) {
  await ElMessageBox.confirm(`确认删除 ${row.year} 年 ${row.month} 月的里程碑？`, '提示', { type: 'warning' })
  try {
    await roadmapApi.removeMilestone(row.id)
    ElMessage.success('已删除')
    await loadProjects()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

onMounted(() => loadProjects(false))
</script>

<style scoped>
.roadmap-manage { padding: 4px; }

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}
.card-head .el-icon { vertical-align: middle; margin-right: 4px; }

.hint {
  color: #909399;
  text-align: center;
  padding: 20px 0;
  font-size: 13px;
}

.project-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.project-item {
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid #ebeef5;
  transition: all 0.15s ease;
}
.project-item:hover {
  border-color: #c6e2ff;
  background: #f5faff;
}
.project-item.active {
  border-color: #409EFF;
  background: #ecf5ff;
}
.project-item.inactive { opacity: 0.6; }
.project-item .row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
}
.project-item .name {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.project-item .meta {
  font-size: 11px;
  color: #909399;
  margin-top: 4px;
  display: flex;
  gap: 6px;
}
.project-item .meta .off { color: #e6a23c; }

.detail-card { margin-bottom: 14px; }
.detail-card:last-child { margin-bottom: 0; }

.color-chip {
  display: inline-block;
  width: 14px; height: 14px;
  border-radius: 3px;
  vertical-align: middle;
  margin-right: 6px;
  border: 1px solid #ebeef5;
}
.color-text { font-size: 12px; color: #606266; }

.color-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.color-preset {
  width: 22px; height: 22px;
  padding: 0;
  border-radius: 4px;
  border: 1px solid #dcdfe6;
}
.dash { margin: 0 8px; color: #909399; }

.multiline {
  white-space: pre-wrap;
  display: inline-block;
  line-height: 1.55;
}
</style>
