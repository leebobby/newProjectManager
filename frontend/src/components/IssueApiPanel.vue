<template>
  <div class="api-panel" v-loading="loading">
    <div class="api-bar">
      <el-tag type="primary" effect="plain">项目：{{ project }}</el-tag>
      <el-button
        v-if="isAdmin"
        size="small"
        type="primary"
        :icon="Refresh"
        :loading="collecting"
        @click="collectNow"
      >{{ collecting ? '采集中…' : '立即采集' }}</el-button>
      <el-button
        v-if="snapshots.length"
        size="small"
        :icon="Download"
        :loading="exporting"
        @click="doExport"
      >导出 Excel</el-button>
      <span class="muted" style="margin-left: auto">共 {{ snapshots.length }} 个历史快照</span>
    </div>

    <!-- 采集失败时快照会是空的，而「采集日志」正是这时最该看的，所以 tabs 始终渲染 -->
    <el-tabs v-model="topTab" class="snap-tabs" @tab-change="onTopTabChange">
      <!-- Tab 1：某一次统计到的数据 -->
      <el-tab-pane label="统计数据" name="snapshot">
        <el-empty v-if="!loading && !snapshots.length" description="暂无快照数据">
          <span class="muted">
            每天定时自动采集{{ isAdmin ? '（时刻在「配置」中设置），也可点上方「立即采集」手动触发' : '' }}；
            若长期没有数据，请到「采集日志」查看失败原因。
          </span>
        </el-empty>

        <template v-else>
        <div class="snap-bar">
          <span class="muted">统计日期：</span>
          <el-select v-model="selDate" size="small" style="width: 190px" @change="loadDetail">
            <el-option v-for="s in snapshots" :key="s.date" :label="`${s.date}（${s.total} 条）`" :value="s.date" />
          </el-select>
          <span v-if="detail && detail.created_at" class="muted">采集于 {{ detail.created_at }}</span>
        </div>

        <template v-if="detail && detail.exists">
          <div class="stat-row">
            <div class="stat-card" @click="openDrill({}, '全部问题单')">
              <div class="stat-num">{{ detail.count }}</div><div class="stat-label">合计</div>
            </div>
            <div class="stat-card sev" @click="openDrill({ severity: '严重' }, '严重缺陷')">
              <div class="stat-num">{{ sevCount('严重') }}</div><div class="stat-label">严重</div>
            </div>
            <div class="stat-card nor" @click="openDrill({ severity: '一般' }, '一般缺陷')">
              <div class="stat-num">{{ sevCount('一般') }}</div><div class="stat-label">一般</div>
            </div>
            <div class="stat-card tip" @click="openDrill({ severity: '提示' }, '提示缺陷')">
              <div class="stat-num">{{ sevCount('提示') }}</div><div class="stat-label">提示</div>
            </div>
          </div>

          <el-card shadow="never" class="main-card">
            <el-tabs v-model="subTab" @tab-change="onSubTabChange">
              <el-tab-pane label="统计明细" name="stats">
                <div class="stats-toolbar">
                  <span class="stats-toolbar-label">视图：</span>
                  <el-button-group size="small">
                    <el-button :type="statsView === 'both' ? 'primary' : ''" @click="statsView = 'both'">双视图</el-button>
                    <el-button :type="statsView === 'table' ? 'primary' : ''" @click="statsView = 'table'">表格</el-button>
                    <el-button :type="statsView === 'chart' ? 'primary' : ''" @click="statsView = 'chart'">图表</el-button>
                  </el-button-group>
                </div>

                <div class="section-title">按小组 × 严重程度</div>
                <el-row :gutter="16">
                  <el-col v-show="statsView !== 'chart'" :span="statsView === 'both' ? 14 : 24">
                    <StatsTable head="小组" :columns="groupBySev.columns" :rows="groupBySev.rows"
                      @cell-click="(r, c, v) => onCellClick('group', r, c, v)" />
                  </el-col>
                  <el-col v-show="statsView !== 'table'" :span="statsView === 'both' ? 10 : 24">
                    <div ref="groupBarEl" class="chart-sm" :class="{ 'chart-wide': statsView === 'chart' }" />
                  </el-col>
                </el-row>

                <div class="section-title" style="margin-top: 20px">按客户面 × 严重程度</div>
                <el-row :gutter="16">
                  <el-col v-show="statsView !== 'chart'" :span="statsView === 'both' ? 14 : 24">
                    <StatsTable head="客户面" :columns="customerBySev.columns" :rows="customerBySev.rows"
                      @cell-click="(r, c, v) => onCellClick('customer', r, c, v)" />
                  </el-col>
                  <el-col v-show="statsView !== 'table'" :span="statsView === 'both' ? 10 : 24">
                    <div ref="customerBarEl" class="chart-sm" :class="{ 'chart-wide': statsView === 'chart' }" />
                  </el-col>
                </el-row>

                <div class="section-title" style="margin-top: 20px">按年月 × 严重程度</div>
                <el-row :gutter="16">
                  <el-col v-show="statsView !== 'chart'" :span="statsView === 'both' ? 14 : 24">
                    <StatsTable head="年月" :columns="yearMonthBySev.columns" :rows="yearMonthBySev.rows"
                      @cell-click="(r, c, v) => onCellClick('year_month', r, c, v)" />
                  </el-col>
                  <el-col v-show="statsView !== 'table'" :span="statsView === 'both' ? 10 : 24">
                    <div ref="yearMonthBarEl" class="chart-sm" :class="{ 'chart-wide': statsView === 'chart' }" />
                  </el-col>
                </el-row>
              </el-tab-pane>

              <el-tab-pane label="原始数据" name="raw">
                <div class="raw-bar">
                  <el-input v-model="search" :prefix-icon="Search" clearable placeholder="搜索标题/编号/责任人/小组" style="width: 320px" />
                  <span class="muted">共 {{ filtered.length }} 条</span>
                </div>
                <IssueRawTable :data="filtered" max-height="520" />
              </el-tab-pane>
            </el-tabs>
          </el-card>
        </template>
        <el-empty v-else description="该日期无数据" />
        </template>
      </el-tab-pane>

      <!-- Tab 2：趋势（每日刷新，只读库里数字）-->
      <el-tab-pane label="趋势" name="trend">
        <div class="trend-bar">
          <span class="muted">维度：</span>
          <el-radio-group v-model="trendDim" size="small" @change="loadTrend">
            <el-radio-button label="group">按小组</el-radio-button>
            <el-radio-button label="customer">按客户面</el-radio-button>
            <el-radio-button label="severity">按严重程度</el-radio-button>
          </el-radio-group>
          <span class="muted" style="margin-left: auto">已积累 {{ trend?.dates?.length || 0 }} 天</span>
        </div>
        <div v-if="trend && !trend.dates.length" class="muted" style="padding: 28px 0; text-align: center">
          暂无趋势数据（至少采集 1 天后展示；多天才能看出走势）
        </div>
        <div v-else ref="trendEl" class="chart-lg" />
      </el-tab-pane>

      <!-- Tab 3：采集日志（定时 + 手动的每次执行，成败都留痕）-->
      <el-tab-pane label="采集日志" name="logs">
        <div class="trend-bar">
          <el-button size="small" :icon="Refresh" :loading="logsLoading" @click="loadLogs">刷新</el-button>
          <span class="muted">记录每次采集的耗时与失败原因，最近 50 条</span>
        </div>
        <el-table v-loading="logsLoading" :data="logs" border stripe size="small" max-height="520">
          <el-table-column prop="started_at" label="开始时间" width="160" />
          <el-table-column label="结果" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="row.ok ? 'success' : 'danger'" size="small">{{ row.ok ? '成功' : '失败' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="触发" width="90" align="center">
            <template #default="{ row }">{{ row.source === 'manual' ? '手动' : '定时' }}</template>
          </el-table-column>
          <el-table-column prop="total" label="条数" width="80" align="center" />
          <el-table-column label="耗时" width="90" align="center">
            <template #default="{ row }">{{ (row.duration_ms / 1000).toFixed(1) }}s</template>
          </el-table-column>
          <el-table-column prop="error" label="失败原因" min-width="280" show-overflow-tooltip>
            <template #default="{ row }">
              <span :class="row.ok ? 'muted' : 'err-text'">{{ row.error || '—' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-drawer v-model="drillVisible" :title="drillTitle" size="72%" direction="rtl">
      <div class="muted" style="margin-bottom: 8px">共 {{ drillRows.length }} 条</div>
      <IssueRawTable :data="drillRows" max-height="calc(100vh - 150px)" />
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElTable, ElTableColumn, ElTag } from 'element-plus'
import { Download, Refresh, Search } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { downloadBlob, issueApi } from '../api'
import { auth } from '../store/auth'

const props = defineProps({
  project: { type: String, required: true },
})

const isAdmin = auth.isAdmin
const collecting = ref(false)
const exporting = ref(false)

const PAL = ['#4073ba', '#67C23A', '#E6A23C', '#F56C6C', '#909399', '#8E7AD8', '#26C9C3', '#F9A825']
const SEV_CLR = { 严重: '#F56C6C', 一般: '#E6A23C', 提示: '#909399' }
const SEV_ORDER = { 严重: 0, 一般: 1, 提示: 2 }

// ── 内联子组件：统计交叉表 ───────────────────────────
const StatsTable = defineComponent({
  props: { columns: Array, rows: Array, head: { type: String, default: '分组' } },
  emits: ['cell-click'],
  setup(p, { emit }) {
    return () => h(ElTable, { data: p.rows || [], border: true, stripe: true, size: 'small' }, {
      default: () => [
        h(ElTableColumn, { prop: 'label', label: p.head, width: 150, fixed: true }),
        ...(p.columns || []).map((col) =>
          h(ElTableColumn, { key: col, label: col, align: 'center', minWidth: 80 }, {
            default: ({ row }) => {
              const val = row[col] ?? 0
              const isTotal = col === '合计' || row.label === '合计'
              return h('span', {
                class: val && !isTotal ? 'num-link' : (isTotal && val ? 'num-total' : 'num-zero'),
                onClick: (val && !isTotal) ? () => emit('cell-click', row.label, col, val) : undefined,
              }, String(val))
            },
          }),
        ),
      ],
    })
  },
})

// ── 内联子组件：问题单原始表格 ─────────────────────
const IssueRawTable = defineComponent({
  props: { data: Array, maxHeight: [String, Number] },
  setup(p) {
    const sevType = (s) => (s === '严重' ? 'danger' : s === '一般' ? 'warning' : 'info')
    return () => h(ElTable, {
      data: p.data || [], border: true, stripe: true, size: 'small', maxHeight: p.maxHeight,
    }, {
      default: () => [
        h(ElTableColumn, { prop: 'version', label: '版本信息', width: 160, showOverflowTooltip: true }),
        h(ElTableColumn, { prop: 'issue_id', label: '缺陷业务编号', width: 190 }),
        h(ElTableColumn, { prop: 'title', label: '标题', minWidth: 240, showOverflowTooltip: true }),
        h(ElTableColumn, { prop: 'owner', label: '当前责任人', width: 100 }),
        h(ElTableColumn, { prop: 'group', label: '所属小组', width: 130 }),
        h(ElTableColumn, { prop: 'department', label: '责任人部门', width: 150, showOverflowTooltip: true }),
        h(ElTableColumn, { prop: 'customer', label: '客户面', width: 110 }),
        h(ElTableColumn, { prop: 'feature', label: '特性', width: 110, showOverflowTooltip: true }),
        h(ElTableColumn, { prop: 'subsystem', label: '子系统', width: 110, showOverflowTooltip: true }),
        h(ElTableColumn, { prop: 'module', label: '模块', width: 110, showOverflowTooltip: true }),
        h(ElTableColumn, { prop: 'progress', label: '进展', width: 90 }),
        h(ElTableColumn, { prop: 'severity', label: '严重程度', width: 90, align: 'center' }, {
          default: ({ row }) => h(ElTag, { type: sevType(row.severity), size: 'small' }, () => row.severity || '—'),
        }),
      ],
    })
  },
})

const loading = ref(false)
const snapshots = ref([])
const selDate = ref('')
const detail = ref(null)
const topTab = ref('snapshot')
const subTab = ref('stats')
const statsView = ref('both')
const search = ref('')
const trendDim = ref('group')
const trend = ref(null)

const raw = computed(() => detail.value?.raw || [])
function sevCount(s) { return detail.value?.by_severity?.[s] || 0 }

// ── 交叉表构建（行维度 × 严重程度）────────────────
function buildCross(rows, rowField, colField) {
  const rowFallback = rowField === 'group' ? '未分组' : '未标注'
  const colFallback = '未标注'
  const map = {}
  const colTotals = {}
  const colSet = new Set()
  let grand = 0
  for (const r of rows) {
    const rv = r[rowField] || rowFallback
    const cv = r[colField] || colFallback
    colSet.add(cv)
    map[rv] = map[rv] || {}
    map[rv][cv] = (map[rv][cv] || 0) + 1
    colTotals[cv] = (colTotals[cv] || 0) + 1
    grand += 1
  }
  let cols = [...colSet]
  if (colField === 'severity') cols.sort((a, b) => (SEV_ORDER[a] ?? 99) - (SEV_ORDER[b] ?? 99))
  else cols.sort()
  const columns = [...cols, '合计']
  const outRows = Object.keys(map).sort().map((rv) => {
    const rec = { label: rv }
    let t = 0
    for (const c of cols) { const n = map[rv][c] || 0; rec[c] = n; t += n }
    rec['合计'] = t
    return rec
  })
  const totalRow = { label: '合计' }
  for (const c of cols) totalRow[c] = colTotals[c] || 0
  totalRow['合计'] = grand
  outRows.push(totalRow)
  return { columns, rows: outRows }
}

const groupBySev = computed(() => buildCross(raw.value, 'group', 'severity'))
const customerBySev = computed(() => buildCross(raw.value, 'customer', 'severity'))
const yearMonthBySev = computed(() => buildCross(raw.value, 'year_month', 'severity'))

// ── ECharts ──────────────────────────────────────
const groupBarEl = ref(null)
const customerBarEl = ref(null)
const yearMonthBarEl = ref(null)
const trendEl = ref(null)
const inst = {}
function setChart(key, el, option) {
  if (!el) return
  if (!inst[key]) inst[key] = echarts.init(el)
  inst[key].setOption(option, { notMerge: true })
}

// 交叉表柱状图：x = 行标签（小组/客户面），按严重程度堆叠
// 排版：图例放顶部、grid 开 containLabel（旋转后的长标签计入绘图区，不再与图例/边缘重叠）
function crossBarOption(cross) {
  const { columns = [], rows = [] } = cross
  const cats = columns.filter((c) => c !== '合计')
  const xRows = rows.filter((r) => r.label !== '合计')
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: cats, top: 0, type: 'scroll' },
    grid: { top: 32, left: 8, right: 12, bottom: 4, containLabel: true },
    xAxis: {
      type: 'category',
      data: xRows.map((r) => r.label),
      axisLabel: {
        rotate: xRows.length > 5 ? 35 : 0,
        interval: 0,                       // 全量显示，不隔项省略
        fontSize: 11,
        width: 84, overflow: 'truncate',   // 超长名截断（tooltip 里仍是全名）
      },
    },
    yAxis: { type: 'value', minInterval: 1 },
    series: cats.map((c, i) => ({
      name: c, type: 'bar', stack: 'total', color: SEV_CLR[c] || PAL[i % PAL.length],
      data: xRows.map((r) => r[c] ?? 0),
    })),
  }
}

function trendLineOption(t) {
  const dates = t.dates || []
  const color = (name, i) => (trendDim.value === 'severity' ? (SEV_CLR[name] || PAL[i % PAL.length]) : PAL[i % PAL.length])
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['合计', ...(t.series || []).map((s) => s.name)], top: 0, type: 'scroll' },
    grid: { top: 34, left: 8, right: 16, bottom: 4, containLabel: true },
    xAxis: { type: 'category', data: dates, axisLabel: { rotate: dates.length > 8 ? 30 : 0, fontSize: 11 } },
    yAxis: { type: 'value', minInterval: 1, name: '缺陷数' },
    series: [
      {
        name: '合计', type: 'line', smooth: true, symbolSize: 8, lineStyle: { width: 2.5 },
        color: '#4073ba', data: t.total || [], areaStyle: { opacity: 0.05 },
      },
      ...(t.series || []).map((s, i) => ({
        name: s.name, type: 'line', smooth: true, symbolSize: 6, color: color(s.name, i), data: s.data,
      })),
    ],
  }
}

