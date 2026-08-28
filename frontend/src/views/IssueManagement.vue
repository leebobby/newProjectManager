<template>
  <div class="issue-page">
    <el-tabs v-model="topTab" class="issue-top-tabs">
      <!-- 各项目：通过 API 拉取（懒加载，切到该 tab 才请求；顺序由管理员配置） -->
      <el-tab-pane v-for="proj in apiProjects" :key="proj" :label="proj" :name="proj">
        <IssueApiPanel v-if="topTab === proj" :project="proj" />
      </el-tab-pane>

      <el-tab-pane label="历史数据" name="local">

    <!-- ── 模式切换栏 ────────────────────────────────── -->
    <div class="mode-bar">
      <el-button-group>
        <el-button :type="mode==='today'  ? 'primary' : ''" @click="switchMode('today')">
          <el-icon><DataLine /></el-icon> 当天数据
        </el-button>
        <el-button :type="mode==='trend'  ? 'primary' : ''" @click="switchMode('trend')">
          <el-icon><TrendCharts /></el-icon> 查看趋势
        </el-button>
      </el-button-group>

      <!-- 日期选择器（当天数据模式） -->
      <el-select
        v-if="mode==='today' && availableDates.length"
        v-model="selectedDate"
        placeholder="选择日期"
        size="small"
        style="width:150px"
        @change="onDateChange"
      >
        <el-option
          v-for="d in availableDates"
          :key="d"
          :label="d"
          :value="d"
        />
      </el-select>

      <span v-if="fileHint" class="file-hint">
        <el-icon><Document /></el-icon> {{ fileHint }}
      </span>

      <el-button
        v-if="todayData?.raw"
        type="success"
        :icon="Download"
        :loading="exporting"
        style="margin-left:auto"
        @click="exportPptx"
      >导出 PPT</el-button>
    </div>

    <!-- ══════════════════════════════════════════════ -->
    <!-- 模式 1：当天数据                                -->
    <!-- ══════════════════════════════════════════════ -->
    <template v-if="mode==='today'">
      <div v-if="loading" class="hint">加载中…</div>
      <el-empty v-else-if="!todayData?.configured" description="请配置报表目录" />

      <template v-else-if="todayData?.raw">
        <!-- 统计卡片 -->
        <div class="stat-row">
          <div class="stat-card" @click="openDrill({}, '全部问题单')">
            <div class="stat-num">{{ todayData.raw.length }}</div>
            <div class="stat-label">合计</div>
          </div>
          <div class="stat-card sev" @click="openDrill({severity:'严重'},'严重缺陷')">
            <div class="stat-num">{{ countBy('severity','严重') }}</div>
            <div class="stat-label">严重</div>
          </div>
          <div class="stat-card nor" @click="openDrill({severity:'一般'},'一般缺陷')">
            <div class="stat-num">{{ countBy('severity','一般') }}</div>
            <div class="stat-label">一般</div>
          </div>
          <div class="stat-card tip" @click="openDrill({severity:'提示'},'提示缺陷')">
            <div class="stat-num">{{ countBy('severity','提示') }}</div>
            <div class="stat-label">提示</div>
          </div>
        </div>

        <!-- 主内容 -->
        <el-card shadow="never" class="main-card">
          <el-tabs v-model="subTab" @tab-change="onSubTabChange">

            <!-- 统计明细（表格 + 直方图） -->
            <el-tab-pane label="统计明细" name="stats">
              <!-- 视图切换 -->
              <div class="stats-toolbar">
                <span class="stats-toolbar-label">视图：</span>
                <el-button-group size="small">
                  <el-button :type="statsView==='both' ? 'primary' : ''" @click="statsView='both'">双视图</el-button>
                  <el-button :type="statsView==='table' ? 'primary' : ''" @click="statsView='table'">表格</el-button>
                  <el-button :type="statsView==='chart' ? 'primary' : ''" @click="statsView='chart'">图表</el-button>
                </el-button-group>
              </div>

              <!-- 按小组×月度 -->
              <div class="section-title">按小组 × 月度</div>
              <el-row :gutter="16">
                <el-col v-show="statsView !== 'chart'" :span="statsView === 'both' ? 14 : 24">
                  <StatsTable
                    :columns="todayData.monthly_by_group.columns"
                    :rows="todayData.monthly_by_group.rows"
                    @cell-click="(r,c,v)=>onMonthlyClick(r,c,v)"
                  />
                </el-col>
                <el-col v-show="statsView !== 'table'" :span="statsView === 'both' ? 10 : 24">
                  <div ref="monthlyBarEl" class="chart-sm" :class="{ 'chart-wide': statsView === 'chart' }" />
                </el-col>
              </el-row>

              <!-- 按客户分布 -->
              <div class="section-title" style="margin-top:20px">按客户分布</div>
              <el-row :gutter="16">
                <el-col v-show="statsView !== 'chart'" :span="statsView === 'both' ? 14 : 24">
                  <StatsTable
                    :columns="todayData.by_customer.columns"
                    :rows="todayData.by_customer.rows"
                    @cell-click="(r,c,v)=>onCustomerClick(r,c,v)"
                  />
                </el-col>
                <el-col v-show="statsView !== 'table'" :span="statsView === 'both' ? 10 : 24">
                  <div ref="customerBarEl" class="chart-sm" :class="{ 'chart-wide': statsView === 'chart' }" />
                </el-col>
              </el-row>

              <!-- 特性×小组 —— 暂不展示，待 Excel 增加该数据后开启 -->
              <template v-if="SHOW_FEATURE">
                <div class="section-title" style="margin-top:20px">特性 × 小组</div>
                <el-row :gutter="16">
                  <el-col v-show="statsView !== 'chart'" :span="statsView === 'both' ? 14 : 24">
                    <StatsTable
                      :columns="todayData.feature_by_group.columns"
                      :rows="todayData.feature_by_group.rows"
                      @cell-click="(r,c,v)=>onFeatureClick(r,c,v)"
                    />
                  </el-col>
                  <el-col v-show="statsView !== 'table'" :span="statsView === 'both' ? 10 : 24">
                    <div ref="featureBarEl" class="chart-sm" :class="{ 'chart-wide': statsView === 'chart' }" />
                  </el-col>
                </el-row>
              </template>
            </el-tab-pane>

            <!-- 原始数据 -->
            <el-tab-pane label="原始数据" name="raw">
              <div class="raw-toolbar">
                <el-input v-model="rawSearch" :prefix-icon="Search" clearable
                          placeholder="搜索标题 / 编号 / 责任人 / 小组" style="width:300px" />
                <span class="raw-count">共 {{ filteredRaw.length }} 条</span>
              </div>
              <IssueTable :data="filteredRaw" max-height="540" />
            </el-tab-pane>

          </el-tabs>
        </el-card>
      </template>
    </template>

    <!-- ══════════════════════════════════════════════ -->
    <!-- 模式 2：查看趋势                                -->
    <!-- ══════════════════════════════════════════════ -->
    <template v-else-if="mode==='trend'">
      <div v-if="trendLoading" class="hint">正在汇总所有报表文件…</div>
      <el-empty v-else-if="!trendData" description="暂无趋势数据" />
      <template v-else>
        <el-card shadow="never" class="detail-card">
          <template #header>
            <span class="card-title">每日缺陷趋势 · 按小组</span>
            <span class="card-hint">共 {{ trendData.daily.length }} 个报表文件</span>
          </template>
          <div ref="trendGroupEl" class="chart-lg" />
        </el-card>
        <el-card shadow="never" class="detail-card">
          <template #header><span class="card-title">每日缺陷趋势 · 按严重程度</span></template>
          <div ref="trendSeverityEl" class="chart-lg" />
        </el-card>
        <!-- 数据明细表 -->
        <el-card shadow="never" class="detail-card">
          <template #header><span class="card-title">每日数据明细</span></template>
          <el-table :data="trendData.daily" border stripe size="small" max-height="400">
            <el-table-column prop="date" label="日期" width="120" align="center" />
            <el-table-column prop="file" label="文件" min-width="260" show-overflow-tooltip />
            <el-table-column prop="total" label="合计" width="80" align="center" />
            <el-table-column
              v-for="g in trendData.all_groups" :key="g" :label="g" width="120" align="center"
            >
              <template #default="{ row }">{{ row.by_group[g] ?? 0 }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </template>
    </template>

    <!-- ══════════════════════════════════════════════ -->
    <!-- 模式 3：实时刷新（仅管理员）                     -->
    <!-- ══════════════════════════════════════════════ -->
    <template v-else-if="mode==='script' && isAdmin">
      <el-card shadow="never">
        <template #header><span class="card-title"><el-icon><VideoPlay /></el-icon> 执行刷新脚本</span></template>
        <p class="script-tip">
          脚本路径已在上方管理员配置区设置（issue_script_path）。
          点击「执行」后系统将运行该脚本，执行完毕后可点「查看最新数据」切换至当天数据视图。
        </p>
        <el-alert
          v-if="remoteRunning && !scriptRunning"
          type="warning"
          :title="`脚本正在执行中，请等待完成后再操作${remoteStartedAt ? '（开始于 ' + new Date(remoteStartedAt).toLocaleTimeString() + '）' : ''}`"
          show-icon :closable="false"
          style="margin-bottom:14px"
        />
        <el-button
          type="danger" size="large"
          :loading="scriptRunning"
          :disabled="remoteRunning && !scriptRunning"
          :icon="VideoPlay"
          @click="doRunScript"
        >
          执行脚本
        </el-button>
        <template v-if="scriptResult">
          <el-divider />
          <el-alert
            :type="scriptResult.ok ? 'success' : 'error'"
            :title="scriptResult.ok ? `执行成功（退出码 ${scriptResult.exit_code}）` : `执行失败（退出码 ${scriptResult.exit_code}）`"
            show-icon :closable="false" style="margin-bottom:12px"
          />
          <div v-if="scriptResult.stdout" class="script-out">
            <div class="out-label">标准输出</div>
            <pre>{{ scriptResult.stdout }}</pre>
          </div>
          <div v-if="scriptResult.stderr" class="script-err">
            <div class="out-label">标准错误</div>
            <pre>{{ scriptResult.stderr }}</pre>
          </div>
          <el-button v-if="scriptResult.ok" type="primary" style="margin-top:12px" @click="afterScript">
            查看最新数据
          </el-button>
        </template>
      </el-card>
    </template>

    <!-- ── 钻取抽屉 ─────────────────────────────────── -->
    <el-drawer v-model="drillVisible" :title="drillTitle" size="78%" direction="rtl">
      <div class="drill-meta">共 {{ drillRows.length }} 条</div>
      <IssueTable :data="drillRows" max-height="calc(100vh - 120px)" />
    </el-drawer>
      </el-tab-pane>

      <!-- ── 管理员配置（数据源 + 项目 Tab） ──────────────── -->
      <el-tab-pane v-if="isAdmin" name="config">
        <template #label><el-icon><Setting /></el-icon> 配置</template>
        <div class="config-pane">
          <el-alert type="info" :closable="false" show-icon
            title="问题单管理配置（仅管理员可见）"
            description="在此维护数据源路径、定时采集与项目 Tab；各项修改后点对应「保存」。" />

          <el-card shadow="never" class="cfg-card">
            <template #header>
              <span class="cfg-title">定时采集</span>
              <span class="cfg-sub">各项目 Tab 每天自动跑一次采集脚本；保存后立即生效，无需重启后端</span>
            </template>
            <el-form label-width="130px" label-position="right">
              <el-form-item label="启用">
                <el-switch v-model="cfg.snapshotEnabled" active-text="每天自动采集" inactive-text="仅手动采集" />
              </el-form-item>
              <el-form-item label="执行时间">
                <div class="cfg-row">
                  <el-time-picker
                    v-model="snapshotTime"
                    format="HH:mm"
                    placeholder="选择时间"
                    style="width: 160px"
                    :disabled="!cfg.snapshotEnabled"
                  />
                  <el-button type="primary" @click="saveSchedule">保存</el-button>
                </div>
                <div class="cfg-hint">建议放在上班前（如 07:30）；采集耗时取决于问题单数量。</div>
              </el-form-item>
              <!-- 光看上面两项分不出"排期了但没跑"和"压根没排期"，把调度器的实际状态摊开 -->
              <el-form-item label="当前状态">
                <el-alert v-if="schedStatus" :type="schedType" :closable="false" show-icon
                  :title="schedTitle" :description="schedDesc" />
                <el-button link type="primary" @click="loadSchedule">刷新状态</el-button>
              </el-form-item>
              <el-form-item label="脚本超时">
                <div class="cfg-row">
                  <el-input-number v-model="cfg.scriptTimeout" :min="30" :max="7200" :step="30" style="width: 160px" />
                  <span class="cfg-hint" style="margin:0">秒</span>
                  <el-button type="primary" @click="saveTimeout">保存</el-button>
                </div>
                <div class="cfg-hint">单个项目采集脚本的最长执行时间，超时判为失败。默认 600 秒。</div>
              </el-form-item>
            </el-form>
          </el-card>

          <el-card shadow="never" class="cfg-card">
            <template #header><span class="cfg-title">数据源路径</span></template>
            <el-form label-width="130px" label-position="right">
              <el-form-item label="本地报表目录">
                <div class="cfg-row">
                  <el-input v-model="cfg.reportPath" placeholder="目录（按 _YYYYMMDD 取最新）或具体 xlsx 路径" clearable />
                  <el-button type="primary" @click="saveCfg('reportPath')">保存</el-button>
                </div>
                <div class="cfg-hint">「本地报表」tab 读取的 Excel 目录 / 文件。</div>
              </el-form-item>
              <el-form-item label="刷新脚本">
                <div class="cfg-row">
                  <el-input v-model="cfg.scriptPath" placeholder="脚本路径（.py / .bat / .exe）" clearable />
                  <el-button type="primary" @click="saveCfg('scriptPath')">保存</el-button>
                </div>
                <div class="cfg-hint">刷新本地报表数据的外部脚本。</div>
              </el-form-item>
              <el-form-item label="API 脚本">
                <div class="cfg-row">
                  <el-input v-model="cfg.apiScriptPath" placeholder="按项目调接口拉取问题单的脚本（.py）" clearable />
                  <el-button type="primary" @click="saveCfg('apiScriptPath')">保存</el-button>
                </div>
                <div class="cfg-hint">各项目 tab 的数据源，也是每日快照采集使用的脚本。</div>
              </el-form-item>
              <el-form-item label="快照存储目录">
                <div class="cfg-row">
                  <el-input v-model="cfg.snapshotDir" placeholder="留空则用 backend/data/issue_snapshots" clearable />
                  <el-button type="primary" @click="saveCfg('snapshotDir')">保存</el-button>
                </div>
                <div class="cfg-hint">每日快照的明细文件落盘目录（趋势数字存库，不占此目录）。</div>
              </el-form-item>
              <el-form-item label="Excel 原始表目录">
                <div class="cfg-row">
                  <el-input v-model="cfg.rawExcelDir" placeholder="留空则用 backend/data/issue_excel/raw" clearable />
                  <el-button type="primary" @click="saveCfg('rawExcelDir')">保存</el-button>
                </div>
                <div class="cfg-hint">采集时自动导出「原始数据」Excel 的备份目录；同日多次采集按时间戳保存、不覆盖。</div>
              </el-form-item>
              <el-form-item label="Excel 分析表目录">
                <div class="cfg-row">
                  <el-input v-model="cfg.analysisExcelDir" placeholder="留空则用 backend/data/issue_excel/analysis" clearable />
                  <el-button type="primary" @click="saveCfg('analysisExcelDir')">保存</el-button>
                </div>
                <div class="cfg-hint">采集时自动导出「统计分析」Excel 的备份目录。</div>
              </el-form-item>
            </el-form>
          </el-card>

          <el-card shadow="never" class="cfg-card">
            <template #header>
              <span class="cfg-title">项目 Tab</span>
              <span class="cfg-sub">顺序即页面从左到右的展示顺序（第 1 个＝第一页）</span>
            </template>
            <div class="proj-list">
              <div v-for="(p, i) in cfg.apiProjects" :key="p" class="proj-item">
                <span class="proj-idx">{{ i + 1 }}</span>
                <span class="proj-name">{{ p }}</span>
                <el-button link :icon="ArrowUp" :disabled="i === 0" title="上移" @click="moveProject(i, -1)" />
                <el-button link :icon="ArrowDown" :disabled="i === cfg.apiProjects.length - 1" title="下移" @click="moveProject(i, 1)" />
                <el-button link type="danger" :icon="Delete" title="删除" @click="removeProject(i)" />
              </div>
              <div v-if="!cfg.apiProjects.length" class="proj-empty">暂无项目，请在下方新增</div>
            </div>
            <div class="proj-add">
              <el-input v-model="newProject" placeholder="新增项目名，如 YLS9000" style="width:220px" @keyup.enter="addProject" />
              <el-button :icon="Plus" @click="addProject">新增项目</el-button>
              <el-button type="primary" @click="saveProjects">保存顺序</el-button>
            </div>
          </el-card>

          <el-card shadow="never" class="cfg-card">
            <template #header>
              <span class="cfg-title">统计部门</span>
              <span class="cfg-sub">只统计这些部门的问题单（留空＝全部）；子串匹配「责任人部门」，一行/分号一个</span>
            </template>
            <el-input
              v-model="cfg.statDepartments"
              type="textarea"
              :rows="3"
              placeholder="如：量检测装备软件部&#10;（多个部门一行一个，或用分号 ; 分隔；留空＝不限部门）"
            />
            <div class="cfg-actions">
              <el-button type="primary" @click="saveDepartments">保存</el-button>
            </div>
          </el-card>

          <el-card shadow="never" class="cfg-card">
            <template #header>
              <span class="cfg-title">小组配置</span>
              <span class="cfg-sub">部门下的小组，用于按责任人归组统计；成员用分号「;」分隔（中英文均可）</span>
            </template>
            <div class="grp-list">
              <div v-for="(g, i) in cfg.issueGroups" :key="i" class="grp-item">
                <span class="grp-idx">{{ i + 1 }}</span>
                <el-input v-model="g.name" placeholder="小组名" style="width:160px" />
                <el-input v-model="g.members" placeholder="成员，用 ; 分隔，如 张三;李四;Wang Wu" />
                <el-button link type="danger" :icon="Delete" title="删除" @click="removeGroup(i)" />
              </div>
              <div v-if="!cfg.issueGroups.length" class="proj-empty">暂无小组，点下方「新增小组」</div>
            </div>
            <div class="proj-add">
              <el-button :icon="Plus" @click="addGroup">新增小组</el-button>
              <el-button type="primary" @click="saveGroups">保存小组</el-button>
            </div>

            <!-- 归不到小组的责任人：名单少人是配置问题，摆在小组配置底下当场能补 -->
            <el-divider />
            <div class="ung-head">
              <span class="cfg-title">未归组责任人</span>
              <el-select v-model="ungProject" size="small" style="width:150px" @change="loadUngrouped">
                <el-option v-for="p in cfg.apiProjects" :key="p" :label="p" :value="p" />
              </el-select>
              <el-button size="small" :icon="Refresh" :loading="ungLoading" @click="loadUngrouped">刷新</el-button>
              <span class="muted">{{ ungHint }}</span>
            </div>
            <el-table v-if="ung.rows.length" :data="ung.rows" border stripe size="small" max-height="320">
              <el-table-column prop="owner" label="责任人" width="130" />
              <el-table-column prop="dept" label="部门" min-width="200" show-overflow-tooltip />
              <el-table-column prop="count" label="问题单" width="80" align="center" />
              <el-table-column label="加入小组" width="220">
                <template #default="{ row }">
                  <el-select
                    size="small" placeholder="选小组" style="width:200px"
                    :model-value="undefined" :persistent="false"
                    @change="(g) => assignToGroup(row, g)"
                  >
                    <el-option v-for="g in namedGroups" :key="g.name" :label="g.name" :value="g.name" />
                  </el-select>
                </template>
              </el-table-column>
            </el-table>
            <div v-else class="proj-empty">{{ ungLoading ? '加载中…' : ungEmptyText }}</div>
          </el-card>
        </div>
      </el-tab-pane>
    </el-tabs>

  </div>
