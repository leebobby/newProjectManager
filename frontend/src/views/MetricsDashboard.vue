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
          项目挂在需求行上（同一个迭代里排着多个项目的需求）；没填项目的行不计入任何一个项目，页面会提示去补
        </span>
      </div>

      <el-tabs v-model="active" @tab-change="onTabChange">
        <!-- ============ 版本质量：口径＝整个版本，跨迭代 ============ -->
        <el-tab-pane label="版本质量" name="version">
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
            <span class="muted">整个版本口径，跨迭代——版本是跨月的，按月截一刀会得到一个既不是这个版本、也不是这个月的数</span>
            <el-button :icon="Refresh" :disabled="!selectedVersionId" style="margin-left: auto"
              @click="loadVersion">刷新</el-button>
          </div>

          <ExclusionNote
            :unassigned="versionMetric?.unassigned || 0"
            :changed="versionMetric?.changed || 0"
            scope="该版本下"
          />

          <div v-if="versionMetric" class="metric-summary">
            <div class="stat">
              <div class="label">总需求<span class="hint">领域+产品</span></div>
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
              <div class="value">{{ versionMetric.total_code_volume.toLocaleString() }}</div>
            </div>
            <div class="stat">
              <div class="label">用例密度<span class="hint">个/kloc</span></div>
              <div class="value">{{ versionMetric.total_code_volume ? versionMetric.total_self_test_case_density : '—' }}</div>
            </div>
            <div class="stat">
              <div class="label">问题单密度<span class="hint">个/kloc</span></div>
              <div class="value danger">{{ versionMetric.total_code_volume ? versionMetric.total_post_test_issue_density : '—' }}</div>
            </div>
          </div>

          <!-- 按领域拆：质量字段只有领域需求有，所以这张表的条数比上面的总需求少
               （少的是产品需求）。表头写明白，否则会被当成丢数据。 -->
          <div class="block-head">
            <span class="block-title">按领域</span>
            <span class="muted">只数领域需求（产品需求没有 PL 组归属，也没有质量字段），所以合计比上面的「总需求」少</span>
            <div class="issue-src">
              <span class="muted">问题单快照：</span>
              <el-select v-model="issueProject" size="small" clearable placeholder="自动"
                style="width: 170px" @change="loadVersion">
                <el-option v-for="p in versionMetric?.issue_projects || []" :key="p.project"
                  :value="p.project" :label="p.project + (p.latest_date ? ` · ${p.latest_date}` : '（未采集）')" />
              </el-select>
            </div>
          </div>

          <!-- 匹配率显式标注：快照的「版本信息」是 DTS 的自由串，对不上是常态。
               不报匹配率的话，「这个版本怎么一个问题单都没有」没人说得清。 -->
          <el-alert v-if="versionMetric?.issues?.available" :closable="false" show-icon
            :type="matchRateType" style="margin-bottom: 10px">
            <template #title>
              {{ versionMetric.issues.project || '报表文件' }}
              {{ versionMetric.issues.stamp ? `（${versionMetric.issues.stamp}）` : '' }}
              共 {{ versionMetric.issues.total }} 条，按「版本信息」命中本版本
              <b>{{ versionMetric.issues.matched }}</b> 条（{{ pct(versionMetric.issues.match_rate) }}）
            </template>
            <template v-if="versionMetric.issues.unmatched_top.length" #default>
              <span class="muted">没命中的版本信息：{{ versionMetric.issues.unmatched_top.join('、') }}</span>
              <div class="muted">只做精确匹配（版本号 + 名下所有构建号）；模糊匹配会把 C10SPC101 认到 C10SPC1011 上，错挂的单在质量表里只是数字偏一点。</div>
            </template>
          </el-alert>
          <el-alert v-else-if="versionMetric" :closable="false" show-icon type="info" style="margin-bottom: 10px"
            :title="versionMetric.issues?.note || '没有可用的问题单数据源，「采集问题单」两列留空'" />

          <DomainQualityTable :rows="versionMetric?.by_domain || []" :loading="versionLoading" show-snapshot />

          <el-collapse class="detail-collapse">
            <el-collapse-item :title="`需求明细（${versionMetric?.items?.length || 0} 条）`" name="items">
              <el-table :data="versionMetric?.items || []" border stripe size="small">
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
            </el-collapse-item>
          </el-collapse>
        </el-tab-pane>

        <!-- ============ 领域质量：口径＝一个迭代（按月排活）============ -->
        <el-tab-pane label="领域质量" name="domain">
          <div class="bar">
            <el-select v-model="selectedYear" placeholder="年份" style="width: 130px" @change="onYearChange">
              <el-option v-for="y in years" :key="y" :value="y" :label="y + '年'" />
            </el-select>
            <el-select v-model="selectedIterationId" placeholder="选择月份" style="width: 220px"
              @change="loadIterationTab">
              <el-option v-for="it in iterations" :key="it.id" :value="it.id"
                :label="`${it.month}月 ${it.name || ''}`" />
            </el-select>
            <span class="muted">按迭代口径——领域是按月排活的，问「这个月各领域干得怎么样」才有意义</span>
            <el-button :icon="Refresh" :disabled="!selectedIterationId" style="margin-left: auto"
              @click="loadIterationTab">刷新</el-button>
          </div>

          <ExclusionNote
            :unassigned="domainQuality?.unassigned || 0"
            :changed="domainQuality?.changed || 0"
            scope="该迭代里"
          />

          <div v-if="domainQuality" class="metric-summary">
            <div class="stat">
              <div class="label">领域需求</div>
              <div class="value">{{ domainQuality.total }}</div>
            </div>
            <div class="stat">
              <div class="label">已完成</div>
              <div class="value primary">{{ domainQuality.done }}</div>
            </div>
            <div class="stat">
              <div class="label">平均完成度</div>
              <div class="value primary">{{ pct(domainQuality.avg_completion) }}</div>
            </div>
            <div class="stat">
              <div class="label">代码量(行)</div>
              <div class="value">{{ domainQuality.code_volume.toLocaleString() }}</div>
            </div>
            <div class="stat">
              <div class="label">用例密度<span class="hint">个/kloc</span></div>
              <div class="value">{{ domainQuality.code_volume ? domainQuality.self_test_case_density : '—' }}</div>
            </div>
            <div class="stat">
              <div class="label">问题单密度<span class="hint">个/kloc</span></div>
              <div class="value danger">{{ domainQuality.code_volume ? domainQuality.post_test_issue_density : '—' }}</div>
            </div>
          </div>

          <div class="block-head">
            <span class="block-title">按领域</span>
            <span class="muted">
              「转测后问题单」是需求行上人填的那一列。采集快照没有迭代维度（它是"当天还开着的单"），
              按月摊给某个迭代是编的，所以这里不放采集问题单——那两列在「版本质量」里。
            </span>
          </div>
          <DomainQualityTable :rows="domainQuality?.rows || []" :loading="domainLoading" />

          <el-collapse class="detail-collapse">
            <el-collapse-item title="本迭代交付概览（含产品需求 / 优先级分布）" name="iter">
              <div v-if="iterMetric" class="metric-summary">
                <div class="stat"><div class="label">领域需求</div><div class="value">{{ iterMetric.total_domain }}</div></div>
                <div class="stat"><div class="label">产品需求</div><div class="value">{{ iterMetric.total_product }}</div></div>
                <div class="stat"><div class="label">已完成</div><div class="value primary">{{ iterMetric.done_count }}</div></div>
                <div class="stat"><div class="label">已延期</div><div class="value danger">{{ iterMetric.delayed_count }}</div></div>
                <div class="stat"><div class="label">平均完成度</div><div class="value primary">{{ pct(iterMetric.avg_completion) }}</div></div>
              </div>
              <div class="priority-grid">
                <div v-for="(cnt, p) in iterMetric?.by_priority || {}" :key="p" class="prio-cell">
                  <div class="prio-label">{{ p }}</div>
                  <div class="prio-cnt">{{ cnt }}</div>
                </div>
              </div>
            </el-collapse-item>
            <el-collapse-item :title="`${selectedYear} 年逐迭代质量趋势`" name="trend">
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
            </el-collapse-item>
          </el-collapse>
        </el-tab-pane>

        <!-- ============ 组级负载 ============ -->
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
        <!-- ====== 问题单超期：各领域横向对比 ====== -->
        <el-tab-pane label="问题单超期" name="overdue">
          <div class="bar">
            <span class="project-label">问题单项目</span>
            <el-select v-model="overdueProject" style="width: 260px" @change="loadOverdue">
              <el-option
                v-for="p in overdue?.projects || []"
                :key="p.project"
                :value="p.project"
                :label="p.latest_date ? `${p.project} · ${p.latest_date}` : `${p.project}（未采集）`"
              />
            </el-select>
            <el-button :icon="Refresh" @click="loadOverdue">刷新</el-button>
            <!-- 顶部那个「度量项目」是需求上的项目 FK，跟这里的采集项目不是一回事。
                 不写明白的话，选了上面那个却什么都没变，看着像页面坏了。 -->
            <span class="muted">
              问题单按采集项目分快照，与顶部的「度量项目」不是同一个维度；
              <template v-if="overdue?.stamp">数据为 {{ overdue.stamp }} 那次采集的快照</template>
            </span>
          </div>

          <el-alert
            v-if="overdue && !overdue.available"
            type="info" show-icon :closable="false"
            :title="overdue.note || '还没有问题单快照'"
            description="到「问题单管理」里点一次「立即采集」之后这里就有数了。"
          />

          <template v-else-if="overdue">
            <div class="metric-summary">
              <div class="stat"><div class="label">在跟的单</div><div class="value primary">{{ overdue.total }}</div></div>
              <div class="stat">
                <div class="label">超期未处理</div>
                <div class="value" :class="overdue.overdue ? 'danger' : ''">{{ overdue.overdue }}</div>
              </div>
              <div class="stat">
                <div class="label">没填预计闭环时间</div>
                <div class="value">{{ overdue.overdue_unknown }}</div>
              </div>
            </div>

            <!-- 全都没填日期时说清楚"算不出"，别让人把 0 读成"一条都没超期" -->
            <el-alert
              v-if="overdue.total && overdue.overdue_unknown >= overdue.total"
              type="warning" show-icon :closable="false"
              title="这批单一条都没有「预计闭环时间」，超期数算不出来"
              description="DTS 该字段为空，或采集脚本的 FIELD_MAPPING 里还没映射上；见部署指南 4.1 ⑤。"
            />
            <el-alert
              v-else-if="overdue.overdue_unknown"
              type="info" show-icon :closable="false"
              :title="`另有 ${overdue.overdue_unknown} 条没填「预计闭环时间」，没有计入超期数`"
            />

            <el-table :data="overdue.rows" v-loading="overdueLoading" border stripe size="small">
              <el-table-column prop="group_name" label="领域" min-width="160">
                <template #default="{ row }">
                  {{ row.group_name }}
                  <!-- 「未归组」＝责任人不在任何名单里，跟"组还没建"是两回事：
                       提示要指向补名单，而不是让人去建一个根本不该存在的组 -->
                  <el-tooltip v-if="row.ungrouped" placement="top"
                    content="这些单的责任人不在任何小组名单里；到「问题单管理 → 配置 → 未归组责任人」补上名单，它们就会归到各自的领域">
                    <el-tag size="small" type="warning" effect="plain">名单缺人</el-tag>
                  </el-tooltip>
                  <el-tooltip v-else-if="row.group_id === null" placement="top"
                    content="名单里有这个组名，但组织架构里还没建这个 PL 组">
                    <el-tag size="small" type="info" effect="plain">未建组</el-tag>
                  </el-tooltip>
                </template>
              </el-table-column>
              <el-table-column prop="total" label="在跟的单" width="100" align="center" />
              <el-table-column label="超期未处理" width="120" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.overdue" type="danger" size="small">{{ row.overdue }}</el-tag>
                  <span v-else-if="row.overdue_unknown >= row.total" class="muted">算不出</span>
                  <span v-else class="muted">0</span>
                </template>
              </el-table-column>
              <el-table-column label="超期占比" min-width="180">
                <template #default="{ row }">
                  <!-- 用颜色而不是 status="exception"：后者把百分比换成一个 ✗ 图标，
                       而这一列的重点恰恰是那个数 -->
                  <el-progress
                    v-if="row.total > row.overdue_unknown"
                    :percentage="Math.round(row.overdue_rate * 100)"
                    :stroke-width="12"
                    :color="row.overdue_rate >= 0.3 ? '#f56c6c' : '#e6a23c'"
                  />
                  <span v-else class="muted">没有可比的基数</span>
                </template>
              </el-table-column>
              <el-table-column label="最久超了" width="110" align="center">
                <template #default="{ row }">
                  <span v-if="row.oldest_overdue_days" :class="{ danger: row.oldest_overdue_days >= 30 }">
                    {{ row.oldest_overdue_days }} 天
                  </span>
                  <span v-else class="muted">—</span>
                </template>
              </el-table-column>
              <el-table-column label="没填计划时间" width="120" align="center">
                <template #default="{ row }">
                  <span :class="{ muted: !row.overdue_unknown }">{{ row.overdue_unknown }}</span>
                </template>
              </el-table-column>
            </el-table>
          </template>
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
  annualIterationApi, apiError, majorVersionApi, metricsApi, resourceGroupApi, roadmapApi,
} from '../api'
import DomainQualityTable from '../components/metrics/DomainQualityTable.vue'

