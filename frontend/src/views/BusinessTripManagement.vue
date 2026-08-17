<template>
  <div class="trip-page">
    <!-- ===== 看板 ===== -->
    <div class="board">
      <div class="board-head">
        <span class="board-title">客户面支撑看板</span>
        <el-date-picker
          v-model="dashRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始"
          end-placeholder="结束"
          value-format="YYYY-MM-DD"
          size="small"
          :clearable="false"
          style="width: 260px"
          @change="loadDash"
        />
        <span class="muted">口径：{{ dash.range_label || '—' }}</span>
      </div>

      <div class="stat-cards">
        <div class="stat-card now">
          <div class="stat-num">{{ dash.on_trip_now }}</div>
          <div class="stat-label">当前支撑中（人次）</div>
        </div>
        <div class="stat-card plan">
          <div class="stat-num">{{ dash.planned }}</div>
          <div class="stat-label">计划中</div>
        </div>
        <div class="stat-card month">
          <div class="stat-num">{{ dash.range_total }}</div>
          <div class="stat-label">区间支撑（人次）</div>
        </div>
      </div>

      <div class="dim-cards">
        <el-card v-for="dim in dimCards" :key="dim.title" shadow="never" class="dim-card">
          <div class="dim-title">{{ dim.title }}</div>
          <div v-if="!dim.items.length" class="muted">暂无数据</div>
          <div v-else class="dim-list">
            <div v-for="it in dim.items" :key="it.name" class="dim-row">
              <span class="dim-name" :title="it.name">{{ it.name }}</span>
              <div class="dim-bar-wrap"><div class="dim-bar" :style="{ width: dimWidth(it.count, dim.items) }"></div></div>
              <span class="dim-count">{{ it.count }}</span>
            </div>
          </div>
        </el-card>
      </div>
    </div>

    <!-- ===== 工具栏 ===== -->
    <el-card shadow="never" class="main-card">
      <div class="toolbar">
        <el-button type="primary" :icon="Plus" @click="openCreate">登记支撑</el-button>
        <el-button :icon="Refresh" @click="loadAll">刷新</el-button>
        <el-select v-model="filterUserId" placeholder="按成员" clearable filterable size="small" style="width: 150px">
          <el-option v-for="u in users" :key="u.id" :value="u.id" :label="userLabel(u)" />
        </el-select>
        <el-select v-model="filterCustomerId" placeholder="按战场" clearable filterable size="small" style="width: 150px">
          <el-option v-for="c in customers" :key="c.id" :value="c.id" :label="custLabel(c)" />
        </el-select>
        <el-select v-model="filterStatus" placeholder="按状态" clearable size="small" style="width: 120px">
          <el-option v-for="s in STATUSES" :key="s" :value="s" :label="s" />
        </el-select>
        <span class="legend">
          <span class="lg now">进行中</span>
          <span class="lg plan">计划中</span>
          <span class="lg done">已完成</span>
        </span>
      </div>

      <!-- ===== 甘特时间轴 ===== -->
      <div class="gantt-head">
        <el-button :icon="ArrowLeft" size="small" circle @click="shiftMonth(-1)" />
        <span class="gantt-month">{{ monthLabel }}</span>
        <el-button :icon="ArrowRight" size="small" circle @click="shiftMonth(1)" />
        <span class="gantt-tip">横条为支撑区间，点击可编辑</span>
      </div>

      <div class="gantt" v-loading="loading">
        <div class="gantt-scroll">
          <div class="gantt-axis">
            <div class="axis-label"></div>
            <div class="axis-days">
              <div
                v-for="d in daysInMonth"
                :key="d"
                class="axis-day"
                :class="{ weekend: isWeekend(d), today: isToday(d) }"
              >{{ d }}</div>
            </div>
          </div>
          <div v-if="!timelineRows.length" class="gantt-empty">本月暂无支撑安排</div>
          <div v-for="row in timelineRows" :key="row.key" class="gantt-row">
            <div class="row-label">
              <span class="row-name" :title="row.name">{{ row.name }}</span>
              <span v-if="row.group" class="row-group">{{ row.group }}</span>
            </div>
            <div class="row-track">
              <div
                v-for="d in daysInMonth"
                :key="d"
                class="track-cell"
                :class="{ weekend: isWeekend(d) }"
              ></div>
              <div v-if="todayPct !== null" class="today-line" :style="{ left: todayPct + '%' }"></div>
              <el-tooltip
                v-for="bar in row.bars"
                :key="bar.id"
                :content="barTip(bar)"
                placement="top"
              >
                <div
                  class="gantt-bar"
                  :class="bar.statusClass"
                  :style="{ left: bar.leftPct + '%', width: bar.widthPct + '%' }"
                  @click="openEdit(bar.trip)"
                >{{ bar.label }}</div>
              </el-tooltip>
            </div>
          </div>
        </div>
      </div>

      <!-- ===== 明细表 ===== -->
      <div class="table-title">支撑明细（共 {{ filteredTrips.length }} 条）</div>
      <el-table :data="filteredTrips" v-loading="loading" border stripe size="small" style="width: 100%">
        <el-table-column label="成员" width="120">
          <template #default="{ row }">
            {{ row.user_name || '未指定' }}
            <div v-if="row.user_group" class="cell-sub">{{ row.user_group }}</div>
          </template>
        </el-table-column>
        <el-table-column label="支撑战场" width="140">
          <template #default="{ row }">
            <el-tag v-if="row.customer_name" size="small" effect="plain">{{ row.customer_name }}</el-tag>
            <span v-else class="muted">—</span>
            <div v-if="row.location" class="cell-sub">{{ row.location }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="purpose" label="事由" min-width="160" show-overflow-tooltip />
        <el-table-column label="支撑时间" width="200">
          <template #default="{ row }">
            <span v-if="row.start_date || row.end_date">
              {{ fmt(row.start_date) }} ~ {{ fmt(row.end_date) }}
            </span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="140" show-overflow-tooltip />
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ===== 登记/编辑弹窗 ===== -->
    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑支撑' : '登记支撑'" width="560px" :close-on-click-modal="false">
      <el-form :model="form" label-width="100px">
        <el-form-item label="成员" required>
          <el-select v-model="form.user_id" filterable placeholder="选择支撑人" style="width: 100%">
            <el-option v-for="u in users" :key="u.id" :value="u.id" :label="userLabel(u)" />
          </el-select>
        </el-form-item>
        <el-form-item label="支撑战场" required>
          <el-select v-model="form.customer_id" filterable clearable placeholder="选择客户/战场" style="width: 100%">
            <el-option v-for="c in customers" :key="c.id" :value="c.id" :label="custLabel(c)" />
          </el-select>
        </el-form-item>
        <el-form-item label="具体地点">
          <el-input v-model="form.location" placeholder="可选：城市 / 站点 / 非战场地点" />
        </el-form-item>
        <el-form-item label="事由">
          <el-input v-model="form.purpose" placeholder="如 现场交付 / 调试支持 / 客户会议" />
        </el-form-item>
        <el-form-item label="支撑时间" required>
          <el-date-picker
            v-model="form.dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始"
            end-placeholder="结束"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item v-if="form.id" label="已取消">
          <el-switch v-model="form.cancelled" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, ArrowRight, Plus, Refresh } from '@element-plus/icons-vue'
