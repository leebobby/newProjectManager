<template>
  <div>
    <el-card shadow="never">
      <el-tabs v-model="active">
        <!-- 版本完成率 -->
        <el-tab-pane label="版本完成率" name="version">
          <div class="bar">
            <el-select
              v-model="selectedVersionId"
              filterable
              clearable
              placeholder="选择大版本"
              style="width: 280px"
              @change="loadVersion"
            >
              <el-option
                v-for="v in versions"
                :key="v.id"
                :value="v.id"
                :label="`${v.version_no}${v.title ? ' — ' + v.title : ''}`"
              />
            </el-select>
            <el-button :icon="Refresh" :disabled="!selectedVersionId" @click="loadVersion">刷新</el-button>
          </div>

          <div v-if="versionMetric" class="metric-summary">
            <div class="stat">
              <div class="label">总需求</div>
              <div class="value">{{ versionMetric.total }}</div>
            </div>
            <div class="stat">
              <div class="label">已完成</div>
              <div class="value primary">{{ versionMetric.done }}</div>
            </div>
            <div class="stat">
              <div class="label">平均完成度</div>
              <div class="value primary">{{ pct(versionMetric.avg_completion) }}</div>
            </div>
            <div class="stat">
              <div class="label">代码量(行)</div>
              <div class="value">{{ versionMetric.total_code_volume }}</div>
            </div>
            <div class="stat">
              <div class="label">自验证用例数</div>
              <div class="value">{{ versionMetric.total_self_test_cases }}</div>
            </div>
            <div class="stat">
              <div class="label">转测后问题单</div>
              <div class="value danger">{{ versionMetric.total_post_test_issues }}</div>
            </div>
          </div>

          <el-table :data="versionMetric?.items || []" v-loading="versionLoading" border stripe size="small">
            <el-table-column label="类型" width="80">
              <template #default="{ row }">
                <el-tag size="small" :type="row.kind === 'domain' ? 'primary' : 'success'">
                  {{ row.kind === 'domain' ? '领域' : '产品' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="需求标题" min-width="240" />
            <el-table-column label="完成度" width="160">
              <template #default="{ row }">
                <el-progress
                  :percentage="Math.round(row.completion * 100)"
                  :status="row.is_done ? 'success' : ''"
                  :stroke-width="14"
                />
              </template>
            </el-table-column>
            <el-table-column label="状态" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.is_done ? 'success' : 'info'" size="small">
                  {{ row.is_done ? '完成' : '进行中' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 迭代质量 -->
        <el-tab-pane label="迭代质量" name="iteration">
          <div class="bar">
            <el-select
              v-model="selectedYear"
              placeholder="年份"
              style="width: 140px"
              @change="onYearChange"
            >
              <el-option v-for="y in years" :key="y" :value="y" :label="y + '年'" />
            </el-select>
            <el-select
              v-model="selectedIterationId"
              placeholder="选择月份"
              style="width: 240px"
              clearable
              @change="loadIteration"
            >
              <el-option
                v-for="it in iterations"
                :key="it.id"
                :value="it.id"
                :label="`${it.month}月 ${it.name || ''}`"
              />
            </el-select>
            <el-button :icon="Refresh" :disabled="!selectedIterationId" @click="loadIteration">刷新</el-button>
          </div>

          <div v-if="iterMetric" class="metric-summary">
            <div class="stat"><div class="label">领域需求</div><div class="value">{{ iterMetric.total_domain }}</div></div>
            <div class="stat"><div class="label">产品需求</div><div class="value">{{ iterMetric.total_product }}</div></div>
            <div class="stat"><div class="label">已完成</div><div class="value primary">{{ iterMetric.done_count }}</div></div>
            <div class="stat"><div class="label">已延期</div><div class="value danger">{{ iterMetric.delayed_count }}</div></div>
            <div class="stat"><div class="label">平均完成度</div><div class="value primary">{{ pct(iterMetric.avg_completion) }}</div></div>
          </div>

          <el-card v-if="iterMetric" shadow="never" style="margin-top: 12px">
            <div class="block-title">按优先级分布</div>
            <div class="priority-grid">
              <div v-for="(cnt, p) in iterMetric.by_priority" :key="p" class="prio-cell">
                <div class="prio-label">{{ p }}</div>
                <div class="prio-cnt">{{ cnt }}</div>
              </div>
            </div>
          </el-card>

          <el-card shadow="never" style="margin-top: 12px">
            <div class="block-title">{{ selectedYear }} 年各迭代质量（领域需求汇总）</div>
            <el-table :data="qualityRows" v-loading="qualityLoading" border stripe size="small">
              <el-table-column label="迭代" min-width="140">
                <template #default="{ row }">
                  {{ row.month }}月{{ row.name ? ' · ' + row.name : '' }}
                </template>
              </el-table-column>
              <el-table-column label="代码量(行)" width="110" align="right">
                <template #default="{ row }">{{ row.code_volume.toLocaleString() }}</template>
              </el-table-column>
              <el-table-column label="自验证用例数" width="120" align="right">
                <template #default="{ row }">{{ row.self_test_cases }}</template>
              </el-table-column>
              <el-table-column label="用例密度(个/kloc)" width="150" align="right">
                <template #default="{ row }">
                  <span :class="row.code_volume ? '' : 'muted'">
                    {{ row.code_volume ? row.self_test_case_density : '—' }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="转测后问题单" width="120" align="right">
                <template #default="{ row }">{{ row.post_test_issues }}</template>
              </el-table-column>
              <el-table-column label="问题单密度(个/kloc)" width="160" align="right">
                <template #default="{ row }">
                  <span :class="row.code_volume ? '' : 'muted'">
                    {{ row.code_volume ? row.post_test_issue_density : '—' }}
                  </span>
                </template>
              </el-table-column>
            </el-table>
            <div class="quality-tip">
              密度 = 数量 ÷ (代码量 / 1000)；代码量为空的迭代不计算密度。数据来源于领域需求页填报的版本质量统计。
            </div>
          </el-card>
        </el-tab-pane>

        <!-- 组级负载 -->
        <el-tab-pane label="组级负载" name="group">
          <div class="bar">
            <el-select
              v-model="selectedGroupId"
              placeholder="选择 PL 组"
              filterable
              style="width: 280px"
              @change="loadGroup"
            >
              <el-option
                v-for="g in groups"
                :key="g.id"
                :value="g.id"
                :label="`${g.parent_name || '—'} / ${g.name}`"
              />
            </el-select>
            <el-select v-model="groupYear" clearable placeholder="按年度过滤" style="width: 140px" @change="loadGroup">
              <el-option v-for="y in years" :key="y" :value="y" :label="y + '年'" />
            </el-select>
            <el-button :icon="Refresh" :disabled="!selectedGroupId" @click="loadGroup">刷新</el-button>
          </div>

          <div v-if="groupMetric" class="metric-summary">
            <div class="stat"><div class="label">未完成数</div><div class="value primary">{{ groupMetric.total_open }}</div></div>
            <div class="stat"><div class="label">已延期</div><div class="value danger">{{ groupMetric.delayed }}</div></div>
            <div class="stat"><div class="label">平均完成度</div><div class="value primary">{{ pct(groupMetric.avg_completion) }}</div></div>
          </div>

          <el-table :data="groupMetric?.by_member || []" v-loading="groupLoading" border stripe size="small">
            <el-table-column prop="full_name" label="姓名" width="140" />
            <el-table-column label="未完成" width="110" align="center">
              <template #default="{ row }">{{ row.open_count }}</template>
            </el-table-column>
            <el-table-column label="已延期" width="110" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.delayed_count" type="danger" size="small">{{ row.delayed_count }}</el-tag>
                <span v-else class="muted">0</span>
              </template>
            </el-table-column>
            <el-table-column label="平均完成度" min-width="200">
              <template #default="{ row }">
                <el-progress :percentage="Math.round(row.avg_completion * 100)" :stroke-width="12" />
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 调试版本（现场使用看板） -->
        <el-tab-pane label="调试版本" name="debug">
          <div class="bar">
            <span class="muted">按月统计现场调试版本数量与目标客户分布（月份口径＝发布时间，缺失用计划发布时间）</span>
            <el-button :icon="Refresh" style="margin-left: auto" @click="loadDebug">刷新</el-button>
          </div>

          <div v-if="debugStat" class="metric-summary">
            <div class="stat"><div class="label">调试版本总数</div><div class="value primary">{{ debugTotal }}</div></div>
            <div class="stat"><div class="label">涉及目标客户</div><div class="value">{{ debugStat.customers.length }}</div></div>
            <div class="stat"><div class="label">统计月份数</div><div class="value">{{ debugStat.months.length }}</div></div>
          </div>

          <el-table :data="debugStat?.months || []" v-loading="debugLoading" border stripe size="small">
            <el-table-column prop="month" label="月份" width="120" fixed />
            <el-table-column
              v-for="c in debugStat?.customers || []"
              :key="c"
              :label="c"
              min-width="110"
              align="center"
            >
              <template #default="{ row }">
                <span v-if="row.by_customer[c]">{{ row.by_customer[c] }}</span>
                <span v-else class="muted">·</span>
              </template>
            </el-table-column>
            <el-table-column label="合计" width="90" align="center" fixed="right">
              <template #default="{ row }"><b>{{ row.total }}</b></template>
            </el-table-column>
          </el-table>
          <div v-if="debugStat && !debugStat.months.length" class="quality-tip">
            暂无调试版本数据。去「版本管理 → 现场调试版本」录入后即可统计。
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { annualIterationApi, debugVersionApi, majorVersionApi, metricsApi, resourceGroupApi } from '../api'

const active = ref('version')

const pct = (v) => `${Math.round((v || 0) * 100)}%`

// 版本
const versions = ref([])
const selectedVersionId = ref(null)
const versionMetric = ref(null)
const versionLoading = ref(false)

async function loadVersionList() {
  try {
    const { data } = await majorVersionApi.list()
    versions.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载版本列表失败')
  }
}

async function loadVersion() {
  if (!selectedVersionId.value) return
  versionLoading.value = true
  try {
    const { data } = await metricsApi.version(selectedVersionId.value)
    versionMetric.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    versionLoading.value = false
  }
}

// 迭代
const years = ref([])
const selectedYear = ref(new Date().getFullYear())
const iterations = ref([])
const selectedIterationId = ref(null)
const iterMetric = ref(null)
const qualityRows = ref([])
const qualityLoading = ref(false)

async function loadYears() {
  try {
    const { data } = await annualIterationApi.years()
    years.value = data
    if (!data.includes(selectedYear.value)) selectedYear.value = data[0]
    await onYearChange()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载年份失败')
  }
}

async function loadQuality() {
  if (!selectedYear.value) return
  qualityLoading.value = true
  try {
    const { data } = await metricsApi.iterationQuality(selectedYear.value)
    qualityRows.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载迭代质量失败')
  } finally {
    qualityLoading.value = false
  }
}

async function onYearChange() {
  if (!selectedYear.value) return
  loadQuality()
  try {
    const { data } = await annualIterationApi.list(selectedYear.value)
    iterations.value = data
    // 默认选当前月
    const now = new Date()
    if (selectedYear.value === now.getFullYear()) {
      const m = data.find((i) => i.month === now.getMonth() + 1)
      if (m) {
        selectedIterationId.value = m.id
        await loadIteration()
      }
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载迭代失败')
  }
}

async function loadIteration() {
  if (!selectedIterationId.value) return
  try {
    const { data } = await metricsApi.iteration(selectedIterationId.value)
    iterMetric.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  }
}

// 组
const groups = ref([])
const selectedGroupId = ref(null)
const groupYear = ref(null)
const groupMetric = ref(null)
const groupLoading = ref(false)

async function loadGroupList() {
  try {
    const { data } = await resourceGroupApi.list({ kind: 'pl' })
    groups.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载组列表失败')
  }
}

async function loadGroup() {
  if (!selectedGroupId.value) return
  groupLoading.value = true
  try {
    const params = groupYear.value ? { year: groupYear.value } : {}
    const { data } = await metricsApi.group(selectedGroupId.value, params)
    groupMetric.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    groupLoading.value = false
  }
}

// 调试版本看板
const debugStat = ref(null)
const debugLoading = ref(false)
const debugTotal = computed(() => (debugStat.value?.months || []).reduce((s, m) => s + m.total, 0))

async function loadDebug() {
  debugLoading.value = true
  try {
    const { data } = await debugVersionApi.dashboard()
    debugStat.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载调试版本看板失败')
  } finally {
    debugLoading.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadVersionList(), loadYears(), loadGroupList(), loadDebug()])
})
</script>

<style scoped>
.bar { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.metric-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.stat {
  background: #f8fafc;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 12px 16px;
  text-align: center;
}
.stat .label { color: #909399; font-size: 12px; }
.stat .value { font-size: 24px; font-weight: 600; color: #303133; }
.stat .value.primary { color: #409eff; }
.stat .value.danger { color: #f56c6c; }
.block-title { font-weight: 600; margin-bottom: 8px; color: #303133; }
.priority-grid { display: flex; gap: 8px; flex-wrap: wrap; }
.prio-cell {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 8px 16px;
  background: #fafafa;
  min-width: 80px;
  text-align: center;
}
.prio-label { color: #909399; font-size: 12px; }
.prio-cnt { font-size: 18px; font-weight: 600; color: #303133; }
.muted { color: #c0c4cc; }
.quality-tip { margin-top: 10px; color: #909399; font-size: 12px; line-height: 1.6; }
</style>
