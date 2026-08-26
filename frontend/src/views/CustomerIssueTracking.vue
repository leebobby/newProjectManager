<template>
  <div class="track-page">
    <!-- ── 统计卡 ─────────────────────────────────── -->
    <div class="stat-row">
      <div class="stat-card" :class="{ active: !filters.status && !filters.overdue_only && !filters.urgency }" @click="resetStatusFilter">
        <div class="stat-num">{{ stats.open }}</div><div class="stat-label">未闭环</div>
      </div>
      <div class="stat-card crit" :class="{ active: filters.urgency === '重要紧急' }" @click="toggleFilter('urgency', '重要紧急')">
        <div class="stat-num">{{ stats.critical }}</div><div class="stat-label">重要紧急</div>
      </div>
      <div class="stat-card over" :class="{ active: filters.overdue_only }" @click="toggleOverdue">
        <div class="stat-num">{{ stats.overdue }}</div><div class="stat-label">逾期未闭环</div>
      </div>
      <div class="stat-card hold" :class="{ active: filters.status === '挂起' }" @click="toggleFilter('status', '挂起')">
        <div class="stat-num">{{ stats.on_hold }}</div><div class="stat-label">挂起</div>
      </div>
      <div class="stat-card done" :class="{ active: filters.status === 'CLOSED' }" @click="toggleFilter('status', 'CLOSED')">
        <div class="stat-num">{{ stats.closed }}</div><div class="stat-label">已闭环</div>
      </div>
    </div>

    <el-card shadow="never">
      <!-- ── 筛选栏 ───────────────────────────────── -->
      <div class="filter-bar">
        <el-select v-model="filters.customer_id" placeholder="客户 / 战场" clearable size="small" style="width:160px">
          <el-option v-for="c in customers" :key="c.id" :label="c.display_name || c.code" :value="c.id" />
        </el-select>
        <el-select v-model="filters.urgency" placeholder="重要程度" clearable size="small" style="width:130px">
          <el-option v-for="u in URGENCIES" :key="u" :label="u" :value="u" />
        </el-select>
        <el-select v-model="filters.group_id" placeholder="责任领域" clearable filterable size="small" style="width:150px">
          <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
        </el-select>
        <el-select v-model="filters.status" placeholder="状态" clearable size="small" style="width:120px">
          <el-option v-for="s in STATUSES" :key="s" :label="s" :value="s" />
        </el-select>
        <el-select v-model="filters.owner_user_id" placeholder="责任人" clearable filterable size="small" style="width:140px">
          <el-option v-for="u in users" :key="u.id" :label="u.full_name || u.username" :value="u.id" />
        </el-select>
        <el-input v-model="filters.q" placeholder="搜索描述 / 问题单 / 机台 / 进展" clearable size="small" style="width:230px"
                  :prefix-icon="Search" />
        <el-checkbox v-model="includeClosed" size="small">含已闭环</el-checkbox>

        <div class="filter-right">
          <span class="muted">共 {{ filteredRows.length }} 条<span v-if="customerIssues.loading"> · 刷新中…</span></span>
          <el-button size="small" type="primary" :icon="Plus" @click="openCreate">新增</el-button>
          <el-button size="small" :icon="Refresh" :loading="customerIssues.loading" @click="reloadIssues">刷新</el-button>
          <el-button size="small" text :icon="Document" @click="onImportTemplate">模板</el-button>
          <el-upload :auto-upload="false" :show-file-list="false" accept=".xlsx" :on-change="onImport">
            <el-button size="small" :icon="Upload" :loading="importing">导入</el-button>
          </el-upload>
          <el-button size="small" :icon="Download" :loading="exporting" @click="onExport">导出 Excel</el-button>
        </div>
      </div>

      <!-- ── 主表 ─────────────────────────────────── -->
      <el-table :data="pagedRows" v-loading="!customerIssues.loaded && customerIssues.loading" border stripe size="small"
                :row-class-name="rowClass" max-height="calc(100vh - 360px)">
        <el-table-column type="index" :index="rowIndex" label="编号" width="60" align="center" />
        <el-table-column prop="battlefield" label="客户" width="120" show-overflow-tooltip />

        <el-table-column label="机台编号" width="110">
          <template #default="{ row }">
            <router-link v-if="row.customer_id && row.machine_id"
                         :to="`/customers/${row.customer_id}?machine=${row.machine_status_id}`" class="machine-link">
              {{ row.machine_id }}
            </router-link>
            <span v-else>{{ row.machine_id || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="问题单号" width="150">
          <template #default="{ row }">
            <LinkableCell :value="row.issue_ref" :to="issueRefLink(row.issue_ref)" placeholder="—"
                          @save="(v) => save(row, { issue_ref: v })" />
          </template>
        </el-table-column>

        <el-table-column label="关键问题描述" min-width="240">
          <template #default="{ row }">
            <EditableCell :value="row.description" @save="(v) => save(row, { description: v })" />
          </template>
        </el-table-column>

        <el-table-column label="责任人" width="130" align="center">
          <template #default="{ row }">
            <el-select :model-value="row.owner_user_id" size="small" clearable filterable :persistent="false"
                       placeholder="未指派" @change="(v) => save(row, { owner_user_id: v ?? null })">
              <el-option v-for="u in users" :key="u.id" :label="u.full_name || u.username" :value="u.id" />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column label="重要程度" width="118" align="center">
          <template #default="{ row }">
            <el-select :model-value="row.urgency" size="small" :persistent="false" @change="(v) => save(row, { urgency: v })">
              <el-option v-for="u in URGENCIES" :key="u" :label="u" :value="u" />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column label="提出时间" width="128" align="center">
          <template #default="{ row }">
            <DateCell :value="row.raised_at" @save="(v) => save(row, { raised_at: v })" />
          </template>
        </el-table-column>

        <el-table-column label="计划解决时间" width="132" align="center">
          <template #default="{ row }">
            <DateCell :value="row.due_date" :overdue="row.overdue" @save="(v) => save(row, { due_date: v })" />
          </template>
        </el-table-column>

        <el-table-column label="责任领域" width="130" align="center">
          <template #default="{ row }">
            <el-select :model-value="row.group_id" size="small" clearable filterable placeholder="—" :persistent="false"
                       @change="(v) => save(row, { group_id: v ?? null })">
              <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column label="问题进展" min-width="200">
          <template #default="{ row }">
            <EditableCell :value="row.progress_note" multiline placeholder="点击填写进展"
                          @save="(v) => save(row, { progress_note: v })" />
          </template>
        </el-table-column>

        <el-table-column label="状态" width="108" align="center" fixed="right">
          <template #default="{ row }">
            <el-select :model-value="row.status" size="small" :persistent="false" @change="(v) => save(row, { status: v })">
              <el-option v-for="s in STATUSES" :key="s" :label="s" :value="s" />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column label="分类专项" width="130" fixed="right">
          <template #default="{ row }">
            <EditableCell :value="row.category" placeholder="—" @save="(v) => save(row, { category: v })" />
          </template>
        </el-table-column>

        <el-table-column v-if="isAdmin" label="操作" width="60" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" :icon="Delete" @click="onDelete(row)" />
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[50, 100, 200, 500]"
          :total="filteredRows.length"
          layout="total, sizes, prev, pager, next, jumper"
          size="small"
        />
      </div>

      <div class="legend">
        <span><i class="dot d-open" />未闭环</span>
        <span><i class="dot d-hold" />挂起</span>
        <span><i class="dot d-done" />已闭环</span>
        <span><i class="dot d-over" />逾期</span>
        <span class="muted">此处新增要先选机台（条目始终挂在机台上）；在「客户面状态」总览的单元格里新增更快，那里机台是现成的。</span>
      </div>
    </el-card>

    <!-- 新增条目：条目始终挂在机台上（后端要 machine_status_id，customer_id 由它推导），
         所以这里必须先选客户再选机台——汇总页不像总览那样天然带着机台上下文。 -->
    <el-dialog v-model="createVisible" title="新增客户面条目" width="620px" :close-on-click-modal="false">
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="客户 / 战场" required>
          <el-select v-model="createForm.customer_id" filterable placeholder="选择客户" style="width: 100%"
                     @change="onCreateCustomerChange">
            <el-option v-for="c in customers" :key="c.id" :label="c.display_name || c.code" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="机台" required>
          <el-select v-model="createForm.machine_status_id" filterable :loading="machineLoading"
                     :placeholder="createForm.customer_id ? '选择机台' : '请先选客户'"
                     :disabled="!createForm.customer_id" style="width: 100%">
            <el-option v-for="m in machineOptions" :key="m.id"
                       :label="m.model ? `${m.machine_id}（${m.model}）` : m.machine_id" :value="m.id" />
          </el-select>
          <div v-if="createForm.customer_id && !machineLoading && !machineOptions.length" class="muted">
            该客户名下还没有机台，先去「客户面状态」建机台。
          </div>
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="createForm.kind">
            <el-radio-button v-for="k in KINDS" :key="k.value" :value="k.value">{{ k.label }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="描述" required>
          <el-input v-model="createForm.description" type="textarea" :rows="3" placeholder="关键问题 / 需求 / 事务的描述" />
        </el-form-item>
        <el-form-item label="问题单号">
          <el-input v-model="createForm.issue_ref" placeholder="选填" />
        </el-form-item>
        <el-form-item label="重要程度">
          <el-select v-model="createForm.urgency" style="width: 160px">
            <el-option v-for="u in URGENCIES" :key="u" :label="u" :value="u" />
          </el-select>
          <span class="muted" style="margin-left: 12px">状态</span>
          <el-select v-model="createForm.status" style="width: 130px; margin-left: 8px">
            <el-option v-for="st in STATUSES" :key="st" :label="st" :value="st" />
          </el-select>
        </el-form-item>
        <el-form-item label="责任人">
          <el-select v-model="createForm.owner_user_id" clearable filterable placeholder="选填" style="width: 100%">
            <el-option v-for="u in users" :key="u.id" :label="u.full_name || u.username" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="责任领域">
          <el-select v-model="createForm.group_id" clearable filterable placeholder="选填" style="width: 100%">
            <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="提出时间">
          <el-date-picker v-model="createForm.raised_at" type="date" value-format="YYYY-MM-DD" style="width: 170px" />
          <span class="muted" style="margin-left: 12px">计划解决</span>
          <el-date-picker v-model="createForm.due_date" type="date" value-format="YYYY-MM-DD"
                          style="width: 170px; margin-left: 8px" />
        </el-form-item>
        <el-form-item label="分类专项">
          <el-input v-model="createForm.category" placeholder="选填" />
        </el-form-item>
        <el-form-item label="问题进展">
          <el-input v-model="createForm.progress_note" type="textarea" :rows="2" placeholder="选填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, nextTick, onActivated, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ElDatePicker, ElIcon, ElInput, ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Document, Download, Edit, Plus, Refresh, Search, Upload } from '@element-plus/icons-vue'
import { customerApi, customerIssueApi, downloadBlob, resourceGroupApi, userApi } from '../api'
import { auth } from '../store/auth'
import {
  customerIssues, ensureIssues, reloadIssues, refreshIssues, removeIssue, upsertIssue,
} from '../store/customerIssues'

// 既可独立路由使用（?focus= 查询串），也可作为「客户面状态」页的内嵌 tab（focus prop）
const props = defineProps({
  focus: { type: Number, default: null },
})

const route = useRoute()
const isAdmin = auth.isAdmin

// 与后端 enums.py 保持一致
const URGENCIES = ['重要紧急', '重要', '一般']
const STATUSES = ['OPEN', 'CLOSED', '挂起']
// 与后端 enums.CUSTOMER_ISSUE_KINDS 一致。这张汇总表三类都显示，所以新增时也要能选：
// 只给「问题」一档的话，事务和需求就只能回总览页去建，等于没解决问题。
const KINDS = [
  { value: 'issue', label: '问题' },
  { value: 'demand', label: '需求' },
  { value: 'task', label: '事务' },
]
const STATUS_RANK = { OPEN: 0, 挂起: 1, CLOSED: 2 }
const URGENCY_RANK = { 重要紧急: 0, 重要: 1, 一般: 2 }

// 问题单号变链接：跳到「问题单管理」页（后续与版本联动会再细化落点）
function issueRefLink(ref) {
  return ref ? { path: '/issue-management', query: { q: ref } } : ''
}

// ── 内联组件：点击即改的文本单元格（支持多行）────────────
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
    const start = () => { draft.value = props.value || ''; editing.value = true }
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
          class: [props.value ? 'cell-text' : 'cell-text muted', props.multiline ? 'cell-multiline' : ''],
          onClick: start,
        }, props.value || props.placeholder)
  },
})

