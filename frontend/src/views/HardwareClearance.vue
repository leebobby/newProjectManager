<template>
  <div class="hw-page">
    <el-card shadow="never">
      <!-- ── 工具栏 ─────────────────────────────────── -->
      <div class="toolbar">
        <el-tag v-if="focusedMachine" type="warning" size="small" closable class="machine-filter-tag" @close="filterMachineId = null">
          仅看机台：{{ focusedMachine.machine_id }}（{{ focusedMachine.battlefield }}）
        </el-tag>
        <el-select v-model="filterCustomerId" placeholder="按战场筛选机台列" clearable filterable size="small" style="width:200px" :disabled="!!filterMachineId">
          <el-option v-for="b in battlefieldOptions" :key="b.customer_id" :label="b.battlefield" :value="b.customer_id" />
        </el-select>
        <el-input v-model="q" placeholder="搜索问题单 / 简述 / 部件 / 进展" clearable size="small" style="width:230px" :prefix-icon="Search" />

        <div class="toolbar-right">
          <span class="muted">共 {{ filteredRows.length }} 行 · {{ visibleMachines.length }} 台机台列</span>
          <el-button size="small" :type="editMode ? 'warning' : 'primary'" :icon="editMode ? Unlock : EditPen" @click="editMode = !editMode">
            {{ editMode ? '退出编辑' : '进入编辑' }}
          </el-button>
          <el-button size="small" :icon="Plus" :disabled="!editMode" @click="addRow">新增一行</el-button>
          <el-button size="small" text :icon="Document" @click="onImportTemplate">模板</el-button>
          <el-upload v-if="editMode" :auto-upload="false" :show-file-list="false" accept=".xlsx" :on-change="onImport">
            <el-button size="small" :icon="Upload" :loading="importing">导入</el-button>
          </el-upload>
          <el-button size="small" :icon="Download" :loading="exporting" @click="onExport">导出</el-button>
          <el-button v-if="isAdmin" size="small" :icon="Setting" @click="openConfig">配置</el-button>
        </div>
      </div>

      <!-- ── 主表（固定列 + 尾部机台列，横向滚动）─────────── -->
      <el-table :data="filteredRows" v-loading="loading" border stripe size="small"
                :row-class-name="rowClass" max-height="calc(100vh - 260px)">
        <el-table-column type="index" label="编号" width="56" align="center" fixed="left" />

        <!-- 固定列 + 自定义列，按 orderedColumns 交织（自定义列可插入任意固定列之间）-->
        <el-table-column v-for="c in orderedColumns" :key="c.uid" :label="c.label"
                         :width="c.width" :min-width="c.minWidth" :align="c.align"
                         :header-align="c.headerAlign" :class-name="c.className">
          <template #default="{ row }">
            <FixedCell v-if="c.type === 'fixed'" :col="c.def" :row="row"
                       :users="users" :groups="groups" :issue-sources="issueSources"
                       @save="(patch) => save(row, patch)" />
            <ExtraCell v-else :col="c.def" :row="row" @save="(k, v) => saveExtra(row, k, v)" />
          </template>
        </el-table-column>

        <!-- 动态机台列 -->
        <el-table-column v-for="m in visibleMachines" :key="m.id" :label="m.machine_id" width="112" align="center" class-name="machine-col">
          <template #header>
            <router-link v-if="m.customer_id" :to="`/customers/${m.customer_id}?machine=${m.id}`" class="machine-link">{{ m.machine_id }}</router-link>
            <span v-else>{{ m.machine_id }}</span>
          </template>
          <template #default="{ row }">
            <el-select v-if="editMode" :model-value="cellVal(row, m.id)" size="small" clearable placeholder="—"
                       @change="(v) => saveCell(row, m.id, v)">
              <el-option v-for="o in optionsWith(cellOptions, cellVal(row, m.id))" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else class="status-chip" :class="{ empty: !cellVal(row, m.id) }" :style="chipStyle(cellVal(row, m.id))">
              {{ cellVal(row, m.id) || '—' }}
            </span>
          </template>
        </el-table-column>

        <el-table-column v-if="isAdmin && editMode" label="操作" width="60" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" :icon="Delete" @click="onDelete(row)" />
          </template>
        </el-table-column>

        <template #empty>
          <div class="empty-hint">暂无硬件问题，点「新增一行」开始，或用「导入」批量导入。</div>
        </template>
      </el-table>

      <div class="legend muted">
        机台列表头可点击跳转到对应机台详情；单元格清零状态与「问题来源」的下拉选项在
        <template v-if="isAdmin"><el-link type="primary" @click="openConfig">配置</el-link></template>
        <template v-else>「配置」（管理员）</template>
        里维护。
      </div>
    </el-card>

    <!-- ── 管理员配置弹窗 ─────────────────────────────── -->
    <el-dialog v-model="cfgVisible" title="硬件问题清零 · 列与选项配置" width="820px">
      <el-form label-position="top">
        <el-form-item label="问题来源选项（每行一个）">
          <el-input v-model="cfgForm.sources" type="textarea" :rows="5" placeholder="来料不良&#10;设计缺陷&#10;工艺问题" />
        </el-form-item>
        <el-form-item label="机台清零状态选项（每行一个）">
          <el-input v-model="cfgForm.cellOptions" type="textarea" :rows="5" placeholder="已清零&#10;未清零&#10;不涉及&#10;已发货待验证" />
        </el-form-item>
        <el-form-item label="状态颜色（可选，用于单元格着色）">
          <div class="color-map">
            <div v-for="opt in cfgCellOpts" :key="opt" class="color-row">
              <span class="status-chip" :style="cfgColors[opt] ? { backgroundColor: cfgColors[opt], color: '#fff', borderColor: cfgColors[opt] } : {}">{{ opt }}</span>
              <el-color-picker v-model="cfgColors[opt]" size="small" />
              <el-button v-if="cfgColors[opt]" link size="small" @click="cfgColors[opt] = ''">清除</el-button>
            </div>
            <div v-if="!cfgCellOpts.length" class="muted">先在上方填写状态选项，再为每个状态配色</div>
          </div>
        </el-form-item>

        <el-form-item label="自定义列（可增删、选类型、选择插入位置、排序）">
          <div class="col-defs">
            <div v-for="(col, i) in cfgColumns" :key="col.key" class="col-def-row">
              <el-input v-model="col.label" size="small" placeholder="列名" style="width:120px" />
              <el-select v-model="col.type" size="small" style="width:92px">
                <el-option label="文本" value="text" />
                <el-option label="链接" value="link" />
                <el-option label="下拉" value="select" />
                <el-option label="日期" value="date" />
                <el-option label="数字" value="number" />
              </el-select>
              <el-select v-model="col.after" size="small" style="width:160px" placeholder="插入位置">
                <el-option v-for="p in positionOptions" :key="p.value" :label="p.label" :value="p.value" />
              </el-select>
              <el-input v-if="col.type === 'select'" v-model="col.optionsText" size="small"
                        placeholder="下拉选项，逗号/换行分隔" style="flex:1; min-width:120px" />
              <span v-else class="col-def-spacer" />
              <el-button link :icon="Top" :disabled="i === 0" title="上移" @click="moveCol(i, -1)" />
              <el-button link :icon="Bottom" :disabled="i === cfgColumns.length - 1" title="下移" @click="moveCol(i, 1)" />
              <el-button link type="danger" :icon="Delete" title="删除列" @click="removeCol(i)" />
            </div>
            <el-button size="small" :icon="Plus" @click="addCol">新增列</el-button>
            <div v-if="!cfgColumns.length" class="muted">还没有自定义列，点「新增列」添加</div>
            <div v-else class="muted col-hint">「插入位置」决定该列出现在哪个固定列之后；同一位置有多列时按上下顺序排列。</div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cfgVisible = false">取消</el-button>
        <el-button type="primary" :loading="cfgSaving" @click="saveConfig">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onActivated, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { ElButton, ElDatePicker, ElInput, ElMessage, ElMessageBox, ElOption, ElSelect } from 'element-plus'