import { businessTripApi, customerApi, userApi } from '../api'

const STATUSES = ['计划中', '进行中', '已完成', '已取消']

const loading = ref(false)
const saving = ref(false)
const trips = ref([])
const users = ref([])
const customers = ref([])
const dash = ref({ on_trip_now: 0, planned: 0, range_label: '', range_total: 0, by_customer: [], by_person: [], by_domain: [] })

const filterUserId = ref(null)
const filterCustomerId = ref(null)
const filterStatus = ref(null)

// ── 月份（甘特轴）──
const today = new Date()
const monthKey = ref(`${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`)
const ym = computed(() => {
  const [y, m] = monthKey.value.split('-').map(Number)
  return { y, m }
})
const daysInMonth = computed(() => new Date(ym.value.y, ym.value.m, 0).getDate())
const monthLabel = computed(() => `${ym.value.y} 年 ${ym.value.m} 月`)

function shiftMonth(delta) {
  let { y, m } = ym.value
  m += delta
  if (m < 1) { m = 12; y -= 1 }
  if (m > 12) { m = 1; y += 1 }
  monthKey.value = `${y}-${String(m).padStart(2, '0')}`
}

function isWeekend(day) {
  const d = new Date(ym.value.y, ym.value.m - 1, day).getDay()
  return d === 0 || d === 6
}
function isToday(day) {
  return today.getFullYear() === ym.value.y && today.getMonth() + 1 === ym.value.m && today.getDate() === day
}
const todayPct = computed(() => {
  if (today.getFullYear() !== ym.value.y || today.getMonth() + 1 !== ym.value.m) return null
  return ((today.getDate() - 0.5) / daysInMonth.value) * 100
})