// ── 内联组件：有值显示为链接（可点跳转）+ 铅笔改；空值点击录入 ──
const LinkableCell = defineComponent({
  props: {
    value: String,
    to: { type: [String, Object], default: '' },
    placeholder: { type: String, default: '—' },
  },
  emits: ['save'],
  setup(props, { emit }) {
    const editing = ref(false)
    const draft = ref('')
    const start = () => { draft.value = props.value || ''; editing.value = true }
    const commit = () => {
      editing.value = false
      if (draft.value !== (props.value || '')) emit('save', draft.value)
    }
    return () => {
      if (editing.value) {
        return h(ElInput, {
          modelValue: draft.value, size: 'small', autofocus: true,
          'onUpdate:modelValue': (v) => { draft.value = v },
          onBlur: commit,
          onKeyup: (e) => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') editing.value = false },
        })
      }
      if (!props.value) {
        return h('span', { class: 'cell-text muted', onClick: start }, props.placeholder)
      }
      return h('span', { class: 'linkcell' }, [
        props.to
          ? h(RouterLink, { to: props.to, class: 'issue-link' }, () => props.value)
          : h('span', props.value),
        h(ElIcon, { class: 'edit-ico', title: '修改', onClick: start }, () => h(Edit)),
      ])
    }
  },
})