</template>

<script setup>
import { computed, defineComponent, h, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElTable, ElTableColumn, ElTag } from 'element-plus'
import { ArrowDown, ArrowUp, DataLine, Delete, Document, Download, Plus, Refresh, Search, Setting, TrendCharts, VideoPlay } from '@element-plus/icons-vue'
// VideoPlay kept for script mode template (mode still accessible but button removed)
import * as echarts from 'echarts'
import { configApi, downloadBlob, issueApi } from '../api'
import { auth } from '../store/auth'
import IssueApiPanel from '../components/IssueApiPanel.vue'

const isAdmin = auth.isAdmin

// 顶层 tab：各项目（走 API）在前，local=历史数据（旧的本地报表）在后
// 默认停在第一个项目上；配置加载完才知道项目列表，见 onMounted
const topTab = ref('local')
// 项目 Tab 列表 + 顺序由管理员配置（config.issue_api_projects）；无配置时回退默认
const DEFAULT_PROJECTS = ['YLS3000', 'YLS5000', 'YLS8000']
const apiProjects = computed(() => cfg.value.apiProjects)
const newProject = ref('')

// 暂时关闭「特性 × 小组」展示（Excel 暂未提供该字段），代码保留待恢复
const SHOW_FEATURE = false

// 统计明细视图切换：'both' | 'table' | 'chart'
const statsView = ref('both')