function renderSnapshotCharts() {
  if (groupBarEl.value) setChart('group', groupBarEl.value, crossBarOption(groupBySev.value))
  if (customerBarEl.value) setChart('customer', customerBarEl.value, crossBarOption(customerBySev.value))
  if (yearMonthBarEl.value) setChart('yearMonth', yearMonthBarEl.value, crossBarOption(yearMonthBySev.value))
}
function renderTrendChart() {
  if (trendEl.value && trend.value?.dates?.length) setChart('trend', trendEl.value, trendLineOption(trend.value))
}
function renderActive() {
  nextTick(() => {
    if (topTab.value === 'snapshot' && subTab.value === 'stats') renderSnapshotCharts()
    else if (topTab.value === 'trend') renderTrendChart()
    Object.values(inst).forEach((c) => c.resize())
  })
}
function onTopTabChange() {
  if (topTab.value === 'trend' && !trend.value) loadTrend()
  else if (topTab.value === 'logs') loadLogs()
  else renderActive()
}
function onSubTabChange() { renderActive() }

watch(statsView, () => nextTick(() => Object.values(inst).forEach((c) => c.resize())))

// ── 原始数据搜索 & 钻取 ──────────────────────────
const filtered = computed(() => {
  const kw = search.value.trim().toLowerCase()
  if (!kw) return raw.value
  return raw.value.filter((r) =>
    [r.title, r.issue_id, r.owner, r.group, r.department, r.customer].some((v) => (v || '').toLowerCase().includes(kw)),
  )
})

