<template>
  <div>
    <!-- 机台总览与问题跟踪本就是一份数据的两个视角，收进同一页面的两个 tab -->
    <el-tabs v-model="pageTab" class="cs-tabs">
      <el-tab-pane label="机台总览" name="overview">
    <el-card shadow="never">
      <div class="toolbar">
        <el-button :type="editMode ? 'warning' : 'primary'" :icon="editMode ? Check : Edit" @click="editMode = !editMode">
          {{ editMode ? '完成' : '编辑' }}
        </el-button>
        <el-button v-if="isAdmin && editMode" :icon="Plus" @click="openCreate">新增</el-button>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
        <el-button v-if="isAdmin" :icon="Download" type="success" @click="onExport">导出 PPT</el-button>
        <el-button-group>
          <el-button :type="tableMode==='compact'?'primary':''" size="small" @click="tableMode='compact'">精简</el-button>
          <el-button :type="tableMode==='detail'?'primary':''" size="small" @click="tableMode='detail'">详细</el-button>
        </el-button-group>
        <el-checkbox v-model="showCompleted" label="显示已完成" size="small" />
        <span class="tip">
          {{ editMode ? '编辑模式：可直接修改各字段，完成后点「完成」退出' : '只读模式：点「编辑」进入可修改各字段' }}
        </span>
      </div>

      <el-table :data="list" v-loading="loading" border stripe style="width:100%"
        :default-sort="{ prop: 'machine_id', order: 'ascending' }">
        <el-table-column type="index" label="序号" width="60" align="center" :index="(i) => i + 1" />
        <el-table-column prop="machine_id" label="机台编号" width="110" align="center" sortable
          :sort-method="(a, b) => naturalCompare(a.machine_id, b.machine_id)" />
        <el-table-column prop="battlefield" label="客户" width="140" align="center" sortable
          :sort-method="(a, b) => naturalCompare(a.battlefield, b.battlefield)">
          <template #default="{ row }">
            <a class="bf-link" :title="'点击查看客户详情'" @click.stop="openCustomerDetail(row)">
              {{ row.battlefield || '—' }}
            </a>
          </template>
        </el-table-column>
        <el-table-column prop="model" label="型号" width="120" align="center" sortable />

        <el-table-column prop="current_stage" label="当前阶段" width="160" align="center" sortable>
          <template #default="{ row }">
            <el-select v-if="isAdmin && editMode" :model-value="row.current_stage" size="small" @change="(v) => onStageChange(row, v)">
              <el-option v-for="s in stages" :key="s" :label="s" :value="s" />
            </el-select>
            <span v-else>{{ row.current_stage || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="field_version" label="现场版本" width="170" align="center" sortable
          :sort-method="(a, b) => naturalCompare(a.field_version, b.field_version)">
          <template #default="{ row }">
            <el-select v-if="isAdmin && editMode" :model-value="row.field_version" size="small" filterable allow-create
              default-first-option placeholder="选择或输入" @change="(v) => onVersionChange(row, v)">
              <el-option v-for="v in versionOptions" :key="v.value" :label="v.label" :value="v.value" />
            </el-select>
            <span v-else>{{ row.field_version || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="attention_level" label="近期关注度" width="170" align="center" sortable
          :sort-method="(a, b) => (a.attention_level || 0) - (b.attention_level || 0)">
          <template #default="{ row }">
            <el-rate :model-value="row.attention_level || 0" :max="5" :disabled="!isAdmin || !editMode"
              show-score score-template="{value}" @change="(v) => onRateChange(row, v)" />
          </template>
        </el-table-column>

        <el-table-column label="当前进展" min-width="180">
          <template #default="{ row }">
            <el-input v-if="isEditing(row, 'customer_status')" v-model="row.customer_status"
              size="small" autofocus type="textarea" :rows="2"
              @blur="commit(row, 'customer_status')"
              @keyup.enter.ctrl="commit(row, 'customer_status')"
              @keyup.esc="cancel(row, 'customer_status')" />
            <div v-else :class="{ 'editable-cell': editMode }" @dblclick="editMode && startEdit(row, 'customer_status')">
              {{ row.customer_status || '—' }}
            </div>
          </template>
        </el-table-column>

        <!-- ── 现场关键事务 ────────────────────────────── -->
        <el-table-column label="现场关键事务" min-width="240">
          <template #default="{ row }">
            <CustomerIssueCell
              kind="task"
              :items="row.task_items"
              :machine-status-id="row.id"
              :edit-mode="editMode"
              :compact="tableMode === 'compact'"
              :show-completed="showCompleted"
              :is-admin="isAdmin"
              @refresh="reloadIssuesGrouped"
              @open="gotoTracking"
            />
          </template>
        </el-table-column>

        <!-- ── 软件类风险和问题 ──────────────────────── -->
        <el-table-column label="软件类风险和问题" min-width="280">
          <template #default="{ row }">
            <CustomerIssueCell
              kind="issue"
              :items="row.issue_items"
              :machine-status-id="row.id"
              :edit-mode="editMode"
              :compact="tableMode === 'compact'"
              :show-completed="showCompleted"
              :is-admin="isAdmin"
              @refresh="reloadIssuesGrouped"
              @open="gotoTracking"
            />
          </template>
        </el-table-column>

        <el-table-column label="关键特性" min-width="190" fixed="right">
          <template #header>
            <span>关键特性</span>
            <el-button link type="primary" size="small" :icon="TopRight" title="打开特性目录" @click="gotoKeyFeatures" />
          </template>
          <template #default="{ row }">
            <el-select v-if="editMode" :model-value="currentFeatureIds(row)" multiple filterable
                       collapse-tags collapse-tags-tooltip size="small" placeholder="选择特性" style="width:100%"
                       @change="(ids) => setMachineFeatures(row, ids)">
              <el-option v-for="f in featureCatalog" :key="f.id" :label="f.name || '(未命名)'" :value="f.id">
                <span class="feat-opt-dot" :style="{ background: featureColor(f.status) }" />{{ f.name || '(未命名)' }}
              </el-option>
            </el-select>
            <div v-else class="feat-cell" @click="gotoKeyFeatures">
              <template v-if="featuresByMachine[row.id] && featuresByMachine[row.id].length">
                <el-tooltip v-for="f in featuresByMachine[row.id]" :key="f.id"
                            :content="`${f.name}：${f.status}`" placement="top">
                  <span class="feat-tag" :style="{ background: featureColor(f.status) }">{{ f.name }}</span>
                </el-tooltip>
              </template>
              <span v-else class="muted">—</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="硬件清零" width="104" align="center" fixed="right">
          <template #default="{ row }">
            <span v-if="clearanceByMachine[row.id] && clearanceByMachine[row.id].total" class="clr-cell">
              <a class="clr-num" title="查看该机台清零情况" @click="gotoHardware(row)">{{ clearanceByMachine[row.id].done }}</a>
              <span class="clr-sep">/</span>
              <a class="clr-num" title="查看该机台清零情况" @click="gotoHardware(row)">{{ clearanceByMachine[row.id].total }}</a>
            </span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>

        <el-table-column v-if="isAdmin && editMode" label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
      </el-tab-pane>

      <el-tab-pane label="问题跟踪" name="issues">
        <!-- KeepAlive：首次懒加载，之后切换秒显；组件内 onActivated 静默刷新保持同步 -->
        <KeepAlive>
          <CustomerIssueTracking v-if="pageTab === 'issues'" :focus="trackingFocus" />
        </KeepAlive>
      </el-tab-pane>

      <el-tab-pane label="硬件问题清零" name="hardware">
        <KeepAlive>
          <HardwareClearance v-if="pageTab === 'hardware'" :focus-machine="hwFocusMachine" />
        </KeepAlive>
      </el-tab-pane>
    </el-tabs>

    <!-- ── 新增 / 编辑弹窗 ──────────────────────────── -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑' : '新增'" width="640px">
      <el-form :model="form" label-width="130px">
        <el-form-item label="机台编号">
          <el-input v-model="form.machine_id" :disabled="!!editing" :placeholder="editing ? '创建后不可修改' : '请输入'" />
        </el-form-item>
        <el-form-item label="客户">
          <template v-if="editing">
            <el-input v-model="form.battlefield" disabled placeholder="创建后不可修改" />
          </template>
          <template v-else>
            <el-select
              v-model="form.battlefield"
              filterable
              placeholder="请选择客户（仅可从客户管理中选）"
              style="width: 100%"
              no-data-text="客户管理中暂无客户，请先到「客户管理」新增"
            >
              <el-option
                v-for="c in customers"
                :key="c.id"
                :label="c.display_name ? `${c.code} · ${c.display_name}` : c.code"
                :value="c.code"
              />
            </el-select>
            <div class="dialog-tip">
              候选来自<router-link to="/customers" class="bf-link">客户管理</router-link>；如缺少请先到那里新增
            </div>
          </template>
        </el-form-item>
        <el-form-item label="型号">
          <el-input v-model="form.model" :disabled="!!editing" :placeholder="editing ? '创建后不可修改' : '请输入'" />
        </el-form-item>
        <el-form-item label="当前阶段">
          <el-select v-model="form.current_stage" placeholder="请选择" style="width:100%">
            <el-option v-for="s in stages" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="现场版本">
          <el-select v-model="form.field_version" filterable allow-create default-first-option placeholder="选择或输入" style="width:100%">
            <el-option v-for="v in versionOptions" :key="v.value" :label="v.label" :value="v.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="近期关注度">
          <el-rate v-model="form.attention_level" :max="5" show-score score-template="{value} 星" />
        </el-form-item>
        <el-form-item label="当前进展">
          <el-input v-model="form.customer_status" type="textarea" :rows="2" />
        </el-form-item>

        <el-alert v-if="editing" type="info" :closable="false" show-icon
          title="现场关键事务 / 软件类问题已改为独立条目"
          description="请在总览表格对应单元格里增删，或到「问题跟踪」总表维护紧急程度、责任人、时间等信息。" />
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Check, Download, Edit, Plus, Refresh, TopRight } from '@element-plus/icons-vue'
import { configApi, customerApi, customerIssueApi, customerStatusApi, downloadBlob, hardwareIssueApi, keyFeatureApi, majorVersionApi } from '../api'
import { auth } from '../store/auth'
import { customerIssues, ensureIssues, reloadIssues } from '../store/customerIssues'
import { featureColor } from '../utils/featureStatus'
import { naturalCompare } from '../utils/format'
import CustomerIssueCell from '../components/CustomerIssueCell.vue'
import CustomerIssueTracking from './CustomerIssueTracking.vue'
import HardwareClearance from './HardwareClearance.vue'

const router = useRouter()
const route = useRoute()

const isAdmin = auth.isAdmin

// 页面顶层 tab：overview=机台总览 / issues=问题跟踪；支持 ?tab=issues&focus=<id> 深链
const TAB_QUERY = { issues: 'issues', hardware: 'hardware' }
const pageTab = ref(TAB_QUERY[route.query.tab] || 'overview')
const trackingFocus = ref(Number(route.query.focus) || null)
const hwFocusMachine = ref(null)        // 从总览点"硬件清零"跳过来时聚焦的机台
const clearanceByMachine = ref({})      // {machine_status_id: {total, done}}
const featuresByMachine = ref({})       // {machine_status_id: [{id,name,status}...]}
const featureCatalog = ref([])          // 全量特性目录，供机台勾选

const list    = ref([])
const stages  = ref([])
const versions = ref([])
const customers = ref([])     // 来自客户管理的主数据，用于"新增机台"时的下拉
const loading = ref(false)
const dialogVisible = ref(false)
const editing = ref(null)
const form    = reactive(defaultForm())

const editingCell = ref(null)
const tableMode   = ref('compact')  // 'compact' | 'detail'
const editMode    = ref(false)      // 顶部「编辑」开关：默认只读，开启后才可改
const showCompleted = ref(false)    // 关键事务/软件类问题是否显示已闭环条目（默认藏起来）

const ADMIN_FIELDS = ['current_stage', 'field_version', 'attention_level', 'issue_url']
// recent_focus / key_issues 已迁到 customer_issues 表，不再随机台一起提交
const USER_FIELDS  = ['customer_status']

const versionOptions = computed(() => versions.value)

function defaultForm() {
  return {
    machine_id: '', battlefield: '', model: '',
    current_stage: '', field_version: '',
    attention_level: 0, customer_status: '', issue_url: '',
  }
}

// ── 数据加载 ──────────────────────────────────────────
// 条目单独一张表，与「问题跟踪」tab 共用一份全局缓存（store/customerIssues），
// 按机台分组挂到每行；避免总览与 tab 各自全量重拉。
function applyIssueGrouping() {
  const byMachine = {}
  for (const it of customerIssues.rows) {
    const g = (byMachine[it.machine_status_id] ||= { task: [], issue: [] })
    ;(it.kind === 'task' ? g.task : g.issue).push(it)
  }
  list.value = list.value.map(row => ({
    ...row,
    task_items:  byMachine[row.id]?.task  || [],
    issue_items: byMachine[row.id]?.issue || [],
  }))
}

// 初次进入：有缓存就秒显，无缓存才拉一次
async function loadIssues() {
  try {
    await ensureIssues()
    applyIssueGrouping()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '问题条目加载失败')
  }
}

// 单元格增删条目后：强制刷新缓存再重组（同时惠及问题跟踪 tab）
async function reloadIssuesGrouped() {
  try {
    await reloadIssues()
    applyIssueGrouping()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '问题条目刷新失败')
  }
}

async function load() {
  loading.value = true
  try {
    const { data } = await customerStatusApi.list()
    list.value = data.map(row => ({ ...row, task_items: [], issue_items: [] }))
    await loadIssues()
    loadClearance()   // 硬件清零汇总；失败不阻塞总览
    loadFeatures()    // 关键特性点灯；失败不阻塞总览
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

async function loadClearance() {
  try {
    const { data } = await hardwareIssueApi.machineSummary()
    clearanceByMachine.value = data || {}
  } catch {
    clearanceByMachine.value = {}
  }
}

async function loadFeatures() {
  try {
    const [bm, cat] = await Promise.all([keyFeatureApi.byMachine(), keyFeatureApi.list()])
    featuresByMachine.value = bm.data || {}
    featureCatalog.value = cat.data || []
  } catch {
    featuresByMachine.value = {}
    featureCatalog.value = []
  }
}

// 某机台当前勾选的特性 id 列表（点灯来源）
function currentFeatureIds(row) {
  return (featuresByMachine.value[row.id] || []).map(f => f.id)
}

// 机台勾选/取消关键特性 → 保存并本地更新点灯
async function setMachineFeatures(row, ids) {
  try {
    await keyFeatureApi.setMachine(row.id, ids)
    const byId = Object.fromEntries(featureCatalog.value.map(f => [f.id, f]))
    featuresByMachine.value = {
      ...featuresByMachine.value,
      [row.id]: ids.map(id => byId[id]).filter(Boolean).map(f => ({ id: f.id, name: f.name, status: f.status })),
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
    loadFeatures()
  }
}

// 点总览"硬件清零"格 → 切到硬件清零 tab 并筛选到该机台
function gotoHardware(row) {
  hwFocusMachine.value = row.id
  pageTab.value = 'hardware'
}

// 跳到关键特性目录页
function gotoKeyFeatures() {
  router.push({ path: '/key-features' })
}

// 点条目 → 跳到问题跟踪总表并聚焦该条；不传则只是打开总表
function gotoTracking(item) {
  trackingFocus.value = item?.id || null
  pageTab.value = 'issues'
}

// 从子 tab 切回总览时，用（可能被 tab 改过的）缓存重组，并刷新硬件清零计数
watch(pageTab, (v) => {
  if (v === 'overview' && list.value.length) {
    applyIssueGrouping()
    loadClearance()
  }
})

async function loadConfig() {
  try {
    const { data } = await configApi.get()
    stages.value = data.current_stages || []
  } catch {}
}

async function loadCustomers() {
  try {
    const { data } = await customerApi.list()
    customers.value = data
  } catch (e) {
    console.error('[CustomerStatus] 加载客户主数据失败:', e)
  }
}

async function loadVersions() {
  try {
    const [majorRes, iterRes] = await Promise.all([
      majorVersionApi.list(),
      majorVersionApi.allIterationVersions(),
    ])
    const iter = (iterRes.data || []).map(v => ({
      value: v.version_no,
      label: v.title ? `${v.version_no} · ${v.title}` : v.version_no,
    }))
    const major = (majorRes.data || []).map(v => ({
      value: v.version_no,
      label: v.title ? `${v.version_no} · ${v.title}` : v.version_no,
    }))
    // 去重，迭代版本在前（更接近客户实际现场版本）
    const seen = new Set()
    const merged = []
    for (const v of [...iter, ...major]) {
      if (!seen.has(v.value)) { seen.add(v.value); merged.push(v) }
    }
    versions.value = merged
    if (!merged.length) {
      console.warn('[CustomerStatus] 版本列表为空：请到「版本管理」新增大版本/迭代版本')
    }
  } catch (e) {
    console.error('[CustomerStatus] 加载版本列表失败:', e)
  }
}

// ── Dialog ────────────────────────────────────────────
function openCreate() {
  editing.value = null
  Object.assign(form, defaultForm())
  if (stages.value.length) form.current_stage = stages.value[0]
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, row)
  dialogVisible.value = true
}

async function onSubmit() {
  if (!editing.value) {
    if (!form.machine_id || !form.battlefield) {
      ElMessage.warning('机台编号、客户必填')
      return
    }
  }
  try {
    if (editing.value) {
      const payload = { version: form.version }
      for (const k of [...ADMIN_FIELDS, ...USER_FIELDS]) payload[k] = form[k]
      await customerStatusApi.update(editing.value.id, payload)
      ElMessage.success('已更新')
      dialogVisible.value = false
      load()
    } else {
      await customerStatusApi.create(form)
      ElMessage.success('已创建')
      dialogVisible.value = false
      load()
    }
  } catch (e) {
    if (e.response?.status !== 409) ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function onDelete(row) {
  await ElMessageBox.confirm(`确认删除机台 ${row.machine_id} 吗？`, '提示', { type: 'warning' })
  await customerStatusApi.remove(row.id)
  ElMessage.success('已删除')
  load()
}

// ── 行内文本编辑（当前进展 / 问题单链接） ───────────────
function isEditing(row, field) {
  return editingCell.value?.id === row.id && editingCell.value?.field === field
}

function startEdit(row, field) {
  if (ADMIN_FIELDS.includes(field) && !isAdmin.value) {
    ElMessage.warning('该字段仅管理员可修改')
    return
  }
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
  const newVal   = row[field]
  editingCell.value = null
  if (newVal === original) return
  try {
    const { data } = await customerStatusApi.update(row.id, { [field]: newVal, version: row.version })
    row.version = data.version
    ElMessage.success('已保存')
  } catch (e) {
    row[field] = original
    if (e.response?.status !== 409) ElMessage.error(e.response?.data?.detail || '保存失败')
    else load()
  }
}

async function onRateChange(row, value) {
  if (!isAdmin.value) { ElMessage.warning('关注度仅管理员可修改'); return }
  const original = row.attention_level || 0
  if (value === original) return
  try {
    const { data } = await customerStatusApi.update(row.id, { attention_level: value, version: row.version })
    row.attention_level = data.attention_level
    row.version = data.version
    ElMessage.success('已保存')
  } catch (e) {
    row.attention_level = original
    if (e.response?.status !== 409) ElMessage.error(e.response?.data?.detail || '保存失败')
    else load()
  }
}

async function onStageChange(row, value) {
  const original = row.current_stage
  if (value === original) return
  try {
    const { data } = await customerStatusApi.update(row.id, { current_stage: value, version: row.version })
    row.current_stage = data.current_stage
    row.version = data.version
    ElMessage.success('已保存')
  } catch (e) {
    row.current_stage = original
    if (e.response?.status !== 409) ElMessage.error(e.response?.data?.detail || '保存失败')
    else load()
  }
}

async function onVersionChange(row, value) {
  const original = row.field_version
  if (value === original) return
  try {
    const { data } = await customerStatusApi.update(row.id, { field_version: value, version: row.version })
    row.field_version = data.field_version
    row.version = data.version
    ElMessage.success('已保存')
  } catch (e) {
    row.field_version = original
    if (e.response?.status !== 409) ElMessage.error(e.response?.data?.detail || '保存失败')
    else load()
  }
}

async function onExport() {
  try {
    const resp = await customerStatusApi.exportPptx()
    const ts = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19)
    downloadBlob(resp.data, `customer-status-${ts}.pptx`)
    ElMessage.success('已导出')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导出失败')
  }
}

// ── 点击客户列：跳到完整的客户详情页 ──────────────────
async function openCustomerDetail(row) {
  const name = (row.battlefield || '').trim()
  if (!name) {
    ElMessage.warning('该机台未设置客户')
    return
  }
  try {
    const { data } = await customerApi.resolve(name)
    if (data && data.id) {
      router.push(`/customers/${data.id}`)
    } else if (isAdmin.value) {
      ElMessageBox.confirm(
        `「${name}」尚未在客户管理中登记（或作为别名关联）。是否现在去客户管理新建？`,
        '客户未关联',
        { type: 'info', confirmButtonText: '去客户管理', cancelButtonText: '取消' }
      ).then(() => router.push('/customers')).catch(() => {})
    } else {
      // 客户管理限 admin（路由守卫会拦），普通用户别引到跳转后被弹回首页的死路
      ElMessage.warning(`「${name}」尚未在客户管理中登记，请联系管理员补充客户主数据`)
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '查询客户失败')
  }
}

onMounted(async () => {
  loadConfig()
  loadVersions()
  loadCustomers()
  await load()
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
.bf-link {
  color: #409eff;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
}
.bf-link:hover { text-decoration: underline; }

/* 关键特性点灯列 */
.feat-cell { display: flex; flex-wrap: wrap; gap: 4px; cursor: pointer; min-height: 20px; }
.feat-tag {
  display: inline-block; padding: 1px 8px; border-radius: 10px;
  color: #fff; font-size: 12px; line-height: 18px; white-space: nowrap;
}
.feat-opt-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }

/* 硬件清零联动列 */
.clr-cell { font-variant-numeric: tabular-nums; }
.clr-num {
  color: #409eff; cursor: pointer; font-weight: 600; text-decoration: none;
}
.clr-num:hover { text-decoration: underline; }
.clr-sep { color: #c0c4cc; margin: 0 2px; }
.dialog-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
.hint {
  color: #909399;
  font-size: 13px;
  padding: 8px 4px;
}

/* ── 清单单元格 ── */
.cl-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.cl-empty { color: #c0c4cc; font-size: 13px; }

.cl-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  cursor: pointer;
  user-select: none;
  line-height: 1.5;
}
/* 只读模式：清单项不可点 */
.cl-item.ro { cursor: default; }

.cl-box {
  width: 14px;
  height: 14px;
  border: 1.5px solid #c0c4cc;
  border-radius: 3px;
  background: #fff;
  flex-shrink: 0;
  margin-top: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all .15s;
}
.cl-box.checked {
  background: #67c23a;
  border-color: #67c23a;
}
.cl-box.sm { width: 13px; height: 13px; margin-top: 1px; }

.cl-check-svg { width: 8px; height: 8px; display: block; }

.cl-text { flex: 1; font-size: 13px; transition: color .15s; }
.cl-text.done { color: #b0b3b8; text-decoration: line-through; }

.cl-del {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  border: none;
  background: transparent;
  color: #c0c4cc;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  padding: 0;
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 2px;
  transition: all .15s;
}
.cl-del:hover { background: #fef0f0; color: #f56c6c; }

.cl-more {
  display: inline-block;
  margin-left: 4px;
  padding: 1px 6px;
  border-radius: 8px;
  background: #ecf5ff;
  color: #409eff;
  font-size: 11px;
  font-weight: 500;
  align-self: center;
}

/* 进度条 */
.cl-progress-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 3px;
}
.cl-bar {
  flex: 1;
  height: 3px;
  background: #e4e7ed;
  border-radius: 2px;
  overflow: hidden;
}
.cl-fill {
  height: 100%;
  background: linear-gradient(90deg, #67c23a, #95d475);
  border-radius: 2px;
  transition: width .3s;
}
.cl-pct-text { font-size: 11px; color: #909399; white-space: nowrap; }

/* 新增行 */
.cl-add-row {
  display: flex;
  gap: 4px;
  align-items: center;
  margin-top: 2px;
}
.cl-add-input {
  flex: 1;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  padding: 2px 7px;
  font-size: 12px;
  outline: none;
  color: #303133;
  font-family: inherit;
  min-width: 0;
}
.cl-add-input:focus { border-color: #409eff; }
.cl-btn-ok, .cl-btn-no {
  padding: 1px 7px;
  border-radius: 3px;
  border: 1px solid;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.cl-btn-ok { background: #409eff; border-color: #409eff; color: #fff; }
.cl-btn-no { background: #fff; border-color: #dcdfe6; color: #606266; }

.cl-add-btn {
  align-self: flex-start;
  margin-top: 3px;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px dashed #c0c4cc;
  background: transparent;
  color: #909399;
  font-size: 12px;
  cursor: pointer;
  transition: all .15s;
}
.cl-add-btn:hover { border-color: #409eff; color: #409eff; background: #ecf5ff; }

/* Dialog 清单编辑器 */
.dialog-cl { display: flex; flex-direction: column; gap: 6px; width: 100%; }
.dialog-cl-row { display: flex; align-items: center; gap: 6px; }

/* 紧凑模式行 + 迷你新增按钮 */
.cl-compact-line {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: nowrap;
}
.cl-compact-line .cl-item { flex: 1; min-width: 0; }
.cl-compact-line .cl-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cl-add-btn-mini {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 4px;
  border: 1px dashed #c0c4cc;
  background: transparent;
  color: #909399;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all .15s;
}
.cl-add-btn-mini:hover {
  border-color: #409eff;
  color: #409eff;
  background: #ecf5ff;
  border-style: solid;
}

/* 问题单分布 drawer */
.drill-meta { color: #909399; font-size: 12px; margin-bottom: 6px; }
.drill-summary {
  background: #f5f7fa;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 13px;
  color: #606266;
  margin-bottom: 4px;
}
.drill-summary b { color: #409eff; font-size: 15px; margin: 0 2px; }
.hint { color: #909399; font-size: 13px; padding: 24px 0; text-align: center; }

.drill-sub-header {
  margin: 16px 0 4px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  color: #303133;
}
.drill-sub-header b { color: #409eff; }
.drill-note { color: #909399; font-size: 12px; margin: 0 0 8px; }
:deep(.drill-row-active) { background: #ecf5ff !important; }
:deep(.drill-row-active td) { color: #409eff !important; font-weight: 600; }
</style>