// ── 调色板 ────────────────────────────────────────────
const PAL = ['#4073ba','#67C23A','#E6A23C','#F56C6C','#909399','#8E7AD8','#26C9C3','#F9A825']

// ── 内联子组件：统计表格 ──────────────────────────────
const StatsTable = defineComponent({
  props: { columns: Array, rows: Array },
  emits: ['cell-click'],
  setup(props, { emit }) {
    return () => h(ElTable, { data: props.rows || [], border: true, stripe: true, size: 'small' }, {
      default: () => [
        h(ElTableColumn, { prop: 'label', label: '小组', width: 160, fixed: true }),
        ...(props.columns || []).map(col =>
          h(ElTableColumn, { key: col, label: col, align: 'center', width: 90 }, {
            default: ({ row }) => {
              const val = row[col] ?? 0
              const isTotal = col === '合计' || row.label === '合计'
              return h('span', {
                class: val && !isTotal ? 'num-link' : isTotal && val ? 'num-total' : 'num-zero',
                onClick: (val && !isTotal) ? () => emit('cell-click', row.label, col, val) : undefined,
              }, String(val))
            },
          })
        ),
      ],
    })
  },
})

// ── 内联子组件：问题单表格 ────────────────────────────
const IssueTable = defineComponent({
  props: { data: Array, maxHeight: [String, Number] },
  setup(props) {
    const sevType = s => s === '严重' ? 'danger' : s === '一般' ? 'warning' : 'info'
    return () => h(ElTable, {
      data: props.data || [], border: true, stripe: true, size: 'small', maxHeight: props.maxHeight,
    }, {
      default: () => [
        h(ElTableColumn, { prop: 'version',  label: '版本信息',           width: 180, showOverflowTooltip: true }),
        h(ElTableColumn, { prop: 'issue_id', label: '缺陷业务编号',       width: 200 }),
        h(ElTableColumn, { prop: 'title',    label: '标题', minWidth: 260, showOverflowTooltip: true }),
        h(ElTableColumn, { prop: 'owner',    label: '当前责任人',          width: 110 }),
        h(ElTableColumn, { prop: 'group',    label: '当前责任人所属小组',  width: 160 }),
        h(ElTableColumn, { prop: 'progress', label: '进展',                width: 100 }),
        h(ElTableColumn, { prop: 'severity', label: '严重程度', width: 90, align: 'center' }, {
          default: ({ row }) => h(ElTag, { type: sevType(row.severity), size: 'small' }, () => row.severity),
        }),
      ],
    })
  },
})