import { Bottom, Delete, Document, Download, EditPen, Plus, Search, Setting, Top, TopRight, Unlock, Upload } from '@element-plus/icons-vue'
import { configApi, customerStatusApi, downloadBlob, hardwareIssueApi, resourceGroupApi, userApi } from '../api'
import { auth } from '../store/auth'
import { naturalCompare } from '../utils/format'

const props = defineProps({
  // 从客户总览"硬件清零"格跳过来时，聚焦到某台机台（machine_status_id）
  focusMachine: { type: [Number, String], default: null },
})

const isAdmin = auth.isAdmin

const filterMachineId = ref(props.focusMachine != null ? Number(props.focusMachine) : null)
watch(() => props.focusMachine, (v) => {
  filterMachineId.value = v != null ? Number(v) : null
  q.value = ''
})

const rows = ref([])
const machines = ref([])
const users = ref([])
const groups = ref([])
const issueSources = ref([])
const cellOptions = ref([])
const loading = ref(false)
const exporting = ref(false)
const importing = ref(false)
const editMode = ref(false)        // 默认只读；进入编辑才可改，防止误改
const cellColors = ref({})         // {清零状态: 颜色}，用于机台格着色
const extraColumns = ref([])       // 自定义列定义 [{key,label,type,options}]
const filterCustomerId = ref(null)
const q = ref('')

