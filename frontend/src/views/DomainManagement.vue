<template>
  <div class="domain-page">
    <el-tabs v-model="activeTab" class="domain-tabs">
      <!-- ===== 领域总览 ===== -->
      <el-tab-pane label="领域总览" name="overview">
        <div class="page-head">
          <div class="head-left">
            <span class="muted">需求口径：</span>
            <el-select v-model="monthKey" size="small" style="width: 210px" @change="load">
              <el-option label="进行中迭代（默认）" value="" />
              <el-option
                v-for="it in data.iterations"
                :key="it.year + '-' + it.month"
                :value="it.year + '-' + it.month"
                :label="it.label + statusSuffix(it)"
              />
            </el-select>
            <el-tag type="primary" effect="plain" style="margin-left: 8px">{{ data.iteration_label || '—' }}</el-tag>
            <span class="muted" style="margin-left: 16px">问题单：</span>
            <el-tag v-if="issueMeta.available" type="success" effect="plain">
              {{ issueMeta.file_mtime || '已接入' }}
            </el-tag>
            <el-tooltip v-else :content="issueMeta.note || '未接入'" placement="top">
              <el-tag type="info" effect="plain">未接入</el-tag>
            </el-tooltip>
          </div>
          <div class="head-right">
            <el-checkbox v-model="showHidden" @change="load">显示已隐藏</el-checkbox>
            <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
          </div>
        </div>

        <el-table :data="data.rows" border stripe v-loading="loading" class="domain-table"
          :row-class-name="(o) => (o.row.hidden ? 'hidden-row' : '')">
          <el-table-column label="领域" min-width="180" fixed>
            <template #default="{ row }">
              <div class="domain-name">
                {{ row.name }}
                <el-tag v-if="row.hidden" size="small" type="info" effect="plain">已隐藏</el-tag>
              </div>
              <div class="domain-meta">
                <el-tag v-if="row.dept_name" size="small" effect="plain">{{ row.dept_name }}</el-tag>
                <span v-if="row.leader_name" class="muted">PL：{{ row.leader_name }}</span>
                <span class="muted">{{ row.member_count }} 人</span>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="需求情况" min-width="200">
            <template #default="{ row }">
              <div v-if="row.req_summary.total" class="cell-clickable" @click="openReq(row)">
                <div class="sum-line">
                  <b>{{ row.req_summary.total }}</b> 项
                  <el-tag size="small" type="success" effect="plain">完成 {{ row.req_summary.done }}</el-tag>
                  <el-tag size="small" type="warning" effect="plain">进行 {{ row.req_summary.in_progress }}</el-tag>
                  <el-tag size="small" type="info" effect="plain">未开始 {{ row.req_summary.not_started }}</el-tag>
                  <el-tag v-if="row.req_summary.delayed" size="small" type="danger">延期 {{ row.req_summary.delayed }}</el-tag>
                </div>
                <div class="prio-line">
                  <span v-for="(n, p) in row.req_summary.by_priority" :key="p" class="prio">{{ p }}:{{ n }}</span>
                </div>
              </div>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>

          <el-table-column label="问题单情况" min-width="190">
            <template #header>
              问题单情况
              <el-tooltip placement="top" content="加权总分：致命 10 分 / 严重 3 分 / 一般 1 分 / 提示 0.1 分">
                <el-icon class="hdr-help"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <template v-if="row.issue_summary.available">
                <div v-if="row.issue_summary.total" class="cell-clickable" @click="openIssues(row)">
                  <div class="sum-line">
                    <b>{{ row.issue_summary.total }}</b> 个
                    <span class="score-sep">·</span>
                    <b class="issue-score">{{ row.issue_summary.score }}</b> 分
                  </div>
                  <div class="sev-line">
                    <span v-for="(n, s) in row.issue_summary.by_severity" :key="s">
                      <el-tag size="small" :type="sevType(s)" :effect="s === '致命' ? 'dark' : 'plain'">{{ s }} {{ n }}</el-tag>
                    </span>
                  </div>
                </div>
                <span v-else class="muted">无</span>
              </template>
              <span v-else class="muted">未接入</span>
            </template>
          </el-table-column>

          <el-table-column label="最近主要工作" min-width="260">
            <template #default="{ row }">
              <div v-if="row.recent_work" class="rich-cell" v-html="row.recent_work" />
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>

          <el-table-column label="风险与求助" min-width="240">
            <template #default="{ row }">
              <div v-if="row.risks && row.risks.length" class="risk-list">
                <div v-for="(r, i) in row.risks" :key="i" class="risk-item">
                  <el-tag size="small" :type="r.type === '求助' ? 'warning' : 'danger'" effect="plain">{{ r.type }}</el-tag>
                  <span class="risk-content">{{ r.content }}</span>
                  <span v-if="r.status" class="muted">（{{ r.status }}）</span>
                </div>
              </div>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>

          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button v-if="!row.hidden" link type="danger" @click="hideDomain(row)">移除</el-button>
              <el-button v-else link type="success" @click="restoreDomain(row)">恢复</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ===== 事务与风险跟踪 ===== -->
      <el-tab-pane label="事务与风险跟踪" name="risks">
        <div class="page-head">
          <div class="head-left">
            <el-button type="primary" :icon="Plus" @click="openRisk()">新增</el-button>
            <el-checkbox v-model="showDoneRisks" style="margin-left: 12px" @change="loadRisks">显示已闭环 / 挂起</el-checkbox>
            <span class="muted" style="margin-left: 12px">共 {{ riskRows.length }} 条</span>
          </div>
          <el-button :icon="Refresh" :loading="riskLoading" @click="loadRisks">刷新</el-button>
        </div>

        <el-table :data="riskRows" border stripe size="small" v-loading="riskLoading"
          :row-class-name="(o) => riskRowClass(o.row)">
          <el-table-column prop="seq" label="序号" width="64" align="center" />
          <el-table-column prop="content" label="风险和事务" min-width="240" show-overflow-tooltip />
          <el-table-column label="优先级" width="80" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="prioType(row.priority)">{{ row.priority || '—' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="progress" label="当前进展" min-width="180" show-overflow-tooltip />
          <el-table-column label="责任领域" width="150">
            <template #default="{ row }">
              <el-tag v-if="row.domain_name" size="small" effect="plain">{{ row.domain_name }}</el-tag>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="计划闭环时间" width="130">
            <template #default="{ row }">{{ fmtDate(row.planned_close_date) || '—' }}</template>
          </el-table-column>
          <el-table-column label="当前状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="statusType(row.status)" effect="dark">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openRisk(row)">编辑</el-button>
              <el-button link type="danger" size="small" @click="delRisk(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 编辑：最近主要工作 + 风险求助 -->
    <el-dialog v-model="editVisible" :title="`编辑 · ${editRow?.name || ''}`" width="760px" :close-on-click-modal="false">
      <div class="edit-section-title">最近主要工作</div>
      <RichTextEditor v-model="editForm.recent_work" min-height="140px" placeholder="本周期该领域的主要进展…" />

      <div class="edit-section-title" style="margin-top: 18px">
        风险与求助
        <el-button size="small" :icon="Plus" @click="addRisk">添加一条</el-button>
      </div>
      <div v-if="!editForm.risks.length" class="muted" style="padding: 8px 0">暂无，点击「添加一条」。</div>
      <div v-for="(r, i) in editForm.risks" :key="i" class="risk-edit-row">
        <el-select v-model="r.type" style="width: 90px">
          <el-option label="风险" value="风险" />
          <el-option label="求助" value="求助" />
        </el-select>
        <el-input v-model="r.content" placeholder="内容" />
        <el-input v-model="r.status" placeholder="状态/进展" style="width: 160px" />
        <el-button :icon="Delete" circle type="danger" plain @click="editForm.risks.splice(i, 1)" />
      </div>

      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 事务/风险 编辑弹窗 -->
    <el-dialog v-model="riskVisible" :title="riskForm.id ? '编辑事务/风险' : '新增事务/风险'" width="600px" :close-on-click-modal="false">
      <el-form :model="riskForm" label-width="100px">
        <el-form-item label="风险和事务" required>
          <el-input v-model="riskForm.content" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="riskForm.priority" style="width: 160px">
            <el-option v-for="p in PRIORITIES" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="责任领域">
          <el-select v-model="riskForm.domain_id" clearable filterable placeholder="选择领域（PL组）" style="width: 100%">
            <el-option v-for="d in domainOptions" :key="d.id" :value="d.id" :label="d.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="当前进展">
          <el-input v-model="riskForm.progress" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="计划闭环时间">
          <el-date-picker v-model="riskForm.planned_close_date" type="date" value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
        </el-form-item>
        <el-form-item label="当前状态">
          <el-select v-model="riskForm.status" style="width: 160px">
            <el-option v-for="s in STATUSES" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="riskVisible = false">取消</el-button>
        <el-button type="primary" :loading="riskSaving" @click="saveRisk">保存</el-button>
      </template>
    </el-dialog>

    <!-- 下钻：需求明细 -->
    <el-dialog v-model="reqVisible" :title="`需求明细 · ${drillName}`" width="900px">
      <el-table :data="reqRows" border stripe max-height="60vh" v-loading="reqLoading">
        <el-table-column label="编号" width="120">
          <template #default="{ row }">
            <a v-if="row.req_url" :href="row.req_url" target="_blank" class="link">{{ row.req_no || '查看' }}</a>
            <span v-else>{{ row.req_no || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column prop="owner" label="责任人" width="90" />
        <el-table-column prop="priority" label="优先级" width="80" />
        <el-table-column v-for="c in PROG_COLS" :key="c.key" :label="c.label" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="progType(row[c.key])" effect="plain">{{ row[c.key] || '—' }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 下钻：问题单 -->
    <el-dialog v-model="issueVisible" :title="`问题单 · ${drillName}`" width="900px">
      <el-table :data="issueRows" border stripe max-height="60vh" v-loading="issueLoading">
        <el-table-column prop="issue_id" label="编号" width="130" />
        <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
        <el-table-column prop="owner" label="责任人" width="90" />
        <el-table-column prop="severity" label="严重度" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="sevType(row.severity)" effect="plain">{{ row.severity || '—' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="progress" label="进展" min-width="160" show-overflow-tooltip />
        <el-table-column prop="version" label="版本" width="120" show-overflow-tooltip />
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Plus, QuestionFilled, Refresh } from '@element-plus/icons-vue'
import { domainApi, resourceGroupApi } from '../api'
import RichTextEditor from '../components/RichTextEditor.vue'

const PROG_COLS = [
  { key: 'progress_walkthrough', label: '需求串讲' },
  { key: 'progress_reverse', label: '反串讲' },
  { key: 'progress_stc', label: 'STC' },
  { key: 'progress_coding', label: '编码' },
  { key: 'progress_bbit', label: 'BBIT' },
  { key: 'progress_clarify', label: '转测澄清' },
]
const PRIORITIES = ['高', '中', '低']
const STATUSES = ['OPEN', 'CLOSED', '挂起']

const activeTab = ref('overview')
const data = reactive({ iteration_label: '', rows: [], iterations: [] })
const issueMeta = reactive({ available: false, file_mtime: null, note: '' })
const loading = ref(false)
const showHidden = ref(false)
// 需求口径：'' = 当前进行中迭代；'2026-6' = 指定年度迭代月份
const monthKey = ref('')

function parseKey(k) {
  if (!k) return {}
  const [y, m] = k.split('-')
  return { year: Number(y), month: Number(m) }
}
function statusSuffix(it) {
  return { in_progress: '（进行中）', done: '（已完成）', planning: '（计划）' }[it.status] || ''
}
function fmtDate(d) {
  if (!d) return ''
  const dt = new Date(d)
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`
}

function sevType(s) {
  return { '致命': 'danger', '严重': 'danger', '一般': 'warning', '提示': 'info' }[s] || 'info'
}
function progType(v) {
  return {
    '已完成': 'success', '进行中': 'warning', '已延期': 'danger',
    '已变更': 'warning', '未开始': 'info', '不涉及': 'info',
  }[v] || 'info'
}
function prioType(p) {
  return { '高': 'danger', '中': 'warning', '低': 'info' }[p] || 'info'
}
function statusType(s) {
  // OPEN 橙、CLOSED 绿、挂起 灰
  return { 'OPEN': 'warning', 'CLOSED': 'success', '挂起': 'info' }[s] || 'info'
}
function riskRowClass(row) {
  if (row.status === 'CLOSED') return 'risk-closed'
  if (row.status === '挂起') return 'risk-suspended'
  return ''
}

async function load() {
  loading.value = true
  try {
    const { data: d } = await domainApi.list({ ...parseKey(monthKey.value), include_hidden: showHidden.value })
    data.iteration_label = d.iteration_label
    data.rows = d.rows
    data.iterations = d.iterations || []
    const first = d.rows.find((r) => r.issue_summary)?.issue_summary
    issueMeta.available = !!first?.available
    issueMeta.file_mtime = first?.file_mtime || null
    issueMeta.note = first?.note || ''
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

async function hideDomain(row) {
  await ElMessageBox.confirm(`将「${row.name}」从领域管理移除？（不影响组织架构，可在"显示已隐藏"里恢复）`, '提示', { type: 'warning' })
  try {
    await domainApi.setVisibility(row.group_id, true)
    ElMessage.success('已移除')
    load()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '操作失败') }
}
async function restoreDomain(row) {
  try {
    await domainApi.setVisibility(row.group_id, false)
    ElMessage.success('已恢复')
    load()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '操作失败') }
}

// ── 领域内容编辑 ──────────────────────────────────────
const editVisible = ref(false)
const editRow = ref(null)
const saving = ref(false)
const editForm = reactive({ recent_work: '', risks: [], version: 0 })

function openEdit(row) {
  editRow.value = row
  editForm.recent_work = row.recent_work || ''
  editForm.risks = (row.risks || []).map((r) => ({ ...r }))
  editForm.version = row.version || 0
  editVisible.value = true
}
function addRisk() {
  editForm.risks.push({ content: '', type: '风险', status: '' })
}
async function saveEdit() {
  saving.value = true
  try {
    await domainApi.updateContent(editRow.value.group_id, {
      recent_work: editForm.recent_work,
      risks: editForm.risks,
      version: editForm.version,
    })
    ElMessage.success('已保存')
    editVisible.value = false
    load()
  } catch (e) {
    if (e.response?.status === 409) {
      load()
      editVisible.value = false
    } else {
      ElMessage.error(e.response?.data?.detail || '保存失败')
    }
  } finally {
    saving.value = false
  }
}

// ── 事务与风险跟踪 ──────────────────────────────────────
const riskRows = ref([])
const riskLoading = ref(false)
const showDoneRisks = ref(true)
const domainOptions = ref([])
const riskVisible = ref(false)
const riskSaving = ref(false)
const riskForm = reactive(blankRisk())

function blankRisk() {
  return {
    id: null, version: 0, content: '', priority: '中', progress: '',
    domain_id: null, planned_close_date: null, status: 'OPEN',
  }
}
async function loadRisks() {
  riskLoading.value = true
  try {
    const { data: rows } = await domainApi.riskList({ include_done: showDoneRisks.value })
    riskRows.value = rows
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    riskLoading.value = false
  }
}
async function loadDomainOptions() {
  try {
    const { data } = await resourceGroupApi.list({ kind: 'pl' })
    domainOptions.value = data
  } catch { /* 下拉为空不阻塞 */ }
}
function openRisk(row) {
  Object.assign(riskForm, blankRisk(), row ? { ...row } : {})
  riskVisible.value = true
}
async function saveRisk() {
  if (!riskForm.content.trim()) { ElMessage.warning('内容不能为空'); return }
  riskSaving.value = true
  try {
    if (riskForm.id) await domainApi.riskUpdate(riskForm.id, riskForm)
    else await domainApi.riskCreate(riskForm)
    ElMessage.success('已保存')
    riskVisible.value = false
    loadRisks()
  } catch (e) {
    if (e.response?.status === 409) { riskVisible.value = false; loadRisks() }
    else ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    riskSaving.value = false
  }
}
async function delRisk(row) {
  await ElMessageBox.confirm('确认删除该条事务/风险吗？', '提示', { type: 'warning' })
  try {
    await domainApi.riskRemove(row.id)
    ElMessage.success('已删除')
    loadRisks()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '删除失败') }
}

// ── 下钻 ──────────────────────────────────────────────
const drillName = ref('')
const reqVisible = ref(false)
const reqLoading = ref(false)
const reqRows = ref([])
const issueVisible = ref(false)
const issueLoading = ref(false)
const issueRows = ref([])

async function openReq(row) {
  drillName.value = row.name
  reqVisible.value = true
  reqLoading.value = true
  reqRows.value = []
  try {
    const { data: rows } = await domainApi.requirements(row.group_id, parseKey(monthKey.value))
    reqRows.value = rows
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    reqLoading.value = false
  }
}
async function openIssues(row) {
  drillName.value = row.name
  issueVisible.value = true
  issueLoading.value = true
  issueRows.value = []
  try {
    const { data: res } = await domainApi.issues(row.group_id)
    issueRows.value = res.rows || []
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    issueLoading.value = false
  }
}

onMounted(() => { load(); loadRisks(); loadDomainOptions() })
</script>

<style scoped>
.domain-page { padding: 4px; }
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.head-left { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.head-right { display: flex; align-items: center; gap: 12px; }
.muted { color: #909399; font-size: 13px; }
.domain-name { font-weight: 600; display: flex; align-items: center; gap: 6px; }
.domain-meta { display: flex; align-items: center; gap: 6px; margin-top: 4px; flex-wrap: wrap; }
.cell-clickable { cursor: pointer; }
.cell-clickable:hover { color: #409EFF; }
.sum-line { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.sev-line { margin-top: 4px; display: flex; gap: 4px; flex-wrap: wrap; }
.score-sep { color: #c0c4cc; margin: 0 2px; }
.issue-score { color: #e6a23c; }
.hdr-help { font-size: 13px; color: #909399; vertical-align: -1px; cursor: help; }
.prio-line { margin-top: 4px; }
.prio { color: #909399; font-size: 12px; margin-right: 8px; }
.rich-cell {
  max-height: 96px;
  overflow: auto;
  font-size: 13px;
  line-height: 1.5;
}
.risk-list { display: flex; flex-direction: column; gap: 4px; }
.risk-item { display: flex; align-items: baseline; gap: 6px; font-size: 13px; }
.risk-content { flex: 1; }
.edit-section-title {
  font-weight: 600;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.risk-edit-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.link, a.link { color: #409EFF; text-decoration: none; }
/* 已隐藏领域行：淡化 */
.domain-table :deep(.hidden-row) { background: #fafafa; color: #909399; }
/* 事务风险：CLOSED 浅绿、挂起 浅灰 */
:deep(.risk-closed) td.el-table__cell { background: #f0f9eb !important; }
:deep(.risk-suspended) td.el-table__cell { background: #f4f4f5 !important; }
</style>