// ── 看板区间 ──
function ymd(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const dashRange = ref([ymd(new Date(today.getFullYear(), today.getMonth(), 1)), ymd(today)])
const dimCards = computed(() => [
  { title: '按领域', items: dash.value.by_domain || [] },
  { title: '按人', items: dash.value.by_person || [] },
  { title: '按战场', items: dash.value.by_customer || [] },
])
function dimWidth(count, items) {
  const max = Math.max(1, ...items.map((i) => i.count))
  return `${Math.round((count / max) * 100)}%`
}

// ── 展示辅助 ──
function fmt(d) {
  if (!d) return ''
  const dt = new Date(d)
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`
}
function userLabel(u) {
  return `${u.full_name || u.username}${u.emp_no ? ' (' + u.emp_no + ')' : ''}`
}
function custLabel(c) {
  return c.display_name || c.code
}
function statusTagType(s) {
  return { 进行中: 'success', 计划中: 'primary', 已完成: 'info', 已取消: 'danger' }[s] || 'info'
}
function statusClass(s) {
  return { 进行中: 'bar-now', 计划中: 'bar-plan', 已完成: 'bar-done' }[s] || 'bar-done'
}

// ── 过滤 + 时间轴 ──
const filteredTrips = computed(() => {
  return trips.value.filter((t) => {
    if (filterUserId.value && t.user_id !== filterUserId.value) return false
    if (filterCustomerId.value && t.customer_id !== filterCustomerId.value) return false
    if (filterStatus.value && t.status !== filterStatus.value) return false
    return true
  })
})

const timelineRows = computed(() => {
  const { y, m } = ym.value
  const monthStart = new Date(y, m - 1, 1)
  const monthEnd = new Date(y, m - 1, daysInMonth.value)
  const byUser = new Map()
  for (const t of filteredTrips.value) {
    if (t.cancelled || !t.start_date || !t.end_date) continue
    const s = new Date(t.start_date)
    const e = new Date(t.end_date)
    if (e < monthStart || s > monthEnd) continue
    const key = t.user_id != null ? `u${t.user_id}` : `n:${t.user_name || '未指定'}`
    if (!byUser.has(key)) {
      byUser.set(key, { key, name: t.user_name || '未指定', group: t.user_group || '', bars: [] })
    }
    const os = s < monthStart ? monthStart : s
    const oe = e > monthEnd ? monthEnd : e
    const startDay = os.getDate()
    const spanDays = Math.round((oe - os) / 86400000) + 1
    byUser.get(key).bars.push({
      id: t.id,
      leftPct: ((startDay - 1) / daysInMonth.value) * 100,
      widthPct: (spanDays / daysInMonth.value) * 100,
      statusClass: statusClass(t.status),
      label: t.customer_name || t.location || '支撑',
      trip: t,
    })
  }
  return Array.from(byUser.values()).sort((a, b) => a.name.localeCompare(b.name, 'zh-Hans-CN'))
})

function barTip(bar) {
  const t = bar.trip
  return `${t.customer_name || t.location || '支撑'}｜${fmt(t.start_date)} ~ ${fmt(t.end_date)}｜${t.status}${t.purpose ? '｜' + t.purpose : ''}`
}

// ── 数据加载 ──
async function loadTrips() {
  loading.value = true
  try {
    const { data } = await businessTripApi.list()
    trips.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}
async function loadDash() {
  try {
    const [start, end] = dashRange.value || []
    const { data } = await businessTripApi.dashboard({ start, end })
    dash.value = data
  } catch { /* 看板失败不阻塞 */ }
}
async function loadOptions() {
  try {
    const [{ data: us }, { data: cs }] = await Promise.all([
      userApi.options({ include_inactive: false }),
      customerApi.list(),
    ])
    users.value = us
    customers.value = cs
  } catch { /* 下拉为空不阻塞 */ }
}
async function loadAll() {
  await Promise.all([loadTrips(), loadDash()])
}

// ── CRUD ──
const dialogVisible = ref(false)
const form = reactive(blankForm())
function blankForm() {
  return {
    id: null, version: 0, user_id: null, customer_id: null,
    location: '', purpose: '', dateRange: null, cancelled: false, remark: '',
  }
}
function openCreate() {
  Object.assign(form, blankForm())
  dialogVisible.value = true
}
function openEdit(row) {
  Object.assign(form, blankForm(), {
    id: row.id, version: row.version, user_id: row.user_id, customer_id: row.customer_id,
    location: row.location || '', purpose: row.purpose || '',
    dateRange: row.start_date && row.end_date ? [row.start_date, row.end_date] : null,
    cancelled: !!row.cancelled, remark: row.remark || '',
  })
  dialogVisible.value = true
}
async function onSubmit() {
  if (!form.user_id) { ElMessage.warning('请选择支撑成员'); return }
  if (!form.customer_id) { ElMessage.warning('请选择支撑战场'); return }
  if (!form.dateRange || !form.dateRange[0]) { ElMessage.warning('请选择支撑时间'); return }
  const payload = {
    user_id: form.user_id, customer_id: form.customer_id,
    location: form.location, purpose: form.purpose,
    start_date: form.dateRange[0], end_date: form.dateRange[1],
    cancelled: form.cancelled, remark: form.remark,
  }
  saving.value = true
  try {
    if (form.id) await businessTripApi.update(form.id, { ...payload, version: form.version })
    else await businessTripApi.create(payload)
    ElMessage.success('已保存')
    dialogVisible.value = false
    loadAll()
  } catch (e) {
    if (e.response?.status === 409) { dialogVisible.value = false; loadAll() }
    else ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}
async function onDelete(row) {
  await ElMessageBox.confirm(`确认删除「${row.user_name || ''} · ${row.customer_name || ''}」的支撑记录吗？`, '提示', { type: 'warning' })
  try {
    await businessTripApi.remove(row.id)
    ElMessage.success('已删除')
    loadAll()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '删除失败') }
}

onMounted(() => { loadAll(); loadOptions() })
</script>

<style scoped>
.trip-page { padding: 2px; }

/* 看板 */
.board { margin-bottom: 12px; }
.board-head { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.board-title { font-size: 15px; font-weight: 600; }
.stat-cards { display: flex; gap: 12px; margin-bottom: 12px; }
.stat-card {
  flex: 1; border-radius: 8px; padding: 14px 18px; color: #fff;
  display: flex; flex-direction: column; justify-content: center;
}
.stat-card.now { background: linear-gradient(135deg, #67C23A, #4e9e2c); }
.stat-card.plan { background: linear-gradient(135deg, #409EFF, #2a7fd4); }
.stat-card.month { background: linear-gradient(135deg, #E6A23C, #c8842a); }
.stat-num { font-size: 26px; font-weight: 700; line-height: 1.1; }
.stat-label { font-size: 13px; opacity: 0.92; margin-top: 4px; }

.dim-cards { display: flex; gap: 12px; }
.dim-card { flex: 1; }
.dim-title { font-weight: 600; margin-bottom: 10px; }
.dim-list { display: flex; flex-direction: column; gap: 7px; max-height: 200px; overflow-y: auto; }
.dim-row { display: flex; align-items: center; gap: 10px; }
.dim-name { flex: 0 0 96px; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dim-bar-wrap { flex: 1 1 auto; background: #f0f2f5; border-radius: 4px; height: 14px; overflow: hidden; }
.dim-bar { height: 100%; background: #409EFF; border-radius: 4px; min-width: 2px; transition: width 0.3s; }
.dim-count { flex: 0 0 auto; font-size: 13px; color: #1f2329; font-weight: 600; min-width: 22px; text-align: right; }
.muted { color: #909399; font-size: 13px; }

/* 工具栏 */
.toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.legend { margin-left: auto; display: flex; gap: 10px; font-size: 12px; }
.lg { display: inline-flex; align-items: center; }
.lg::before { content: ''; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; }
.lg.now::before { background: #67C23A; }
.lg.plan::before { background: #409EFF; }
.lg.done::before { background: #c0c4cc; }

/* 甘特 */
.gantt-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.gantt-month { font-weight: 600; font-size: 15px; min-width: 110px; text-align: center; }
.gantt-tip { color: #909399; font-size: 12px; margin-left: 6px; }
.gantt { border: 1px solid #ebeef5; border-radius: 6px; overflow: hidden; margin-bottom: 18px; }
.gantt-scroll { overflow-x: auto; }
.gantt-axis, .gantt-row { display: flex; align-items: stretch; min-width: 760px; }
.axis-label { flex: 0 0 130px; }
.row-label {
  flex: 0 0 130px; padding: 0 10px; display: flex; flex-direction: column; justify-content: center;
  border-right: 1px solid #ebeef5; background: #fafafa;
}
.row-name { font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-group { font-size: 11px; color: #909399; }
.axis-days { flex: 1 1 auto; display: flex; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.axis-day {
  flex: 1 1 0; text-align: center; font-size: 11px; color: #909399; padding: 4px 0;
  border-left: 1px solid #f2f3f5;
}
.axis-day.weekend { background: #f5f7fa; }
.axis-day.today { background: #ecf5ff; color: #409EFF; font-weight: 700; }
.gantt-row { border-top: 1px solid #f2f3f5; }
.row-track { flex: 1 1 auto; position: relative; display: flex; height: 34px; }
.track-cell { flex: 1 1 0; border-left: 1px solid #f5f6f8; }
.track-cell.weekend { background: #fafbfc; }
.today-line { position: absolute; top: 0; bottom: 0; width: 2px; background: #f56c6c; opacity: 0.5; z-index: 1; }
.gantt-bar {
  position: absolute; top: 6px; height: 22px; line-height: 22px; border-radius: 4px;
  font-size: 11px; color: #fff; padding: 0 6px; overflow: hidden; white-space: nowrap;
  text-overflow: ellipsis; cursor: pointer; z-index: 2; box-shadow: 0 1px 2px rgba(0,0,0,0.12);
}
.gantt-bar.bar-now { background: #67C23A; }
.gantt-bar.bar-plan { background: #409EFF; }
.gantt-bar.bar-done { background: #b4bcc8; }
.gantt-bar:hover { filter: brightness(1.06); }
.gantt-empty { padding: 22px; text-align: center; color: #909399; font-size: 13px; }

/* 明细表 */
.table-title { font-weight: 600; margin: 4px 0 10px; }
.cell-sub { font-size: 11px; color: #909399; }
</style>