// ── 内联组件：点开才挂载的日期单元格 ──────────────────────────────
// el-date-picker 的面板是**立即渲染**的（它给 el-tooltip 传的 persistent 写死为真，
// 没有关掉的入口），一行两个日期列就是两个完整月历（各 40+ 个格子）。几百行一起渲染，
// 光日期面板就是几万个节点——这正是这张表卡的主因。所以这里退化成一个纯文本，
// 点下去才挂 el-date-picker，关掉面板就卸载。
// 下拉那几列不用这么做：el-select 支持 :persistent="false"，加上就不会预渲染选项了。
const DateCell = defineComponent({
  props: {
    value: String,
    overdue: { type: Boolean, default: false },
    placeholder: { type: String, default: '—' },
  },
  emits: ['save'],
  setup(props, { emit }) {
    const editing = ref(false)
    const picker = ref(null)
    const start = () => {
      editing.value = true
      // 挂上之后直接把面板弹出来，省掉「点一下出输入框、再点一下出日历」
      nextTick(() => {
        const el = picker.value
        if (el?.handleOpen) el.handleOpen()
        else el?.focus?.()
      })
    }
    return () => editing.value
      ? h(ElDatePicker, {
          ref: picker,
          modelValue: props.value || '',
          type: 'date', size: 'small', valueFormat: 'YYYY-MM-DD',
          placeholder: props.placeholder, style: 'width:112px',
          'onUpdate:modelValue': (v) => { emit('save', v || '') },
          // 面板关掉就卸载：留着不卸载等于又回到「每行常驻一个月历」
          onVisibleChange: (v) => { if (!v) editing.value = false },
        })
      : h('span', {
          class: ['cell-text', props.value ? '' : 'muted', props.overdue ? 'date-overdue' : ''],
          onClick: start,
        }, props.value || props.placeholder)
  },
})