const active = ref('version')

const pct = (v) => `${Math.round((v || 0) * 100)}%`

// ── 问题单超期：各领域横向对比 ────────────────────────────────
// 数据源与口径都与领域管理共用一份（后端 _issue_source），两处各写一份的表现是
// 同一个组在两个页面上超期数不一样，而两边看着都像对的。
const overdue = ref(null)
const overdueLoading = ref(false)
const overdueProject = ref('')

async function loadOverdue() {
  overdueLoading.value = true
  try {
    const { data } = await metricsApi.issueOverdue(overdueProject.value)
    overdue.value = data
    // 首次进来由服务端挑一个有快照的项目，回填到选择器里
    if (!overdueProject.value && data.project) overdueProject.value = data.project
  } catch (e) {
    ElMessage.error(apiError(e, '加载超期统计失败'))
  } finally {
    overdueLoading.value = false
  }
}

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
  loadIterationTab()
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

// 问题单快照取哪个项目：留空＝后端挑第一个有快照的。指定的项目没有快照时后端
// 如实回不可用，**不会静默换成别的项目的数字**——那种错没人看得出来。
const issueProject = ref('')

// 匹配率的配色：低命中率多半是版本命名没对上，得让人一眼看见，而不是当成"没问题单"
const matchRateType = computed(() => {
  const r = versionMetric.value?.issues?.match_rate ?? 0
  if (r >= 0.6) return 'success'
  return r > 0 ? 'warning' : 'error'
})