// 状态颜色的出厂默认（用户未配置时的建议值）
const DEFAULT_CELL_COLORS = { 已清零: '#67c23a', 未清零: '#e6a23c', 不涉及: '#909399' }

// ── 内联可编辑单元格（文本 / 多行）──
const EditableCell = defineComponent({
  props: {
    value: String,
    placeholder: { type: String, default: '点击填写' },
    multiline: { type: Boolean, default: false },
  },
  emits: ['save'],
  setup(props, { emit }) {
    const editing = ref(false)
    const draft = ref('')
    const start = () => {
      if (!editMode.value) return          // 只读模式不进入编辑
      draft.value = props.value || ''
      editing.value = true
    }
    const commit = () => {
      editing.value = false
      if (draft.value !== (props.value || '')) emit('save', draft.value)
    }
    return () => editing.value
      ? h(ElInput, {
          modelValue: draft.value, size: 'small', autofocus: true,
          type: props.multiline ? 'textarea' : 'text',
          autosize: props.multiline ? { minRows: 1, maxRows: 6 } : false,
          'onUpdate:modelValue': (v) => { draft.value = v },
          onBlur: commit,
          onKeyup: (e) => {
            if (e.key === 'Enter' && !props.multiline) commit()
            if (e.key === 'Escape') editing.value = false
          },
        })
      : h('span', {
          class: [
            props.value ? 'cell-text' : 'cell-text muted',
            props.multiline ? 'cell-multiline' : '',
            editMode.value ? '' : 'cell-readonly',
          ],
          onClick: start,
        }, props.value || (editMode.value ? props.placeholder : '—'))
  },
})

// 固定列定义：key 与后端 _FIXED_EXPORT 的锚点一致，供自定义列 after 定位。
// kind 决定单元格渲染方式；text 类 key 即 row 上的字段名。
const FIXED_COLS = [
  { key: 'source', label: '来源', kind: 'text', minWidth: 110 },
  { key: 'issue_ref', label: '问题单号', kind: 'text', minWidth: 130 },
  { key: 'summary', label: '问题简述', kind: 'text', multiline: true, minWidth: 200 },
  { key: 'replaced_part', label: '更换部件', kind: 'text', minWidth: 130 },
  { key: 'issue_source', label: '问题来源', kind: 'issue_source', width: 130, align: 'center' },
  { key: 'group', label: '责任领域', kind: 'group', width: 130, align: 'center' },
  { key: 'owner', label: '责任人', kind: 'owner', width: 130, align: 'center' },
  { key: 'ccb_conclusion', label: 'CCB清零结论', kind: 'text', multiline: true, minWidth: 160 },
  { key: 'ship_clear_from', label: '从#N发货清零', kind: 'text', width: 120, align: 'center' },
  { key: 'clear_progress', label: '清零进展', kind: 'text', multiline: true, minWidth: 160 },
  { key: 'sop_status', label: 'SOP情况', kind: 'text', multiline: true, minWidth: 140 },
]

// 「插入位置」下拉选项：最前 / 各固定列之后 / 机台列前（默认）
const positionOptions = [
  { value: '__start__', label: '表格最前' },
  ...FIXED_COLS.map(fc => ({ value: fc.key, label: `「${fc.label}」后` })),
  { value: '__end__', label: '机台列前（默认）' },
]