const users = ref([])
const customers = ref([])
const groups = ref([])
const exporting = ref(false)
const importing = ref(false)
// 默认只看未闭环：这张表是用来推问题的，已闭环的是历史，勾上才显示。
// 导出也跟着这个开关走——导出的应当是屏幕上这一份。
const includeClosed = ref(false)

const filters = reactive({
  customer_id: null, urgency: null, group_id: null, status: null,
  owner_user_id: null, q: '', overdue_only: false,
})

// ── 新增条目 ────────────────────────────────────────────────────────────────
// 条目在库里始终挂在**机台**上（machine_status_id 是必填，customer_id 由它推导），
// 总览页天然带着机台上下文所以能一行搞定；汇总页没有，只能先选客户再选机台。
const createVisible = ref(false)
const creating = ref(false)
const machineLoading = ref(false)
const machineOptions = ref([])
// 客户 → 机台列表的缓存：来回换客户不重复请求
const machineCache = new Map()

function defaultCreateForm() {
  return {
    customer_id: null,
    machine_status_id: null,
    kind: 'issue',
    description: '',
    issue_ref: '',
    urgency: '一般',
    status: 'OPEN',
    owner_user_id: null,
    group_id: null,
    raised_at: today(),
    due_date: '',
    category: '',
    progress_note: '',
  }
}

