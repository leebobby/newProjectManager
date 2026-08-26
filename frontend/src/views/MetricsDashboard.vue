<template>
  <div>
    <el-card shadow="never">
      <div class="project-bar">
        <span class="project-label">度量项目</span>
        <el-select
          v-model="projectId"
          placeholder="全部项目"
          clearable
          filterable
          style="width: 220px"
          @change="onProjectChange"
        >
          <el-option v-for="p in projects" :key="p.id" :value="p.id" :label="p.name" />
        </el-select>
        <span class="muted">
          项目挂在需求行上（同一个迭代里排着多个项目的需求）；调试版本看板按客户统计，不受此处影响
        </span>
      </div>

      <el-tabs v-model="active">
        <!-- 版本完成率 -->
        <el-tab-pane label="版本完成率" name="version">
          <div class="bar">
            <el-select
              v-model="selectedVersionId"
              filterable
              clearable
              placeholder="选择版本"
              style="width: 320px"
              @change="loadVersion"
            >
              <el-option
                v-for="v in versions"
                :key="v.id"
                :value="v.id"
                :label="`${v.major_version_no ? v.major_version_no + ' / ' : ''}${v.version_no}${v.title ? ' — ' + v.title : ''}`"
              />
            </el-select>
            <el-button :icon="Refresh" :disabled="!selectedVersionId" @click="loadVersion">刷新</el-button>
          </div>

          <ExclusionNote
            :unassigned="versionMetric?.unassigned || 0"
            :changed="versionMetric?.changed || 0"
            scope="该版本下"
          />

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

          <ExclusionNote
            :unassigned="iterMetric?.unassigned || 0"
            :changed="iterMetric?.changed || 0"
            scope="该迭代里"
          />

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
              <el-table-column label="已变更" width="90" align="right">
                <template #default="{ row }">
                  <span :class="row.changed ? '' : 'muted'">{{ row.changed || '—' }}</span>
                </template>
              </el-table-column>
            </el-table>
            <div class="quality-tip">
              密度 = 数量 ÷ (代码量 / 1000)；代码量为空的迭代不计算密度。数据来源于领域需求页填报的版本质量统计。
              标了「已变更」的需求整行不计入（分子分母一起剔），「已变更」列是本年度各迭代被剔掉的条数。
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

          <ExclusionNote
            :unassigned="groupMetric?.unassigned || 0"
            :changed="groupMetric?.changed || 0"
            scope="该组名下"
          />

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
import { computed, defineComponent, h, onMounted, ref } from 'vue'
import { ElAlert, ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import {
  annualIterationApi, debugVersionApi, majorVersionApi, metricsApi, resourceGroupApi, roadmapApi,
} from '../api'

const active = ref('version')

const pct = (v) => `${Math.round((v || 0) * 100)}%`

// 有两种行会被排除在统计之外：标了「已变更」的（本轮不做了，后端 _split_changed）、
// 按项目筛时没填项目的（后端 _split_by_project）。这条提示是那两个口径的配套：
// 数字偏小是有原因的，让人看得见、知道去哪补，而不是对着一个说不清的数发愣。
// 两个数都为 0 时整条不渲染。
const ExclusionNote = defineComponent({
  props: {
    unassigned: { type: Number, default: 0 },
    changed: { type: Number, default: 0 },
    scope: { type: String, default: '' },
  },
  setup(props) {
    return () => {
      const lines = []
      if (props.changed) {
        lines.push(`${props.scope}有 ${props.changed} 条需求标了「已变更」，已整行排除`)
      }
      if (props.unassigned) {
        lines.push(`${props.scope}还有 ${props.unassigned} 条需求没填项目，未计入本次统计`)
      }
      if (!lines.length) return null
      return h(ElAlert, {
        type: 'warning',
        showIcon: true,
        closable: false,
        style: 'margin-bottom: 12px',
        title: lines.join('；'),
        description: props.unassigned
          ? '去「迭代管理 → 对应迭代」的需求列表里补选项目后，数字才会完整。'
          : '已变更的需求在迭代管理里是置灰的，本就不参与度量。',
      })
    }
  },
})

// ── 项目维度（作用于版本 / 迭代 / 组级三个 tab）──
const projects = ref([])
const projectId = ref(null)

async function loadProjects() {
  try {
    const { data } = await roadmapApi.listProjects()
    projects.value = data.map((p) => ({ id: p.id, name: p.name }))
  } catch (e) {
    /* 下拉为空不阻塞，等同于「全部项目」 */
  }
}

// 项目参数：三个 tab 共用一份，避免各自拼一遍口径漂移
const projectParams = () => (projectId.value ? { project_id: projectId.value } : {})

function onProjectChange() {
  // 换项目后已经展示着的数字全都过期了，一次性重算，别让人以为某个 tab 没跟着变
  loadVersion()
  loadIteration()
  loadQuality()
  loadGroup()
}

// 版本
const versions = ref([])
const selectedVersionId = ref(null)
const versionMetric = ref(null)
const versionLoading = ref(false)

async function loadVersionList() {
  // 达成率看「版本」（C10SPC101）——需求填的是它下面的构建号，后端按版本汇总。
  // 原来这里用 majorVersionApi.list()，那个接口不带 project_id 时只返回未挂项目的
  // 大版本，实际是个空列表。
  try {
    const { data } = await majorVersionApi.allReleaseVersions()
    versions.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载版本列表失败')
  }
}

async function loadVersion() {
  if (!selectedVersionId.value) return
  versionLoading.value = true
  try {
    const { data } = await metricsApi.version(selectedVersionId.value, projectParams())
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
    const { data } = await metricsApi.iterationQuality(selectedYear.value, projectParams())
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
    const { data } = await metricsApi.iteration(selectedIterationId.value, projectParams())
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
    const params = { ...projectParams() }
    if (groupYear.value) params.year = groupYear.value
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
  // 项目下拉先到位：loadYears() 会顺带拉当月迭代的数字，晚了就得再算一遍
  await loadProjects()
  await Promise.all([loadVersionList(), loadYears(), loadGroupList(), loadDebug()])
})
</script>

<style scoped>
.bar { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.project-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  padding-bottom: 12px;
  margin-bottom: 4px;
  border-bottom: 1px solid #ebeef5;
}
.project-label { font-weight: 600; color: #303133; }
.project-bar .muted { font-size: 12px; }
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