// ── 固定列单元格（按 kind 切换：文本 / 问题来源 / 责任领域 / 责任人）──
const FixedCell = defineComponent({
  props: { col: Object, row: Object, users: Array, groups: Array, issueSources: Array },
  emits: ['save'],
  setup(props, { emit }) {
    return () => {
      const { col, row } = props
      if (col.kind === 'issue_source') {
        return h(ElSelect, {
          modelValue: row.issue_source, size: 'small', clearable: true, filterable: true,
          placeholder: '—', disabled: !editMode.value,
          onChange: (v) => emit('save', { issue_source: v || '' }),
        }, () => optionsWith(props.issueSources, row.issue_source).map(o => h(ElOption, { key: o, label: o, value: o })))
      }
      if (col.kind === 'group') {
        return h(ElSelect, {
          modelValue: row.group_id, size: 'small', clearable: true, filterable: true,
          placeholder: '—', disabled: !editMode.value,
          onChange: (v) => emit('save', { group_id: v ?? null }),
        }, () => props.groups.map(g => h(ElOption, { key: g.id, label: g.name, value: g.id })))
      }
      if (col.kind === 'owner') {
        return h(ElSelect, {
          modelValue: row.owner_user_id, size: 'small', clearable: true, filterable: true,
          placeholder: '未指派', disabled: !editMode.value,
          onChange: (v) => emit('save', { owner_user_id: v ?? null }),
        }, () => props.users.map(u => h(ElOption, { key: u.id, label: u.full_name || u.username, value: u.id })))
      }
      return h(EditableCell, {
        value: row[col.key], multiline: !!col.multiline, placeholder: '—',
        onSave: (v) => emit('save', { [col.key]: v }),
      })
    }
  },
})

// ── 自定义列单元格（按 type：下拉 / 日期 / 链接 / 数字 / 文本）；emit('save', key, val) ──
const ExtraCell = defineComponent({
  props: { col: Object, row: Object },
  emits: ['save'],
  setup(props, { emit }) {
    return () => {
      const { col, row } = props
      const cur = extraVal(row, col.key)
      if (col.type === 'select') {
        return h(ElSelect, {
          modelValue: cur, size: 'small', clearable: true, disabled: !editMode.value, placeholder: '—',
          onChange: (v) => emit('save', col.key, v || ''),
        }, () => (col.options || []).map(o => h(ElOption, { key: o, label: o, value: o })))
      }
      if (col.type === 'date') {
        return h(ElDatePicker, {
          modelValue: cur, type: 'date', size: 'small', valueFormat: 'YYYY-MM-DD',
          disabled: !editMode.value, placeholder: '—', style: 'width:130px',
          'onUpdate:modelValue': (v) => emit('save', col.key, v || ''),
        })
      }
      if (col.type === 'link') {
        return h('div', { class: 'extra-link' }, [
          h(EditableCell, { value: cur, placeholder: '—', onSave: (v) => emit('save', col.key, v) }),
          cur ? h(ElButton, {
            link: true, type: 'primary', size: 'small', icon: TopRight, title: '打开链接',
            onClick: () => openLink(cur),
          }) : null,
        ])
      }
      return h(EditableCell, {
        value: cur, placeholder: '—',
        onSave: (v) => emit('save', col.key, col.type === 'number' ? normNum(v) : v),
      })
    }
  },
})

// 固定列 + 自定义列交织成有序列，供表格单个 v-for 渲染；自定义列按 after 锚点插入
const orderedColumns = computed(() => {
  const byAnchor = {}
  for (const col of extraColumns.value) {
    const a = col.after || '__end__'
    ;(byAnchor[a] = byAnchor[a] || []).push(col)
  }
  const seen = new Set()
  const extraItem = (c) => {
    seen.add(c.key)
    return {
      uid: 'x:' + c.key, type: 'extra', def: c, label: c.label,
      minWidth: c.type === 'select' ? 120 : 140, headerAlign: 'center', className: 'extra-col',
    }
  }
  const fixedItem = (fc) => ({
    uid: 'f:' + fc.key, type: 'fixed', def: fc, label: fc.label,
    width: fc.width, minWidth: fc.minWidth, align: fc.align,
  })
  const out = []
  for (const c of byAnchor.__start__ || []) out.push(extraItem(c))
  for (const fc of FIXED_COLS) {
    out.push(fixedItem(fc))
    for (const c of byAnchor[fc.key] || []) out.push(extraItem(c))
  }
  for (const c of byAnchor.__end__ || []) out.push(extraItem(c))
  // after 指向已失效锚点的列兜底放末尾，避免丢列
  for (const c of extraColumns.value) if (!seen.has(c.key)) out.push(extraItem(c))
  return out
})