const createForm = reactive(defaultCreateForm())

function today() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function openCreate() {
  Object.assign(createForm, defaultCreateForm())
  // 正按某个客户筛着就默认建在这个客户下——不带过去的话，建完立刻被自己的筛选藏起来
  if (filters.customer_id) {
    createForm.customer_id = filters.customer_id
    loadMachines(filters.customer_id)
  } else {
    machineOptions.value = []
  }
  if (filters.group_id) createForm.group_id = filters.group_id
  if (filters.urgency) createForm.urgency = filters.urgency
  createVisible.value = true
}

async function loadMachines(customerId) {
  if (machineCache.has(customerId)) {
    machineOptions.value = machineCache.get(customerId)
    return
  }
  machineLoading.value = true
  try {
    const { data } = await customerApi.machines(customerId)
    machineCache.set(customerId, data)
    machineOptions.value = data
  } catch (e) {
    machineOptions.value = []
    ElMessage.error(e.response?.data?.detail || '机台加载失败')
  } finally {
    machineLoading.value = false
  }
}

function onCreateCustomerChange(v) {
  createForm.machine_status_id = null
  machineOptions.value = []
  if (v) loadMachines(v)
}

// 新增的行会不会被当前筛选藏起来——藏起来就明说，否则看着像"保存了但没进去"
function hiddenByFilters(row) {
  return !filteredRows.value.some((r) => r.id === row.id)
}

async function submitCreate() {
  if (!createForm.machine_status_id) {
    ElMessage.warning('请先选客户和机台')
    return
  }
  if (!createForm.description.trim()) {
    ElMessage.warning('描述不能为空')
    return
  }
  creating.value = true
  try {
    // customer_id 不传：后端始终跟着机台走，传了反而可能与机台对不上
    const { customer_id, ...payload } = createForm
    payload.description = payload.description.trim()
    const { data } = await customerIssueApi.create(payload)
    upsertIssue(data)
    createVisible.value = false
    if (data.status === 'CLOSED' && !includeClosed.value) includeClosed.value = true
    ElMessage.success(hiddenByFilters(data) ? '已新增（当前筛选条件下不显示）' : '已新增')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '新增失败')
  } finally {
    creating.value = false
  }
}