const drillVisible = ref(false)
const drillTitle = ref('')
const drillRows = ref([])
function openDrill(filters, title = '问题单明细') {
  let rows = raw.value
  if (filters.severity) rows = rows.filter((r) => r.severity === filters.severity)
  if (filters.group) rows = rows.filter((r) => (r.group || '未分组') === filters.group)
  if (filters.customer) rows = rows.filter((r) => (r.customer || '未标注') === filters.customer)
  if (filters.year_month) rows = rows.filter((r) => (r.year_month || '未标注') === filters.year_month)
  drillRows.value = rows
  drillTitle.value = title
  drillVisible.value = true
}
function onCellClick(rowDim, label, col, v) {
  if (!v) return
  const f = {}; const t = []
  if (label !== '合计') { f[rowDim] = label; t.push(label) }
  if (col !== '合计') { f.severity = col; t.push(col) }
  openDrill(f, t.join(' · ') || '全部')
}

// ── 手动采集（仅管理员；调后端定时同款采集逻辑，采完刷新）──
// 采集脚本要跑几分钟，而 axios 全局超时只有 10s。以前同步等结果必然先弹「采集失败」，
// 但后台其实跑完了 —— 这就是"报错后过会儿刷新数据又出来了"的原因。
// 现在后端起线程立即返回，这里轮询 collect-status 拿真实结果。
let _pollTimer = null
function stopPoll() {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null }
}