// ── 配置 ─────────────────────────────────────────────
const cfg = ref({
  reportPath: '', scriptPath: '', apiScriptPath: '', snapshotDir: '',
  rawExcelDir: '', analysisExcelDir: '',
  apiProjects: [], statDepartments: '', issueGroups: [],
  snapshotEnabled: true, snapshotTime: '07:30', scriptTimeout: 600,
})

// el-time-picker 要 Date 对象，config 里存 "HH:mm" 字符串，这里做两向转换
const snapshotTime = computed({
  get() {
    const [h, m] = (cfg.value.snapshotTime || '07:30').split(':')
    const d = new Date()
    d.setHours(Number(h) || 0, Number(m) || 0, 0, 0)
    return d
  },
  set(d) {
    if (!d) return
    cfg.value.snapshotTime = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  },
})
async function loadCfg() {
  try {
    const { data } = await configApi.get()
    cfg.value.reportPath = data.issue_report_path || ''
    cfg.value.scriptPath = data.issue_script_path || ''
    cfg.value.apiScriptPath = data.issue_api_script_path || ''
    cfg.value.snapshotDir = data.issue_snapshot_dir || ''
    cfg.value.rawExcelDir = data.issue_excel_raw_dir || ''
    cfg.value.analysisExcelDir = data.issue_excel_analysis_dir || ''
    cfg.value.apiProjects = Array.isArray(data.issue_api_projects) && data.issue_api_projects.length
      ? data.issue_api_projects.slice()
      : DEFAULT_PROJECTS.slice()
    cfg.value.snapshotEnabled = data.issue_snapshot_enabled !== false
    cfg.value.snapshotTime = /^\d{1,2}:\d{2}$/.test(data.issue_snapshot_time || '') ? data.issue_snapshot_time : '07:30'
    cfg.value.scriptTimeout = Number(data.issue_script_timeout) > 0 ? Number(data.issue_script_timeout) : 600
    cfg.value.statDepartments = (Array.isArray(data.issue_stat_departments) ? data.issue_stat_departments : []).join('\n')
    cfg.value.issueGroups = Array.isArray(data.issue_groups)
      ? data.issue_groups.map(g => ({
          name: g.name || '',
          members: typeof g.members === 'string' ? g.members : (Array.isArray(g.members) ? g.members.join(';') : ''),
        }))
      : []
  } catch { /* 忽略 */ }
}
async function saveCfg(key) {
  const map = {
    reportPath: 'issue_report_path', scriptPath: 'issue_script_path',
    apiScriptPath: 'issue_api_script_path', snapshotDir: 'issue_snapshot_dir',
    rawExcelDir: 'issue_excel_raw_dir', analysisExcelDir: 'issue_excel_analysis_dir',
  }
  try {
    await configApi.save({ [map[key]]: cfg.value[key] })
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

// ── 定时采集配置（管理员）────────────────────────────
// 调度器的实际状态。后端把 config 存进文件和把任务挂进 APScheduler 是两件事，
// 只报"已保存"会掩盖第二件没成功——那正是"日志里只有手动记录"的成因之一。
const schedStatus = ref(null)
async function loadSchedule() {
  try {
    const { data } = await issueApi.collectSchedule()
    schedStatus.value = data
  } catch { schedStatus.value = null }
}
const schedType = computed(() => {
  const s = schedStatus.value
  if (!s) return 'info'
  if (!s.scheduler_running || (s.enabled && !s.job_registered)) return 'error'
  if (!s.enabled || !s.script_path || !s.projects?.length) return 'warning'
  return 'success'
})
const schedTitle = computed(() => {
  const s = schedStatus.value
  if (!s) return '状态未知'
  if (!s.scheduler_running) return '调度器未运行 —— 定时采集不会执行'
  if (!s.enabled) return '每日自动采集已停用（仅手动采集）'
  if (!s.job_registered) return '已启用，但任务未注册到调度器'
  return `已启用，下次自动采集：${s.next_run_at || '未知'}`
})
const schedDesc = computed(() => {
  const s = schedStatus.value
  if (!s) return ''
  if (!s.scheduler_running) return '后端启动时 APScheduler 装载失败，请查后端日志里的「scheduler 启动失败」。'
  if (!s.enabled) return '把上面的开关打开并保存即可恢复排期。'
  if (!s.script_path) return '未配置 API 脚本路径，定时任务会直接跳过、连失败记录都不留。'
  if (!s.projects?.length) return '未配置项目列表，定时任务会直接跳过。'
  return '若到点后「采集日志」里仍没有 auto 记录，说明那一刻后端进程不在运行（内存排期不会事后补跑）。'
})

async function saveSchedule() {
  try {
    const { data } = await configApi.save({
      issue_snapshot_enabled: cfg.value.snapshotEnabled,
      issue_snapshot_time: cfg.value.snapshotTime,
    })
    // 以后端的排期结论为准，而不是照抄我们提交的值
    ElMessage.success(data?._schedule_message || (cfg.value.snapshotEnabled
      ? `已保存：每天 ${cfg.value.snapshotTime} 自动采集`
      : '已保存：已停用每日自动采集'))
    loadSchedule()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}
async function saveTimeout() {
  try {
    await configApi.save({ issue_script_timeout: Number(cfg.value.scriptTimeout) || 600 })
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

// ── 统计部门 & 小组配置（管理员）──────────────────────
async function saveDepartments() {
  const list = cfg.value.statDepartments.split(/[\n;；,，]/).map(s => s.trim()).filter(Boolean)
  try {
    await configApi.save({ issue_stat_departments: list })
    ElMessage.success(list.length ? `已保存（只统计 ${list.length} 个部门）` : '已保存（不限部门）')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}
function addGroup() {
  cfg.value.issueGroups.push({ name: '', members: '' })
}
function removeGroup(i) {
  cfg.value.issueGroups.splice(i, 1)
}
async function saveGroups() {
  const list = cfg.value.issueGroups
    .map(g => ({ name: (g.name || '').trim(), members: (g.members || '').trim() }))
    .filter(g => g.name)
  try {
    await configApi.save({ issue_groups: list })
    ElMessage.success(`小组已保存（${list.length} 个）`)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

// ── 未归组责任人（小组名单的待办清单）────────────────
// 归不到组的单**不会**被丢掉（后端归到「未归组」），否则它会在相邻快照差分里
// 变成一笔假「解决」。这里把人列出来让管理员补名单，补完下次采集就归位了。
const ung = ref({ date: '', rows: [], count: 0, issues: 0 })
const ungProject = ref('')
const ungLoading = ref(false)
const namedGroups = computed(() => cfg.value.issueGroups.filter(g => (g.name || '').trim()))
const ungHint = computed(() => {
  if (!ung.value.date) return ''
  return `${ung.value.date} 快照：${ung.value.count} 人 / ${ung.value.issues} 条问题单`
})
const ungEmptyText = computed(() => {
  if (!namedGroups.value.length) return '还没有配置小组——不配小组时不做归组，也就没有未归组的人。'
  if (!ung.value.date) return '该项目还没有快照，采集一次后这里才有数据。'
  return '没有未归组的责任人，名单是全的。'
})
async function loadUngrouped() {
  if (!ungProject.value) return
  ungLoading.value = true
  try {
    const { data } = await issueApi.ungrouped(ungProject.value)
    ung.value = { date: data.date || '', rows: data.rows || [], count: data.count || 0, issues: data.issues || 0 }
  } catch {
    ung.value = { date: '', rows: [], count: 0, issues: 0 }
  } finally {
    ungLoading.value = false
  }
}
async function assignToGroup(row, groupName) {
  const g = cfg.value.issueGroups.find(x => (x.name || '').trim() === groupName)
  if (!g) return
  const members = (g.members || '').split(/[;；\n]/).map(x => x.trim()).filter(Boolean)
  if (members.some(m => m.toLowerCase() === row.owner.toLowerCase())) {
    ElMessage.warning(`${row.owner} 已经在「${groupName}」名单里了`)
    return
  }
  members.push(row.owner)
  g.members = members.join(';')
  // 直接落盘：点了「加入」却还要记得去点「保存小组」，一定会有人漏掉，
  // 而漏掉的表现是下次采集这人还在未归组里，看着像功能没生效。
  await saveGroups()
  await loadUngrouped()
}

// ── 项目 Tab 编辑（管理员）────────────────────────────
function addProject() {
  const name = newProject.value.trim()
  if (!name) return
  if (cfg.value.apiProjects.includes(name)) {
    ElMessage.warning('该项目已存在')
    return
  }
  cfg.value.apiProjects.push(name)
  newProject.value = ''
}
function removeProject(i) {
  cfg.value.apiProjects.splice(i, 1)
}
function moveProject(i, dir) {
  const arr = cfg.value.apiProjects
  const j = i + dir
  if (j < 0 || j >= arr.length) return
  ;[arr[i], arr[j]] = [arr[j], arr[i]]
}
async function saveProjects() {
  try {
    await configApi.save({ issue_api_projects: cfg.value.apiProjects.slice() })
    ElMessage.success('项目顺序已保存')
    // 若当前正停在某个被删掉的项目 tab 上，回到本地报表，避免空白（config/local 不动）
    if (!['local', 'config'].includes(topTab.value) && !cfg.value.apiProjects.includes(topTab.value)) {
      topTab.value = 'local'
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

// ── 模式切换 ──────────────────────────────────────────
const mode = ref('today')
async function switchMode(m) {
  if (mode.value === 'script' && m !== 'script') stopStatusPoll()
  mode.value = m
  if (m === 'script') startStatusPoll()
  else if (m === 'trend' && !trendData.value) await loadTrend()
  else if (m === 'today' && !todayData.value) await loadToday()
  await nextTick()
  if (m === 'trend') initTrendCharts()
}

// ── 日期选择 ──────────────────────────────────────────
const availableDates = ref([])
const selectedDate   = ref(null)

async function loadDates() {
  try {
    const { data } = await issueApi.listDates()
    availableDates.value = data
    if (data.length && !selectedDate.value) {
      selectedDate.value = data[0]
    }
  } catch { /* 忽略，可能是平铺结构 */ }
}

async function onDateChange() {
  todayData.value = null
  await loadToday()
  await nextTick()
  initTodayCharts()
}

// ── 当天数据 ──────────────────────────────────────────
const todayData  = ref(null)
const loading    = ref(false)
const subTab     = ref('stats')
const rawSearch  = ref('')

async function loadToday() {
  loading.value = true
  try {
    const { data } = await issueApi.getData(selectedDate.value || null)
    todayData.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '读取失败')
  } finally {
    loading.value = false
  }
}

const filteredRaw = computed(() => {
  if (!todayData.value?.raw) return []
  const q = rawSearch.value.trim().toLowerCase()
  if (!q) return todayData.value.raw
  return todayData.value.raw.filter(r =>
    [r.issue_id, r.title, r.owner, r.group, r.progress].some(v => v?.toLowerCase().includes(q))
  )
})

function countBy(field, val) {
  return todayData.value?.raw?.filter(r => r[field] === val).length ?? 0
}

// ── 趋势数据 ──────────────────────────────────────────
const trendData    = ref(null)
const trendLoading = ref(false)

async function loadTrend() {
  trendLoading.value = true
  try {
    const { data } = await issueApi.getTrend()
    trendData.value = data
    await nextTick()
    initTrendCharts()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '趋势加载失败')
  } finally {
    trendLoading.value = false
  }
}

// ── 脚本执行 & 状态轮询 ───────────────────────────────
const scriptRunning   = ref(false)
const scriptResult    = ref(null)
const remoteRunning   = ref(false)
const remoteStartedAt = ref(null)
let   _statusTimer    = null

async function fetchScriptStatus() {
  try {
    const { data } = await issueApi.scriptStatus()
    remoteRunning.value   = data.running
    remoteStartedAt.value = data.started_at
  } catch {}
}

function startStatusPoll() {
  fetchScriptStatus()
  _statusTimer = setInterval(fetchScriptStatus, 3000)
}

function stopStatusPoll() {
  if (_statusTimer) { clearInterval(_statusTimer); _statusTimer = null }
  remoteRunning.value   = false
  remoteStartedAt.value = null
}

async function doRunScript() {
  scriptRunning.value = true
  scriptResult.value  = null
  try {
    const { data } = await issueApi.runScript()
    scriptResult.value = data
    if (data.ok) ElMessage.success('脚本执行成功')
    else         ElMessage.warning('脚本执行完毕，退出码非 0，请检查输出')
  } catch (e) {
    const msg = e.response?.data?.detail || '执行失败'
    ElMessage.error(msg)
  } finally {
    scriptRunning.value = false
    fetchScriptStatus()
  }
}

async function afterScript() {
  mode.value = 'today'
  todayData.value = null
  await loadToday()
  await nextTick()
  initTodayCharts()
}

// ── 刷新 & 导出 ───────────────────────────────────────
async function refresh() {
  if (mode.value === 'trend') await loadTrend()
  else { await loadToday(); await nextTick(); initTodayCharts() }
}

const exporting = ref(false)
async function exportPptx() {
  exporting.value = true
  try {
    const resp = await issueApi.exportPptx(selectedDate.value || null)
    const ts   = new Date().toISOString().replace(/[:.T]/g, '-').slice(0, 19)
    downloadBlob(resp.data, `缺陷统计报表_${ts}.pptx`)
    ElMessage.success('已导出')
  } catch (e) {
    let msg = '导出失败'
    try {
      if (e.response?.data instanceof Blob) {
        const text = await e.response.data.text()
        msg = JSON.parse(text).detail || msg
      } else {
        msg = e.response?.data?.detail || msg
      }
    } catch {}
    ElMessage.error(msg)
  } finally {
    exporting.value = false
  }
}

// ── 文件提示 ──────────────────────────────────────────
const fileHint = computed(() => {
  const d = todayData.value
  if (!d?.actual_file) return ''
  return d.file_mtime ? `${d.actual_file} · ${d.file_mtime}` : d.actual_file
})

// ── 钻取 ─────────────────────────────────────────────
const drillVisible = ref(false)
const drillTitle   = ref('')
const drillRows    = ref([])

function openDrill(filters, title = '问题单明细') {
  let rows = todayData.value?.raw || []
  if (filters.severity)   rows = rows.filter(r => r.severity   === filters.severity)
  if (filters.group)      rows = rows.filter(r => r.group      === filters.group)
  if (filters.year_month) rows = rows.filter(r => r.year_month === filters.year_month)
  if (filters.category)   rows = rows.filter(r => r.category   === filters.category)
  if (filters.feature)    rows = rows.filter(r => r.feature    === filters.feature)
  drillRows.value   = rows
  drillTitle.value  = title
  drillVisible.value = true
}

function onMonthlyClick(group, col, v) {
  if (!v) return
  const f = {}; const t = []
  if (group !== '合计') { f.group = group; t.push(group) }
  if (col   !== '合计') { f.year_month = col; t.push(col) }
  openDrill(f, t.join(' · ') || '全部')
}
function onCustomerClick(group, col, v) {
  if (!v) return
  const f = {}; const t = []
  if (group !== '合计') { f.group = group; t.push(group) }
  if (col   !== '合计') { f.category = col; t.push(`客户:${col}`) }
  openDrill(f, t.join(' · ') || '全部')
}
function onFeatureClick(group, col, v) {
  if (!v) return
  const f = {}; const t = []
  if (group !== '合计') { f.group = group; t.push(group) }
  if (col   !== '合计') { f.feature = col; t.push(`特性:${col}`) }
  openDrill(f, t.join(' · ') || '全部')
}

// ── ECharts 管理 ─────────────────────────────────────
const monthlyBarEl   = ref(null)
const customerBarEl  = ref(null)
const featureBarEl   = ref(null)
const trendGroupEl   = ref(null)
const trendSeverityEl = ref(null)

const instances = {}
function setChart(key, el, option) {
  if (!el) return
  if (!instances[key]) instances[key] = echarts.init(el)
  instances[key].setOption(option, { notMerge: true })
}

function onSubTabChange(tab) {
  nextTick(() => {
    if (tab === 'stats') initStatsBarCharts()
    Object.values(instances).forEach(c => c.resize())
  })
}

function _stackedBarOption(cross, labelField = 'label') {
  const { columns = [], rows = [] } = cross
  const xLabels = columns.filter(c => c !== '合计')
  const series  = rows.filter(r => r.label !== '合计')
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    // 图例放顶部 + containLabel：旋转后的长标签计入绘图区，不与图例/边缘重叠
    legend: { data: series.map(s => s.label), top: 0, type: 'scroll' },
    grid:   { top: 32, left: 8, right: 12, bottom: 4, containLabel: true },
    xAxis:  {
      type: 'category', data: xLabels,
      axisLabel: {
        rotate: xLabels.length > 5 ? 35 : 0,
        interval: 0, fontSize: 11,
        width: 84, overflow: 'truncate',
      },
    },
    yAxis:  { type: 'value', minInterval: 1 },
    series: series.map((s, i) => ({
      name: s.label, type: 'bar', stack: 'total',
      color: PAL[i % PAL.length],
      data: xLabels.map(x => s[x] ?? 0),
      label: { show: false },
    })),
  }
}

function initStatsBarCharts() {
  const d = todayData.value
  if (!d) return
  if (monthlyBarEl.value)  setChart('monthlyBar',  monthlyBarEl.value,  _stackedBarOption(d.monthly_by_group))
  if (customerBarEl.value) setChart('customerBar', customerBarEl.value, _stackedBarOption(d.by_customer))
  if (featureBarEl.value)  setChart('featureBar',  featureBarEl.value,  _stackedBarOption(d.feature_by_group))
}

function initTodayCharts() {
  nextTick(() => {
    if (subTab.value === 'stats') initStatsBarCharts()
  })
}

function initTrendCharts() {
  const td = trendData.value
  if (!td) return
  const dates    = td.daily.map(d => d.date)
  const groups   = td.all_groups
  const sevs     = td.all_severities
  const SEV_CLR  = { '严重': '#F56C6C', '一般': '#E6A23C', '提示': '#909399' }

  if (trendGroupEl.value) {
    setChart('trendGroup', trendGroupEl.value, {
      tooltip: { trigger: 'axis' },
      legend: { data: groups, top: 0, type: 'scroll' },
      grid:   { top: 34, left: 8, right: 16, bottom: 4, containLabel: true },
      xAxis:  { type: 'category', data: dates, axisLabel: { rotate: dates.length > 10 ? 30 : 0, fontSize: 11 } },
      yAxis:  { type: 'value', minInterval: 1, name: '缺陷数' },
      series: groups.map((g, i) => ({
        name: g, type: 'line', smooth: true, symbolSize: 7,
        color: PAL[i % PAL.length],
        data: td.daily.map(d => d.by_group[g] ?? 0),
      })),
    })
  }

  if (trendSeverityEl.value) {
    setChart('trendSeverity', trendSeverityEl.value, {
      tooltip: { trigger: 'axis' },
      legend: { data: sevs, top: 0 },
      grid:   { top: 34, left: 8, right: 16, bottom: 4, containLabel: true },
      xAxis:  { type: 'category', data: dates, axisLabel: { rotate: dates.length > 10 ? 30 : 0, fontSize: 11 } },
      yAxis:  { type: 'value', minInterval: 1, name: '缺陷数' },
      series: sevs.map(s => ({
        name: s, type: 'line', smooth: true, symbolSize: 8, lineWidth: 2,
        color: SEV_CLR[s] || PAL[0],
        data: td.daily.map(d => d.by_severity[s] ?? 0),
        areaStyle: { opacity: 0.08 },
      })),
    })
  }
}

// ── 监听数据变化后更新图表 ───────────────────────────
watch(todayData, async () => {
  await nextTick()
  initTodayCharts()
})

watch(trendData, async () => {
  await nextTick()
  initTrendCharts()
})

// 切换统计明细视图时同步触发 echarts resize（v-show 不会卸载实例）
watch(statsView, async () => {
  await nextTick()
  Object.values(instances).forEach(c => c.resize())
})

// ── resize ────────────────────────────────────────────
function onResize() { Object.values(instances).forEach(c => c.resize()) }

// ── 生命周期 ─────────────────────────────────────────
onMounted(async () => {
  await loadCfg()
  // 默认落在第一个项目 tab（问题单日常看的是这个），没有项目才回退历史数据
  if (cfg.value.apiProjects.length) topTab.value = cfg.value.apiProjects[0]
  await loadDates()   // 先拿到日期列表，selectedDate 会自动设为最新
  await loadToday()
  if (auth.isAdmin.value) {
    loadSchedule()   // 只有管理员能看到「配置」tab
    ungProject.value = cfg.value.apiProjects[0] || ''
    loadUngrouped()
  }
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  stopStatusPoll()
  Object.values(instances).forEach(c => c.dispose())
  window.removeEventListener('resize', onResize)
})
</script>

<style scoped>
.issue-page { display: flex; flex-direction: column; gap: 14px; }

/* 管理员配置页 */
.config-pane { display: flex; flex-direction: column; gap: 14px; max-width: 880px; }
.cfg-card :deep(.el-card__header) { padding: 12px 16px; }
.cfg-title { font-size: 14px; font-weight: 600; color: #1f2329; }
.cfg-sub { font-size: 12px; color: #909399; margin-left: 10px; }
.cfg-row { display: flex; align-items: center; gap: 8px; width: 100%; }
.ung-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.cfg-row .el-input { flex: 1 1 auto; }
.cfg-hint { font-size: 12px; color: #909399; margin-top: 2px; }
.config-pane :deep(.el-form-item) { margin-bottom: 16px; }

.proj-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.proj-item {
  display: flex; align-items: center; gap: 8px;
  background: #f7f9fc; border: 1px solid #e6ebf2; border-radius: 6px; padding: 6px 12px;
}
.proj-idx {
  flex: 0 0 22px; height: 22px; line-height: 22px; text-align: center;
  background: #4073ba; color: #fff; border-radius: 50%; font-size: 12px; font-weight: 600;
}
.proj-name { flex: 1 1 auto; font-size: 14px; color: #1f2329; font-weight: 600; }
.proj-empty { color: #909399; font-size: 13px; padding: 6px 0; }
.muted { color: #909399; font-size: 12px; }
.proj-add { display: flex; align-items: center; gap: 8px; }

/* 统计部门 / 小组配置 */
.cfg-actions { margin-top: 10px; text-align: right; }
.grp-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.grp-item { display: flex; align-items: center; gap: 8px; }
.grp-item .el-input:last-of-type { flex: 1 1 auto; }
.grp-idx {
  flex: 0 0 22px; height: 22px; line-height: 22px; text-align: center;
  background: #eef2f8; color: #4073ba; border-radius: 50%; font-size: 12px; font-weight: 600;
}

/* 模式栏 */
.mode-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #fff;
  border: 1px solid #eaecef;
  border-radius: 8px;
  padding: 10px 14px;
  flex-wrap: wrap;
}
.file-hint { color: #606266; font-size: 13px; display: inline-flex; align-items: center; gap: 4px; }

/* 统计卡片 */
.stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.stat-card {
  background: #fff; border: 1px solid #eaecef; border-radius: 10px;
  padding: 20px 24px; cursor: pointer; text-align: center;
  transition: all .2s;
}
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 8px 20px -12px rgba(31,45,61,.3); border-color: #c6e2ff; }
.stat-num  { font-size: 36px; font-weight: 700; color: #303133; line-height: 1.1; }
.stat-label { font-size: 13px; color: #909399; margin-top: 6px; }
.sev .stat-num { color: #f56c6c; } .sev:hover { border-color: #fab6b6; }
.nor .stat-num { color: #e6a23c; } .nor:hover { border-color: #f3d19e; }
.tip .stat-num { color: #909399; }

/* 主卡 */
.main-card :deep(.el-card__body) { padding: 0 16px 16px; }

/* 统计明细工具栏 */
.stats-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 0 8px;
}
.stats-toolbar-label { color: #606266; font-size: 13px; }

/* 图表 */
.chart-lg { width: 100%; height: 340px; margin-top: 8px; }
.chart-sm { width: 100%; height: 260px; }
.chart-sm.chart-wide { height: 380px; }

/* 统计明细 */
.section-title {
  font-size: 14px; font-weight: 600; color: #303133;
  margin: 12px 0 8px; padding-left: 8px; border-left: 3px solid #4073ba;
}

/* 数字链接（由 StatsTable 子组件渲染，需穿透） */
:deep(.num-link) {
  color: #409EFF; font-weight: 600; cursor: pointer;
  padding: 2px 6px; border-radius: 4px; display: inline-block; min-width: 24px;
}
:deep(.num-link:hover) { background: #ecf5ff; }
:deep(.num-total) { color: #303133; font-weight: 700; display: inline-block; }
:deep(.num-zero)  { color: #c0c4cc; }
:deep(.total-row td) { background: #f5f7fa !important; font-weight: 600; }

/* 原始数据 */
.raw-toolbar { display: flex; align-items: center; gap: 12px; margin: 8px 0 10px; }
.raw-count   { color: #909399; font-size: 13px; }

/* 趋势卡 */
.detail-card { margin-bottom: 14px; }
.detail-card :deep(.el-card__header) { display: flex; justify-content: space-between; align-items: center; }
.card-title { font-size: 15px; font-weight: 600; }
.card-hint  { font-size: 12px; color: #909399; }

/* 脚本模式 */
.script-tip  { color: #606266; font-size: 13px; margin-bottom: 16px; line-height: 1.7; }
.script-out, .script-err { margin-top: 12px; }
.out-label   { font-size: 12px; color: #909399; margin-bottom: 4px; }
.script-out pre { background: #f5f7fa; padding: 12px; border-radius: 6px; font-size: 12px; white-space: pre-wrap; max-height: 300px; overflow: auto; }
.script-err pre { background: #fef0f0; padding: 12px; border-radius: 6px; font-size: 12px; color: #f56c6c; white-space: pre-wrap; max-height: 200px; overflow: auto; }

/* 钻取 */
.drill-meta { color: #606266; font-size: 13px; margin-bottom: 10px; }
</style>