// 从总览点条目跳过来时高亮那一条（prop 优先，路由查询串兜底）
const focusId = computed(() => props.focus || Number(route.query.focus) || null)

// 分页：一屏 50 行。表格里每行都带下拉与可编辑格，全量铺开时行数一多就明显掉帧
const page = ref(1)
const pageSize = ref(50)

// ── 统计卡：从缓存现算，不再单独请求 /summary ──
const stats = computed(() => {
  const rows = customerIssues.rows
  const open = rows.filter((r) => r.status !== 'CLOSED')
  return {
    open: open.length,
    critical: open.filter((r) => r.urgency === '重要紧急').length,
    overdue: open.filter((r) => r.overdue).length,
    on_hold: rows.filter((r) => r.status === '挂起').length,
    closed: rows.filter((r) => r.status === 'CLOSED').length,
  }
})

// ── 筛选 + 排序：全部在前端做（数据已全量缓存）──
const filteredRows = computed(() => {
  let rows = customerIssues.rows.slice()
  const f = filters
  // 显式按「已闭环」筛时不再受开关拦截，否则点「已闭环」统计卡会得到一张空表
  if (!includeClosed.value && f.status !== 'CLOSED') rows = rows.filter((r) => r.status !== 'CLOSED')
  if (f.customer_id) rows = rows.filter((r) => r.customer_id === f.customer_id)
  if (f.owner_user_id) rows = rows.filter((r) => r.owner_user_id === f.owner_user_id)
  if (f.group_id) rows = rows.filter((r) => r.group_id === f.group_id)
  if (f.urgency) rows = rows.filter((r) => r.urgency === f.urgency)
  if (f.status) rows = rows.filter((r) => r.status === f.status)
  if (f.overdue_only) rows = rows.filter((r) => r.overdue)
  if (f.q) {
    const kw = f.q.trim().toLowerCase()
    rows = rows.filter((r) =>
      (r.description || '').toLowerCase().includes(kw)
      || (r.issue_ref || '').toLowerCase().includes(kw)
      || (r.owner_display || '').toLowerCase().includes(kw)
      || (r.machine_id || '').toLowerCase().includes(kw)
      || (r.battlefield || '').toLowerCase().includes(kw)
      || (r.progress_note || '').toLowerCase().includes(kw)
      || (r.category || '').toLowerCase().includes(kw))
  }
  rows.sort((a, b) =>
    (STATUS_RANK[a.status] ?? 9) - (STATUS_RANK[b.status] ?? 9)
    || (URGENCY_RANK[a.urgency] ?? 9) - (URGENCY_RANK[b.urgency] ?? 9)
    || (a.raised_at || '9999-99-99').localeCompare(b.raised_at || '9999-99-99')
    || a.id - b.id)
  return rows
})

// 筛选条件一变就回到第一页：留在第 7 页而结果只剩 2 条时，表看着是空的
watch([filters, includeClosed], () => { page.value = 1 }, { deep: true })

const pagedRows = computed(() => {
  // 删行之后页码可能越界（最后一页只剩一条被删掉），这里兜一下，别让表变空白
  const maxPage = Math.max(1, Math.ceil(filteredRows.value.length / pageSize.value))
  const cur = Math.min(page.value, maxPage)
  const start = (cur - 1) * pageSize.value
  return filteredRows.value.slice(start, start + pageSize.value)
})