// 战场下拉：从机台去重派生，保证与实际机台一致
const battlefieldOptions = computed(() => {
  const seen = new Map()
  for (const m of machines.value) {
    if (m.customer_id && !seen.has(m.customer_id)) seen.set(m.customer_id, m.battlefield || '')
  }
  return [...seen.entries()].map(([customer_id, battlefield]) => ({ customer_id, battlefield }))
    .sort((a, b) => naturalCompare(a.battlefield, b.battlefield))
})

// 聚焦的机台（从总览跳来）
const focusedMachine = computed(() => machines.value.find(m => m.id === filterMachineId.value) || null)

// 可见机台列：聚焦某机台→只显示该列；否则选了战场→只显示该战场机台
const visibleMachines = computed(() => {
  if (filterMachineId.value) {
    const m = machines.value.find(x => x.id === filterMachineId.value)
    return m ? [m] : []
  }
  let ms = machines.value.slice()
  if (filterCustomerId.value) ms = ms.filter(m => m.customer_id === filterCustomerId.value)
  return ms.sort((a, b) => naturalCompare(a.battlefield || '', b.battlefield || '') || naturalCompare(a.machine_id, b.machine_id))
})

const filteredRows = computed(() => {
  let rs = rows.value
  // 聚焦机台时，只看该机台有清零状态的行（即"对应机台的情况"）
  if (filterMachineId.value) {
    const key = String(filterMachineId.value)
    rs = rs.filter(r => r.machine_cells && r.machine_cells[key])
  }
  if (!q.value.trim()) return rs
  const kw = q.value.trim().toLowerCase()
  return rs.filter(r =>
    (r.issue_ref || '').toLowerCase().includes(kw)
    || (r.summary || '').toLowerCase().includes(kw)
    || (r.replaced_part || '').toLowerCase().includes(kw)
    || (r.source || '').toLowerCase().includes(kw)
    || (r.clear_progress || '').toLowerCase().includes(kw)
    || (r.owner_display || '').toLowerCase().includes(kw))
})

function cellVal(row, machineId) {
  return (row.machine_cells && row.machine_cells[String(machineId)]) || ''
}
// 已有值但不在选项里时补进下拉，避免旧值显示不出来
function optionsWith(list, cur) {
  const arr = list.value ? list.value : list
  if (cur && !arr.includes(cur)) return [cur, ...arr]
  return arr
}

function rowClass({ row }) {
  // 全部机台格都「已清零」或含"清零"字样时整行浅绿，提示已收尾
  const vals = Object.values(row.machine_cells || {})
  if (vals.length && vals.every(v => v && v.includes('清零') && !v.includes('未'))) return 'row-done'
  return ''
}

async function reload(silent = false) {
  // silent：已有数据时后台刷新，不转圈不清空，保证 KeepAlive 切回来秒显
  if (!silent) loading.value = true
  try {
    const { data } = await hardwareIssueApi.list()
    rows.value = data
  } catch (e) {
    if (!silent) ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    if (!silent) loading.value = false
  }
}

async function save(row, patch) {
  try {
    const { data } = await hardwareIssueApi.update(row.id, { version: row.version, ...patch })
    const i = rows.value.findIndex(r => r.id === row.id)
    if (i >= 0) rows.value[i] = data
  } catch (e) {
    // 乐观锁冲突：他人已改同一行，明确提示并拉最新，避免静默覆盖
    if (e.response?.status === 409) ElMessage.warning('该行已被他人修改，已刷新为最新数据，请重新编辑')
    else ElMessage.error(e.response?.data?.detail || '保存失败')
    reload()
  }
}

// 机台格按清零状态着色（读取模式显示彩色胶囊）
function chipStyle(val) {
  const c = val && cellColors.value[val]
  if (!c) return {}
  return { backgroundColor: c, color: '#fff', borderColor: c }
}

function saveCell(row, machineId, val) {
  const cells = { ...(row.machine_cells || {}) }
  if (val) cells[String(machineId)] = val
  else delete cells[String(machineId)]
  save(row, { machine_cells: cells })
}