async function finishCollect(results) {
  collecting.value = false
  const r = (results || []).find((x) => x.project === props.project) || (results || [])[0]
  if (r && r.ok) {
    ElMessage.success(`采集完成：${r.total} 条（${r.date}）`)
    trend.value = null       // 让趋势下次进入时按最新数据重算
    selDate.value = ''       // 强制选中最新一天
    await loadSnapshots()
    if (topTab.value === 'trend') await loadTrend()
  } else {
    ElMessage.error(`采集失败：${(r && r.error) || '未知错误'}，详情见「采集日志」`)
  }
  if (topTab.value === 'logs') loadLogs()
}

async function pollCollect() {
  try {
    const { data } = await issueApi.collectStatus()
    if (!data.running) {
      stopPoll()
      await finishCollect(data.results)
    }
  } catch { /* 单次轮询失败继续下一轮 */ }
}

async function collectNow() {
  collecting.value = true
  try {
    await issueApi.snapshotCollect(props.project)
    ElMessage.info('已开始采集，可能需要几分钟，完成后自动刷新')
    stopPoll()
    _pollTimer = setInterval(pollCollect, 3000)
  } catch (e) {
    collecting.value = false
    ElMessage.error(e.response?.data?.detail || '采集启动失败')
  }
}

// ── 采集日志 ─────────────────────────────────────
const logs = ref([])
const logsLoading = ref(false)
async function loadLogs() {
  logsLoading.value = true
  try {
    const { data } = await issueApi.collectLogs(props.project, 50)
    logs.value = data || []
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '日志加载失败')
  } finally {
    logsLoading.value = false
  }
}