// 从总览点条目跳过来时，把那一条所在的页翻出来——否则「聚焦」聚了个看不见的行。
// 只在 focus 变化或数据首次到位时跳一次：挂在 filteredRows 上的话，每存一格都会
// 把页码拽回被聚焦那一页，人翻到第 3 页改点东西就被弹回去了
watch([focusId, () => customerIssues.loaded], () => {
  const id = focusId.value
  if (!id || !customerIssues.loaded) return
  const idx = filteredRows.value.findIndex((r) => r.id === id)
  if (idx >= 0) page.value = Math.floor(idx / pageSize.value) + 1
}, { immediate: true })

// 行号跨页连续：默认的 type="index" 每页都从 1 重来，翻到第 3 页看见的还是 1、2、3
function rowIndex(i) {
  return (page.value - 1) * pageSize.value + i + 1
}

function rowClass({ row }) {
  if (row.id === focusId.value) return 'row-focus'
  if (row.status === 'CLOSED') return 'row-done'
  if (row.status === '挂起') return 'row-hold'
  if (row.overdue) return 'row-overdue'
  return ''
}

function toggleFilter(key, val) {
  filters[key] = filters[key] === val ? null : val
  filters.overdue_only = false
  // 点「已闭环」卡片就是想看已闭环，顺手把开关打开，别让人再找一遍复选框
  if (key === 'status' && filters.status === 'CLOSED') includeClosed.value = true
}
function toggleOverdue() {
  filters.overdue_only = !filters.overdue_only
}
function resetStatusFilter() {
  filters.status = null
  filters.urgency = null
  filters.overdue_only = false
}