// ── 自定义列取值/保存 ──
function extraVal(row, key) {
  return (row.extra_fields && row.extra_fields[key]) || ''
}
function saveExtra(row, key, val) {
  const extra = { ...(row.extra_fields || {}) }
  if (val) extra[key] = val
  else delete extra[key]
  save(row, { extra_fields: extra })
}
function normNum(v) {
  const n = parseInt(v, 10)
  return Number.isNaN(n) ? '' : String(Math.max(0, n))
}
function openLink(url) {
  const u = /^https?:\/\//i.test(url) ? url : `http://${url}`
  window.open(u, '_blank')
}

async function addRow() {
  try {
    const { data } = await hardwareIssueApi.create({})
    rows.value.push(data)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '新增失败')
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除「${row.summary || '该行'}」吗？`, '提示', { type: 'warning' })
  } catch { return }
  try {
    await hardwareIssueApi.remove(row.id)
    rows.value = rows.value.filter(r => r.id !== row.id)
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

async function onExport() {
  exporting.value = true
  try {
    const resp = await hardwareIssueApi.exportXlsx()
    const ts = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19)
    downloadBlob(resp.data, `硬件问题清零_${ts}.xlsx`)
    ElMessage.success('已导出')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导出失败')
  } finally {
    exporting.value = false
  }
}

async function onImportTemplate() {
  try {
    const resp = await hardwareIssueApi.importTemplate()
    downloadBlob(resp.data, '硬件问题清零_导入模板.xlsx')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '模板下载失败')
  }
}

async function onImport(uploadFile) {
  const file = uploadFile?.raw
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.xlsx')) {
    ElMessage.error('仅支持 .xlsx 文件')
    return
  }
  importing.value = true
  try {
    const { data } = await hardwareIssueApi.importXlsx(file)
    await reload()
    const errs = data.errors || []
    if (errs.length) {
      ElMessageBox.alert(
        `成功导入 <b>${data.created}</b> 行，另有 <b>${errs.length}</b> 处未导入：<br><br>`
          + errs.map(e => `· ${e}`).join('<br>'),
        '导入完成（部分未成功）',
        { type: 'warning', dangerouslyUseHTMLString: true, customClass: 'hw-import-box' },
      )
    } else {
      ElMessage.success(`成功导入 ${data.created} 行`)
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导入失败，请检查文件格式')
  } finally {
    importing.value = false
  }
}

// ── 配置 ──
const cfgVisible = ref(false)
const cfgSaving = ref(false)
const cfgForm = ref({ sources: '', cellOptions: '' })
const cfgColors = ref({})   // 弹窗内编辑中的 {状态: 颜色}
const cfgColumns = ref([])  // 弹窗内编辑中的自定义列 [{key,label,type,optionsText}]

// 弹窗里根据"状态选项"文本实时解析出的选项列表，用来渲染配色行
const cfgCellOpts = computed(() => splitLines(cfgForm.value.cellOptions))

function addCol() {
  cfgColumns.value.push({ key: 'c' + Date.now().toString(36), label: '新列', type: 'text', after: '__end__', optionsText: '' })
}
function moveCol(i, dir) {
  const j = i + dir
  if (j < 0 || j >= cfgColumns.value.length) return
  const arr = cfgColumns.value
  ;[arr[i], arr[j]] = [arr[j], arr[i]]
}
function removeCol(i) {
  cfgColumns.value.splice(i, 1)
}

function openConfig() {
  cfgForm.value = {
    sources: (issueSources.value || []).join('\n'),
    cellOptions: (cellOptions.value || []).join('\n'),
  }
  // 未配过色的常见状态给出默认建议色，配过的沿用
  cfgColors.value = { ...DEFAULT_CELL_COLORS, ...(cellColors.value || {}) }
  // 深拷贝列定义，options 数组 → 文本便于编辑
  cfgColumns.value = (extraColumns.value || []).map(c => ({
    key: c.key, label: c.label, type: c.type || 'text', after: c.after || '__end__',
    optionsText: (c.options || []).join('\n'),
  }))
  cfgVisible.value = true
}

function splitLines(s) {
  return (s || '').split(/[\n;；,，]/).map(x => x.trim()).filter(Boolean)
}

async function saveConfig() {
  cfgSaving.value = true
  try {
    const sources = splitLines(cfgForm.value.sources)
    const cells = splitLines(cfgForm.value.cellOptions)
    // 只保留当前仍存在的选项的颜色，避免删了选项残留脏色
    const colors = {}
    for (const opt of cells) {
      if (cfgColors.value[opt]) colors[opt] = cfgColors.value[opt]
    }
    // 自定义列：清洗（去掉空列名），select 类型把选项文本转数组
    const columns = cfgColumns.value
      .filter(c => (c.label || '').trim())
      .map(c => ({
        key: c.key, label: c.label.trim(), type: c.type || 'text', after: c.after || '__end__',
        options: c.type === 'select' ? splitLines(c.optionsText) : [],
      }))
    await configApi.save({
      hw_issue_sources: sources,
      hw_machine_cell_options: cells,
      hw_machine_cell_colors: colors,
      hw_extra_columns: columns,
    })
    issueSources.value = sources
    cellOptions.value = cells
    cellColors.value = colors
    extraColumns.value = columns
    cfgVisible.value = false
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    cfgSaving.value = false
  }
}

async function loadConfig() {
  try {
    const { data } = await configApi.get()
    issueSources.value = Array.isArray(data.hw_issue_sources) ? data.hw_issue_sources : []
    cellOptions.value = Array.isArray(data.hw_machine_cell_options) ? data.hw_machine_cell_options : []
    cellColors.value = (data.hw_machine_cell_colors && typeof data.hw_machine_cell_colors === 'object')
      ? data.hw_machine_cell_colors : {}
    extraColumns.value = Array.isArray(data.hw_extra_columns)
      ? data.hw_extra_columns.filter(c => c && c.key && c.label) : []
  } catch { /* 静默 */ }
}

onMounted(async () => {
  const [ms, u, g] = await Promise.allSettled([
    customerStatusApi.list(),
    userApi.options({ only_can_login: true }),
    resourceGroupApi.list({ kind: 'pl' }),
  ])
  if (ms.status === 'fulfilled') machines.value = ms.value.data
  if (u.status === 'fulfilled') users.value = u.value.data
  if (g.status === 'fulfilled') groups.value = g.value.data
  await Promise.all([loadConfig(), reload()])
})

// KeepAlive 切回来：旧数据先显示，后台静默刷新行 + 机台列（保持与总览增删同步）
let activatedOnce = false
onActivated(() => {
  if (!activatedOnce) { activatedOnce = true; return }  // 首次激活由 onMounted 负责
  reload(true)
  customerStatusApi.list().then(({ data }) => { machines.value = data }).catch(() => {})
})
</script>

<style scoped>
.hw-page { display: flex; flex-direction: column; gap: 14px; }
.toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.toolbar-right { display: flex; align-items: center; gap: 8px; margin-left: auto; }
.machine-filter-tag { margin-right: 2px; }
.muted { color: #909399; font-size: 13px; }
.empty-hint { color: #909399; padding: 24px 0; }
.legend { margin-top: 10px; font-size: 12px; }

:deep(.row-done td.el-table__cell) { background: #f0f9eb !important; }
:deep(.machine-col) { background: #fafcff; }
:deep(.machine-link) { color: #409eff; text-decoration: none; }
:deep(.machine-link:hover) { text-decoration: underline; }
:deep(.cell-text) { cursor: pointer; display: inline-block; min-height: 20px; min-width: 40px; }
:deep(.cell-text:hover) { color: #409eff; }
:deep(.cell-multiline) { white-space: pre-wrap; line-height: 1.5; }
/* 只读模式：不显示可编辑的手型/悬停高亮 */
:deep(.cell-readonly) { cursor: default; }
:deep(.cell-readonly:hover) { color: inherit; }

/* 机台清零状态胶囊 */
.status-chip {
  display: inline-block; padding: 2px 10px; border-radius: 10px;
  border: 1px solid #dcdfe6; font-size: 12px; line-height: 18px; color: #606266;
}
.status-chip.empty { border-color: transparent; color: #c0c4cc; }

/* 配置弹窗：状态配色 */
.color-map { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.color-row { display: flex; align-items: center; gap: 10px; }
.color-row .status-chip { min-width: 90px; text-align: center; }

/* 自定义列配置 */
.col-defs { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.col-def-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.col-def-spacer { flex: 1; }
.col-hint { margin-top: 2px; font-size: 12px; }
.extra-link { display: flex; align-items: center; gap: 2px; }
</style>