async function loadVersion() {
  if (!selectedVersionId.value) return
  versionLoading.value = true
  try {
    const params = { ...projectParams() }
    if (issueProject.value) params.issue_project = issueProject.value
    const { data } = await metricsApi.version(selectedVersionId.value, params)
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
const domainQuality = ref(null)
const domainLoading = ref(false)
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
        await loadIterationTab()
      }
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载迭代失败')
  }
}

// 领域质量（按领域分行）与交付概览是同一个迭代的两面，一起加载：
// 分开触发的话，切月份时两块会一先一后地跳，看着像其中一块没跟上。
async function loadIterationTab() {
  if (!selectedIterationId.value) return
  domainLoading.value = true
  try {
    const [q, m] = await Promise.all([
      metricsApi.domainQuality(selectedIterationId.value, projectParams()),
      metricsApi.iteration(selectedIterationId.value, projectParams()),
    ])
    domainQuality.value = q.data
    iterMetric.value = m.data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    domainLoading.value = false
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

// 调试版本看板搬到「版本管理 → 现场调试版本」了：它是按客户×月统计的，
// 和这里的三个（版本 / 领域 / 组）不是一个维度，混在一起正是"看板有点乱"的来源之一。

// 切到「问题单超期」才去读快照：那份明细在文件里，没人看的时候不该白读一遍
function onTabChange(name) {
  if (name === 'overdue' && !overdue.value) loadOverdue()
}

onMounted(async () => {
  // 项目下拉先到位：loadYears() 会顺带拉当月迭代的数字，晚了就得再算一遍
  await loadProjects()
  await Promise.all([loadVersionList(), loadYears(), loadGroupList()])
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
/* 超期天数用同一套红：30 天以上的单独标出来——2 条超 200 天比 5 条超 2 天更该先看 */
.danger { color: #f56c6c; font-weight: 600; }
.block-title { font-weight: 600; color: #303133; }
/* 「按领域」表上方那一行：标题 + 口径说明 + 问题单来源选择挤在一行，窄屏时换行不错位 */
.block-head {
  display: flex;
  gap: 10px;
  align-items: baseline;
  flex-wrap: wrap;
  margin: 18px 0 8px;
}
.block-head .muted { font-size: 12px; flex: 1 1 320px; line-height: 1.6; }
.issue-src { display: flex; gap: 6px; align-items: center; margin-left: auto; }
/* 明细/趋势收进折叠面板：默认收起，看板一屏之内先给结论，要细节再展开 */
.detail-collapse { margin-top: 14px; }
.stat .label .hint { color: #c0c4cc; margin-left: 4px; }
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