// 逐格保存：后端会在状态流转时自动维护闭环时间，保存后用返回值整行替换缓存
async function save(row, patch) {
  try {
    const { data } = await customerIssueApi.update(row.id, { version: row.version, ...patch })
    upsertIssue(data)
  } catch (e) {
    if (e.response?.status !== 409) ElMessage.error(e.response?.data?.detail || '保存失败')
    refreshIssues()
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除「${row.description || '该条目'}」吗？`, '提示', { type: 'warning' })
  } catch { return }
  try {
    await customerIssueApi.remove(row.id)
    removeIssue(row.id)
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

async function onExport() {
  exporting.value = true
  try {
    const resp = await customerIssueApi.exportXlsx(includeClosed.value)
    const ts = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19)
    downloadBlob(resp.data, `客户面问题跟踪_${ts}.xlsx`)
    ElMessage.success('已导出')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导出失败')
  } finally {
    exporting.value = false
  }
}

async function onImportTemplate() {
  try {
    const resp = await customerIssueApi.importTemplate()
    downloadBlob(resp.data, '客户面问题跟踪_导入模板.xlsx')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '模板下载失败')
  }
}

// el-upload 的 on-change：拿到文件后自己上传；失败要明确报错
async function onImport(uploadFile) {
  const file = uploadFile?.raw
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.xlsx')) {
    ElMessage.error('仅支持 .xlsx 文件')
    return
  }
  importing.value = true
  try {
    const { data } = await customerIssueApi.importXlsx(file)
    await reloadIssues()
    const errs = data.errors || []
    if (errs.length) {
      // 部分失败：逐行原因列全（HTML 换行），让用户能定位改哪一行
      ElMessageBox.alert(
        `成功导入 <b>${data.created}</b> 条，另有 <b>${errs.length}</b> 行未导入：<br><br>`
          + errs.map((e) => `· ${e}`).join('<br>'),
        '导入完成（部分未成功）',
        { type: 'warning', dangerouslyUseHTMLString: true, customClass: 'ci-import-box' },
      )
    } else {
      ElMessage.success(`成功导入 ${data.created} 条`)
    }
  } catch (e) {
    // 文件级错误（解析失败 / 缺列 / 空文件）后端返回 400 detail
    ElMessage.error(e.response?.data?.detail || '导入失败，请检查文件格式')
  } finally {
    importing.value = false
  }
}

// 带 focus 进来时，把已闭环也放开，否则聚焦项可能是已闭环、被过滤掉
watch(focusId, (v) => { if (v) includeClosed.value = true }, { immediate: true })

onMounted(async () => {
  const [u, c, g] = await Promise.allSettled([
    userApi.options({ only_can_login: true }),
    customerApi.list(),
    resourceGroupApi.list({ kind: 'pl' }),
  ])
  if (u.status === 'fulfilled') users.value = u.value.data
  if (c.status === 'fulfilled') customers.value = c.value.data
  if (g.status === 'fulfilled') groups.value = g.value.data
  // 已有缓存 → 秒显 + 后台静默刷新；否则首次加载
  if (customerIssues.loaded) refreshIssues()
  else await ensureIssues()
})

// KeepAlive 切回来：缓存数据先显示，后台静默刷新（与总览增删保持同步）
let activatedOnce = false
onActivated(() => {
  if (!activatedOnce) { activatedOnce = true; return }  // 首次激活由 onMounted 负责
  refreshIssues()
})
</script>

<style scoped>
.track-page { display: flex; flex-direction: column; gap: 14px; }

/* 统计卡 */
.stat-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
.stat-card {
  background: #fff; border: 1px solid #eaecef; border-radius: 10px;
  padding: 14px 20px; cursor: pointer; text-align: center; transition: all .2s;
}
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 8px 20px -12px rgba(31,45,61,.3); }
.stat-card.active { border-color: #409eff; box-shadow: 0 0 0 2px #ecf5ff inset; }
.stat-num { font-size: 28px; font-weight: 700; color: #1f2329; line-height: 1.1; }
.stat-label { font-size: 13px; color: #909399; margin-top: 4px; }
.crit .stat-num { color: #f56c6c; }
.over .stat-num { color: #e6a23c; }
.hold .stat-num { color: #909399; }
.done .stat-num { color: #67c23a; }

/* 筛选栏 */
.filter-bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.filter-right { display: flex; align-items: center; gap: 8px; margin-left: auto; }
.muted { color: #909399; font-size: 13px; }

/* 行着色：已闭环浅绿（与专项管理 closed-row 同款，盖过斑马纹），挂起偏黄，逾期偏红 */
:deep(.row-done td.el-table__cell) { background: #f0f9eb !important; }
:deep(.row-done .cell) { color: #6b7d6b; }
:deep(.row-hold) { background: #fdf9f0 !important; }
:deep(.row-overdue) { background: #fef4f4 !important; }
:deep(.row-focus) { background: #ecf5ff !important; box-shadow: inset 3px 0 0 #409eff; }

:deep(.cell-text) { cursor: pointer; display: inline-block; min-height: 20px; min-width: 40px; }
:deep(.cell-text:hover) { color: #409eff; }
:deep(.cell-multiline) { white-space: pre-wrap; line-height: 1.5; }
:deep(.date-overdue) { color: #f56c6c; font-weight: 600; }

/* 链接单元格 */
:deep(.machine-link), :deep(.issue-link) { color: #409eff; text-decoration: none; }
:deep(.machine-link:hover), :deep(.issue-link:hover) { text-decoration: underline; }
:deep(.linkcell) { display: inline-flex; align-items: center; gap: 4px; }
:deep(.linkcell .edit-ico) { cursor: pointer; color: #c0c4cc; font-size: 13px; }
:deep(.linkcell .edit-ico:hover) { color: #409eff; }

/* 分页与图例 */
.pager { display: flex; justify-content: flex-end; margin-top: 10px; }
.legend { display: flex; align-items: center; gap: 16px; margin-top: 10px; font-size: 12px; color: #606266; flex-wrap: wrap; }
.legend .dot { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; }
.d-open { background: #fff; border: 1px solid #dcdfe6; }
.d-hold { background: #fdf9f0; border: 1px solid #f3d19e; }
.d-done { background: #f0f9eb; border: 1px solid #b3d8a4; }
.d-over { background: #fef4f4; border: 1px solid #fab6b6; }
</style>