// ── 导出 Excel（原始数据 + 统计分析 两张表）──
async function doExport() {
  exporting.value = true
  try {
    const resp = await issueApi.snapshotExport(props.project, selDate.value || undefined)
    downloadBlob(resp.data, `问题单_${props.project}_${selDate.value || 'latest'}.xlsx`)
    ElMessage.success('已导出')
  } catch (e) {
    let msg = '导出失败'
    try {
      if (e.response?.data instanceof Blob) msg = JSON.parse(await e.response.data.text()).detail || msg
      else msg = e.response?.data?.detail || msg
    } catch { /* ignore */ }
    ElMessage.error(msg)
  } finally {
    exporting.value = false
  }
}

// ── 加载 ─────────────────────────────────────────
async function loadSnapshots() {
  loading.value = true
  try {
    const { data } = await issueApi.snapshotList(props.project)
    snapshots.value = data || []
    if (snapshots.value.length) {
      if (!selDate.value || !snapshots.value.find((s) => s.date === selDate.value)) {
        selDate.value = snapshots.value[0].date
      }
      await loadDetail()
    } else {
      detail.value = null
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

async function loadDetail() {
  if (!selDate.value) return
  try {
    const { data } = await issueApi.snapshotDetail(props.project, selDate.value)
    detail.value = data
    await nextTick()
    if (topTab.value === 'snapshot' && subTab.value === 'stats') renderSnapshotCharts()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  }
}

async function loadTrend() {
  try {
    const { data } = await issueApi.snapshotTrend(props.project, trendDim.value)
    trend.value = data
    await nextTick()
    renderTrendChart()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '趋势加载失败')
  }
}

function onResize() { Object.values(inst).forEach((c) => c.resize()) }

watch(() => props.project, () => {
  detail.value = null
  trend.value = null
  logs.value = []
  selDate.value = ''
  topTab.value = 'snapshot'
  loadSnapshots()
})
onMounted(() => {
  window.addEventListener('resize', onResize)
  loadSnapshots()
  // 别的页面/别人触发的采集也可能正在跑，进来就接上进度
  issueApi.collectStatus().then(({ data }) => {
    if (data.running) {
      collecting.value = true
      stopPoll()
      _pollTimer = setInterval(pollCollect, 3000)
    }
  }).catch(() => {})
})
onUnmounted(() => {
  stopPoll()
  Object.values(inst).forEach((c) => c.dispose())
  window.removeEventListener('resize', onResize)
})
</script>

<style scoped>
.api-panel { min-height: 200px; }
.api-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.muted { color: #909399; font-size: 13px; }
.err-text { color: #f56c6c; }

.snap-bar, .trend-bar { display: flex; align-items: center; gap: 10px; margin: 4px 0 14px; flex-wrap: wrap; }

/* 统计卡片 */
.stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 12px; }
.stat-card {
  background: #fff; border: 1px solid #eaecef; border-radius: 10px;
  padding: 16px 24px; cursor: pointer; text-align: center; transition: all .2s;
}
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 8px 20px -12px rgba(31,45,61,.3); border-color: #c6e2ff; }
.stat-num { font-size: 30px; font-weight: 700; color: #303133; line-height: 1.1; }
.stat-label { font-size: 13px; color: #909399; margin-top: 6px; }
.sev .stat-num { color: #f56c6c; } .sev:hover { border-color: #fab6b6; }
.nor .stat-num { color: #e6a23c; } .nor:hover { border-color: #f3d19e; }
.tip .stat-num { color: #909399; }

.main-card :deep(.el-card__body) { padding: 0 16px 16px; }

.stats-toolbar { display: flex; align-items: center; gap: 8px; padding: 12px 0 8px; }
.stats-toolbar-label { color: #606266; font-size: 13px; }

.section-title {
  font-size: 14px; font-weight: 600; color: #303133;
  margin: 12px 0 8px; padding-left: 8px; border-left: 3px solid #4073ba;
}

.chart-sm { width: 100%; height: 260px; }
.chart-sm.chart-wide { height: 380px; }
.chart-lg { width: 100%; height: 380px; margin-top: 8px; }

.raw-bar { display: flex; align-items: center; gap: 12px; margin: 8px 0 10px; }

/* 数字链接（StatsTable 子组件渲染，需穿透） */
:deep(.num-link) {
  color: #409EFF; font-weight: 600; cursor: pointer;
  padding: 2px 6px; border-radius: 4px; display: inline-block; min-width: 24px;
}
:deep(.num-link:hover) { background: #ecf5ff; }
:deep(.num-total) { color: #303133; font-weight: 700; display: inline-block; }
:deep(.num-zero) { color: #c0c4cc; }
</style>
