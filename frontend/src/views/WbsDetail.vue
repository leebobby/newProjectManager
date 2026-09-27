<template>
  <div class="page" v-loading="loading">
    <template v-if="plan">
      <div class="page-head">
        <div>
          <div class="crumb"><router-link to="/wbs">← 全部 WBS</router-link></div>
          <h2>{{ plan.name }}</h2>
          <div class="sub">
            <el-tag size="small" :type="plan.kind === 'machine' ? 'warning' : 'info'" effect="plain">
              {{ plan.kind_label }}
            </el-tag>
            <span>{{ plan.ref_name || '—' }}</span>
            <span class="sep" />负责人 <b>{{ plan.owner || '未指定' }}</b>
            <span class="sep" />计划窗口 <b class="num">{{ ymd(plan.planned_start) }} → {{ ymd(plan.planned_end) }}</b>
          </div>
        </div>
        <div class="head-ops">
          <el-button size="small" @click="rename">重命名</el-button>
          <el-button v-if="isAdmin" size="small" type="danger" plain @click="removePlan">删除此 WBS</el-button>
        </div>
      </div>

      <div class="stats">
        <div class="stat"><div class="k">计入统计的人天</div><div class="v">{{ plan.total_days }}</div>
          <div class="n">{{ plan.leaf_count }} 个叶子工作包</div></div>
        <div class="stat"><div class="k">加权完成度</div><div class="v">{{ plan.progress_pct }}%</div>
          <div class="n">Σ(人天×完成度)÷Σ人天</div></div>
        <div class="stat"><div class="k">层级深度</div><div class="v">最深 {{ plan.max_depth }} 层</div>
          <div class="n">{{ plan.row_count }} 行</div></div>
        <div class="stat" :class="{ flagged: plan.flagged }"><div class="k">待补录</div>
          <div class="v">{{ plan.flagged }}</div><div class="n">缺负责人 / 工期等</div></div>
      </div>

      <!-- 排除多少条要如实报出来：只筛不报的表现是「数字怎么小了一截」，
           而没人说得清少的是哪些 -->
      <div class="excluded">
        <template v-if="plan.excluded">
          已排除 <b>{{ plan.excluded }}</b> 条（状态为「已变更 / 不涉及」）、合计
          <b>{{ plan.excluded_days }}</b> 人天，不计入上面任何一个数字。这些行仍然留在表里。
        </template>
        <template v-else>当前没有「已变更 / 不涉及」的行，上面的数字就是全量。</template>
      </div>

      <div class="tools">
        <el-button size="small" type="primary" :icon="Plus" @click="addRow(null)">新增分组</el-button>
        <el-button v-if="!items.length" size="small" @click="applyTpl">套用标准调试模板</el-button>
        <el-button size="small" @click="expandAll(true)">全部展开</el-button>
        <el-button size="small" @click="expandAll(false)">全部收起</el-button>
        <el-checkbox v-model="onlyFlag" size="small" style="margin-left: 8px">只看待补录</el-checkbox>
        <span class="grow" />
        <!-- 导出到第几层：深于它的行不再逐条列出，但**汇总数字一个都不变**
             （人天/完成度本来就是从叶子算上来的），折叠了几条写在表尾 -->
        <el-select v-model="exportDepth" size="small" style="width: 128px" :persistent="false">
          <el-option v-for="o in depthOptions" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
        <!-- A 图是**另一张图**，和调试框图各答各的（见 wbs_timeline 模块说明）。
             页面**默认还是表**，图放在预览弹窗里：不是每次进来都要看图，
             而它一展开就占掉一屏 -->
        <el-button size="small" type="primary" plain @click="timelineOn = true">预览 A 图</el-button>
        <el-button size="small" :type="showDiagram ? 'primary' : ''" :plain="showDiagram"
                   @click="showDiagram = !showDiagram">调试框图</el-button>
        <el-button size="small" :icon="Download" :loading="exporting" @click="exportXlsx">导出 Excel</el-button>
      </div>

      <!-- 框图与表格是同一份数据的两种看法：表看每一行填了什么，
           图看这件事分几步走、每一步哪天该完、哪一步已经拖了。
           默认收着——不是每次进来都要看图，而它一展开就占掉一屏 -->
      <WbsDiagram v-if="showDiagram" ref="diagramRef" :plan-id="route.params.id"
                  :max-depth="exportDepth || null" class="diagram" />

      <el-empty v-if="!items.length" description="这份 WBS 还是空的">
        <span class="muted">可以「套用标准调试模板」一次生成 6 个分组，再往里逐层拆；也可以直接新增一个分组。</span>
      </el-empty>

      <el-table v-else :data="visible" border size="small" row-key="id" class="wbs-table"
                :row-class-name="rowClass">
        <el-table-column label="编号" width="132">
          <!-- 缩进用**定宽的 inline-block**，不是给空 span 加 padding：
               层级一深，padding 那种写法会把编号挤到折行，看着像编号错位了 -->
          <template #default="{ row }">
            <span class="codecell">
              <i class="indent" :style="{ width: (row.depth - 1) * 14 + 'px' }" />
              <el-button v-if="!row.is_leaf" link class="caret" @click="toggle(row.id)">
                {{ collapsed.has(row.id) ? '▸' : '▾' }}
              </el-button>
              <span v-else class="caret" />
              <span class="code" :style="codeStyle(row.depth)">{{ row.code }}</span>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="工作包" min-width="230">
          <template #default="{ row }">
            <el-input v-model="row.name" size="small" class="cell"
                      :input-style="levelStyle(row.depth)"
                      @change="patch(row, { name: row.name })" />
            <el-tooltip v-if="row.issues.length" :content="row.issues.join(' · ')">
              <span class="warn">⚠ {{ row.issues.length }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="负责人" width="118">
          <template #default="{ row }">
            <el-select v-model="row.owner_user_id" size="small" filterable clearable
                       :persistent="false" class="cell" placeholder="未指定"
                       @change="patch(row, { owner_user_id: row.owner_user_id ?? null })">
              <el-option v-for="u in users" :key="u.id" :label="u.full_name || u.username" :value="u.id" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="PL组" width="132">
          <template #default="{ row }">
            <el-select v-model="row.group_id" size="small" filterable clearable
                       :persistent="false" class="cell" placeholder="未指定"
                       @change="patch(row, { group_id: row.group_id ?? null })">
              <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="计划开始" width="126">
          <template #default="{ row }">
            <DateCell v-if="row.is_leaf" :model-value="row.planned_start"
                      @update:model-value="(v) => patch(row, { planned_start: v })" />
            <span v-else class="roll">{{ ymd(row.roll_start) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计划完成" width="126">
          <template #default="{ row }">
            <DateCell v-if="row.is_leaf" :model-value="row.planned_end"
                      @update:model-value="(v) => patch(row, { planned_end: v })" />
            <span v-else class="roll">{{ ymd(row.roll_end) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="人天" width="88" align="right">
          <template #default="{ row }">
            <el-input v-if="row.is_leaf" v-model="row.man_days" size="small" class="cell num"
                      @change="patch(row, { man_days: numOrNull(row.man_days) })" />
            <span v-else class="roll">{{ row.roll_days }}<i class="tag">汇总</i></span>
          </template>
        </el-table-column>
        <el-table-column label="完成度" width="118">
          <template #default="{ row }">
            <template v-if="row.is_leaf">
              <el-input v-model="row.progress_pct" size="small" class="cell num"
                        @change="patch(row, { progress_pct: clampPct(row.progress_pct) })" />
              <el-progress :percentage="clampPct(row.progress_pct)" :show-text="false" :stroke-width="4" />
            </template>
            <template v-else>
              <span class="roll">{{ row.roll_pct }}%</span>
              <el-progress :percentage="row.roll_pct" :show-text="false" :stroke-width="4" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="112">
          <template #default="{ row }">
            <el-select v-if="row.is_leaf" v-model="row.status" size="small" :persistent="false"
                       class="cell status" :style="statusStyle(row.status)"
                       @change="patch(row, { status: row.status })">
              <el-option v-for="s in STATUSES" :key="s" :label="s" :value="s" />
            </el-select>
            <span v-else class="roll muted">{{ row.leaf_count }} 个叶子</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="196">
          <template #default="{ row }">
            <el-button link size="small" @click="addRow(row.id)">+子项</el-button>
            <el-button link size="small" :disabled="!canDemote(row)" @click="demote(row)">→</el-button>
            <el-button link size="small" :disabled="row.depth === 1" @click="promote(row)">←</el-button>
            <el-button link size="small" @click="shift(row, -1)">↑</el-button>
            <el-button link size="small" @click="shift(row, 1)">↓</el-button>
            <el-button link size="small" @click="openDrawer(row)">详情</el-button>
            <el-button link size="small" class="del" @click="removeRow(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="notes">
        <h3>这几条口径由服务端保证</h3>
        <ol>
          <li><b>能不能填，看它有没有子行，不看它在第几层。</b>叶子行填人天 / 完成度 / 状态 / 计划起止；
            只要挂了子行，这几项一律变成汇总（灰色、点不动）。把 <code>2.1</code> 拆成
            <code>2.1.1</code> 的那一刻，它自己填的数就让位给底下加出来的——不然父子两个数对不上，而两边看着都对。</li>
          <li><b>完成度按人天加权</b>，分子分母都只数叶子，所以父行的数字和子行加起来永远对得上。</li>
          <li><b>计划起止也是汇总</b>：父行取子行的最早开始与最晚完成。</li>
          <li><b>编号按位置自动重排</b>，不存库：增删、上下移、升降级之后 <code>2.1.3</code>
            永远是第 2 组第 1 个包的第 3 个子任务。</li>
        </ol>
      </div>

      <!-- A 图：一根真日期横轴 + 大框套中框套小框。导出的 Excel 第 3 页是同一张图
           （版面在服务端算，两处共用一份），所以这儿看到什么样，导出就是什么样 -->
      <el-dialog v-model="timelineOn" title="A 图（时间轴嵌套框图）" width="94%" top="4vh"
                 destroy-on-close>
        <WbsTimeline v-if="timelineOn" :plan-id="route.params.id"
                     :max-depth="exportDepth || null" />
        <template #footer>
          <span class="dlg-foot">导出的 Excel 第 3 页就是这张图；上面那个「导出到第几层」
            同时管表、调试框图和这张 A 图——各裁各的话同一个「到第 2 层」在表里是 8 行、
            图上是 11 个框。</span>
        </template>
      </el-dialog>

      <el-drawer v-model="drawer" :title="drawerRow?.name || '工作包详情'" size="440px">
        <div class="dcode">WBS {{ drawerRow?.code }} · 第 {{ drawerRow?.depth }} 层 ·
          {{ drawerRow?.is_leaf ? '叶子（可填人天/完成度/状态）' : '父行（人天、完成度、日期均为汇总）' }}</div>
        <el-form label-position="top">
          <el-form-item label="交付物"><el-input v-model="dform.deliverable" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="完成标准（DoD）"><el-input v-model="dform.dod" type="textarea" :rows="2" /></el-form-item>
          <!-- 前置**存 id 不存编号**：编号（1.2.3）是按位置现算的，存编号的话上移
               一行之后它就指到另一件活上去了，而两行单独看都合法 -->
          <el-form-item label="前置任务（在这份 WBS 里选）">
            <el-select v-model="dform.predecessor_ids" multiple filterable clearable
                       :persistent="false" style="width: 100%"
                       placeholder="选一个或多个先做的任务">
              <el-option v-for="o in predOptions" :key="o.id" :label="o.label" :value="o.id" />
            </el-select>
            <div v-if="predLinks.length" class="predlinks">
              <span class="ptip">点进去看：</span>
              <template v-for="p in predLinks" :key="p.id">
                <el-button v-if="!p.missing" link type="primary" size="small"
                           @click="gotoItem(p.id)">{{ p.code }} {{ p.name }} →</el-button>
                <!-- 指向的行被删掉时照样摆出来：悄悄滤掉的话，填的人以为自己没填过 -->
                <span v-else class="pgone">（已删除 #{{ p.id }}）</span>
              </template>
            </div>
            <div v-if="drawerRow?.predecessor" class="plegacy">
              老写法（手填的编号）：<b>{{ drawerRow.predecessor }}</b>。编号会随行的位置变，
              已改成按任务关联——照着它把上面的前置选好之后，可以
              <el-button link type="primary" size="small" @click="dropLegacy">清掉这行老值</el-button>。
            </div>
          </el-form-item>
          <el-form-item label="假设 · 范围外 · 风险"><el-input v-model="dform.remark" type="textarea" :rows="3" /></el-form-item>
        </el-form>
        <el-button type="primary" @click="saveDrawer">保存</el-button>
        <el-button @click="drawer = false">关闭</el-button>
      </el-drawer>
    </template>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElDatePicker, ElMessage, ElMessageBox } from 'element-plus'
import { Download, Plus } from '@element-plus/icons-vue'
import { apiError, downloadBlob, resourceGroupApi, userApi, wbsApi } from '../api'
import { auth } from '../store/auth'
import { reloadWbs } from '../store/wbs'
import WbsDiagram from '../components/WbsDiagram.vue'
import WbsTimeline from '../components/WbsTimeline.vue'
// 各级任务的字号阶梯与后端 enums.WBS_LEVEL_FONTS **两端各一份、必须同步**：
// 分叉的表现是页面上分组比子任务大一号、导出的 Excel 里一样大
import { levelStyle } from '../utils/wbsLevel'

// 六档与后端 enums.PROGRESS_STATUSES 一致；着色只上在状态那一格，不整行铺
const STATUSES = ['未开始', '进行中', '已完成', '已延期', '已变更', '不涉及']
const FILL = { 已完成: '#92D050', 进行中: '#FFD966', 已延期: '#FF9999', 已变更: '#D9D9D9' }

// 大表格里不能每行常驻 el-date-picker：它的面板立即渲染且关不掉，
// 一行两个日期列＝两个完整月历，几百行就是几万个节点（见 CustomerIssueTracking 的 DateCell）
const DateCell = defineComponent({
  props: { modelValue: [String, Object] },
  emits: ['update:modelValue'],
  setup(p, { emit }) {
    const editing = ref(false)
    const txt = computed(() => (p.modelValue ? String(p.modelValue).slice(0, 10) : ''))
    return () => editing.value
      ? h(ElDatePicker, {
        modelValue: txt.value, type: 'date', size: 'small', valueFormat: 'YYYY-MM-DD',
        style: 'width:112px', teleported: true,
        'onUpdate:modelValue': (v) => { editing.value = false; emit('update:modelValue', v || null) },
        onBlur: () => { editing.value = false },
      })
      : h('span', { class: txt.value ? 'datecell' : 'datecell blank', onClick: () => { editing.value = true } },
        txt.value || '点击填写')
  },
})

const route = useRoute()
const router = useRouter()
const isAdmin = auth.isAdmin
const plan = ref(null)
const items = ref([])
const users = ref([])
const groups = ref([])
const loading = ref(false)
const collapsed = ref(new Set())
const onlyFlag = ref(false)
const drawer = ref(false)
const drawerRow = ref(null)
const showDiagram = ref(false)
const timelineOn = ref(false)
// 顺着前置跳过去的那一行：高亮留着不自动消，弹窗一关还看得见自己跳到了哪儿
const hlId = ref(null)
const diagramRef = ref(null)
const exporting = ref(false)
// 0 ＝ 全部。默认全部：先给全量，要收再收——默认砍掉几层的话，
// 导出的人根本不知道自己少拿了东西
const exportDepth = ref(0)
const dform = reactive({ deliverable: '', dod: '', predecessor_ids: [], remark: '' })

const ymd = (v) => (v ? String(v).slice(0, 10) : '—')
const numOrNull = (v) => (v === '' || v === null || v === undefined ? null : Number(v))
const clampPct = (v) => Math.max(0, Math.min(100, Number(v) || 0))
const statusStyle = (s) => (FILL[s] ? { background: FILL[s], color: '#1F242E' } : {})
// 编号跟着名字一起分档，但不跟着加粗：一列等宽数字全加粗会比名字还抢眼
const codeStyle = (d) => ({ ...levelStyle(d), fontWeight: 400 })

// 只列到「树里真有的那么深」+ 全部：铺一堆点进去和全量一样的档位没有意义
const depthOptions = computed(() => {
  const max = plan.value?.max_depth || 1
  const out = [{ value: 0, label: '导出全部层级' }]
  for (let d = 1; d < max; d += 1) out.push({ value: d, label: `只导出到第 ${d} 层` })
  return out
})

async function exportXlsx() {
  exporting.value = true
  try {
    const { data } = await wbsApi.exportXlsx(plan.value.id, exportDepth.value || null)
    const suffix = exportDepth.value ? `-第${exportDepth.value}层` : ''
    downloadBlob(data, `${plan.value.name || 'wbs'}${suffix}-${new Date().toISOString().slice(0, 10)}.xlsx`)
    ElMessage.success('已导出（第 1 页是表，第 2 页是调试框图，第 3 页是 A 图）')
  } catch (e) {
    ElMessage.error(apiError(e, '导出失败'))
  } finally {
    exporting.value = false
  }
}

// 收起某一行时，它整棵子树都不显示——只藏直接子行的话，孙行会浮在外面变成孤儿
const visible = computed(() => {
  const out = []
  let hideDepth = null
  for (const r of items.value) {
    if (hideDepth !== null) {
      if (r.depth > hideDepth) continue
      hideDepth = null
    }
    if (onlyFlag.value && r.is_leaf && !r.issues.length) continue
    out.push(r)
    if (!r.is_leaf && collapsed.value.has(r.id)) hideDepth = r.depth
  }
  return out
})
function rowClass({ row }) {
  const base = row.issues.length ? 'flagged' : (row.is_leaf ? 'leaf' : 'parent')
  return row.id === hlId.value ? `${base} hl` : base
}
function toggle(id) {
  const s = new Set(collapsed.value)
  s.has(id) ? s.delete(id) : s.add(id)
  collapsed.value = s
}
function expandAll(open) {
  collapsed.value = open ? new Set() : new Set(items.value.filter((r) => !r.is_leaf).map((r) => r.id))
}

function apply(data) {
  plan.value = data
  items.value = data.items || []
}
async function load() {
  loading.value = true
  try {
    const [d, u, g] = await Promise.all([
      wbsApi.detail(route.params.id), userApi.list(), resourceGroupApi.list(),
    ])
    apply(d.data)
    users.value = u.data
    groups.value = g.data
  } catch (e) {
    ElMessage.error(apiError(e, '加载 WBS 失败'))
  } finally {
    loading.value = false
  }
}

// 每次写操作都拿服务端回的整份详情覆盖：汇总口径只有服务端一份，
// 前端就地改一格再自己往上加，迟早和服务端算的对不上
async function call(fn, okMsg) {
  try {
    const { data } = await fn()
    apply(data)
    // 图跟着树走：不重拉的话，加了一行之后图还停在上一版，而页面和图看着都对
    if (showDiagram.value) diagramRef.value?.reload()
    if (okMsg) ElMessage.success(okMsg)
    return true
  } catch (e) {
    ElMessage.error(apiError(e, '保存失败'))
    await load()      // 409 之类：拉回最新的，别让页面停在一个改坏了的状态
    return false
  }
}
const patch = (row, data) => call(() => wbsApi.updateItem(row.id, { ...data, version: row.version }))
const addRow = (parentId) => call(() => wbsApi.addItem(route.params.id, { parent_id: parentId, name: parentId ? '新子项' : '新分组' }))
const applyTpl = () => call(() => wbsApi.applyTemplate(route.params.id), '已生成标准分组')

async function removeRow(row) {
  const kids = items.value.filter((r) => r.code.startsWith(row.code + '.')).length
  const msg = kids ? `「${row.name}」下面还有 ${kids} 行，一并删除？` : `删除「${row.name}」？`
  try { await ElMessageBox.confirm(msg, '确认', { type: 'warning' }) } catch { return }
  await call(() => wbsApi.removeItem(row.id))
}

// ── 层级与顺序 ──────────────────────────────────────────────
const siblings = (row) => items.value.filter((r) => r.parent_id === row.parent_id)
function canDemote(row) {
  const sib = siblings(row)
  return sib.indexOf(sib.find((r) => r.id === row.id)) > 0     // 有前一个兄弟才能挂进去
}
function demote(row) {
  const sib = siblings(row)
  const i = sib.findIndex((r) => r.id === row.id)
  if (i <= 0) return
  return call(() => wbsApi.move(row.id, sib[i - 1].id, row.version))
}
function promote(row) {
  const parent = items.value.find((r) => r.id === row.parent_id)
  if (!parent) return
  return call(() => wbsApi.move(row.id, parent.parent_id ?? null, row.version))
}
function shift(row, dir) {
  const sib = siblings(row)
  const i = sib.findIndex((r) => r.id === row.id)
  const j = i + dir
  if (i < 0 || j < 0 || j >= sib.length) return
  const ids = sib.map((r) => r.id)
  ids.splice(j, 0, ids.splice(i, 1)[0])
  return call(() => wbsApi.reorder(route.params.id, row.parent_id ?? null, ids))
}

// ── 抽屉：长字段摊在表里的话一行要横拉到底 ──────────────────
function openDrawer(row) {
  drawerRow.value = row
  Object.assign(dform, {
    deliverable: row.deliverable || '', dod: row.dod || '',
    // 回填的是**服务端给的那几个 id**（含指向已删除行的那些）：照着现算的编号
    // 反填的话，行一挪编号就变了，等于每次打开都换一批关联
    predecessor_ids: (row.predecessors || []).map((p) => p.id),
    remark: row.remark || '',
  })
  drawer.value = true
}
async function saveDrawer() {
  if (await patch(drawerRow.value, { ...dform })) drawer.value = false
}

// 前置可选项＝这份 WBS 里除自己以外的全部行（含分组：一整段做完才能开下一段
// 是常态）。**不排除子孙**：前置只是先后，不是层级，拦掉反而会让人绕着填
const predOptions = computed(() => items.value
  .filter((r) => r.id !== drawerRow.value?.id)
  .map((r) => ({ id: r.id, label: `${r.code} ${r.name}` })))

// 选了就能点，不用先保存。编号取**页面上这一份**（服务端算好发下来的），
// 不在前端按位置另算一遍
const predLinks = computed(() => (dform.predecessor_ids || []).map((id) => {
  const it = items.value.find((r) => r.id === id)
  return it ? { id, code: it.code, name: it.name, missing: false }
    : { id, code: '', name: '', missing: true }
}))

/** 顺着前置切到那一行：展开它的上级、滚过去、高亮，并把抽屉换成它自己的。 */
function gotoItem(id) {
  const row = items.value.find((r) => r.id === id)
  if (!row) { ElMessage.warning('这条前置指向的工作包已经被删掉了'); return }
  // 上级收着的话跳过去那一行根本不在 DOM 里，看着像"点了没反应"
  const s = new Set(collapsed.value)
  let cur = row
  while (cur?.parent_id) {
    s.delete(cur.parent_id)
    cur = items.value.find((r) => r.id === cur.parent_id)
  }
  collapsed.value = s
  onlyFlag.value = false      // 「只看待补录」开着时目标行可能被筛掉了
  hlId.value = id
  openDrawer(row)
  nextTick(() => {
    document.querySelector('.wbs-table .hl')?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  })
}

/** 老写法那一行值只在人确认之后才清，不在保存时顺手抹掉——那上面是别人填的东西。 */
function dropLegacy() {
  if (drawerRow.value) patch(drawerRow.value, { predecessor: '' })
}

async function rename() {
  try {
    const { value } = await ElMessageBox.prompt('WBS 名称', '重命名', { inputValue: plan.value.name })
    if (!value || !value.trim()) return
    if (await call(() => wbsApi.updatePlan(plan.value.id, { name: value.trim(), version: plan.value.version }))) {
      await reloadWbs()
    }
  } catch { /* 取消 */ }
}
async function removePlan() {
  try {
    await ElMessageBox.confirm(`删除「${plan.value.name}」及它下面的全部工作包？`, '确认', { type: 'warning' })
  } catch { return }
  try {
    await wbsApi.removePlan(plan.value.id)
    await reloadWbs()
    router.push('/wbs')
  } catch (e) {
    ElMessage.error(apiError(e, '删除失败'))
  }
}

watch(() => route.params.id, load)
onMounted(load)
</script>

<style scoped>
.page { padding: 4px 2px 24px; }
/* 顺着前置跳过去的那一行：**高亮不自动消**，不然滚过去的一瞬间就没了，
   人还得自己找是哪一行（:deep 是因为行的 class 由 el-table 挂在内部节点上） */
.wbs-table :deep(.hl > td) { background: #FDF6EC !important; box-shadow: inset 0 0 0 1px #E6A23C; }
.predlinks { margin-top: 6px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.predlinks .ptip { color: #909399; font-size: 12px; }
.predlinks .pgone { color: #F56C6C; font-size: 12px; }
.plegacy { margin-top: 6px; color: #8a6d3b; background: #fdf6ec; border-left: 3px solid #E6A23C;
  border-radius: 3px; padding: 5px 9px; font-size: 12px; line-height: 1.7; }
.dlg-foot { color: #909399; font-size: 12px; line-height: 1.7; display: block; text-align: left; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 12px; }
.page-head h2 { margin: 2px 0 4px; font-size: 18px; }
.crumb a { color: #409EFF; text-decoration: none; font-size: 12px; }
.sub { color: #909399; font-size: 12.5px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.sub b { color: #303133; }
.sep { width: 1px; height: 12px; background: #dcdfe6; margin: 0 6px; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 10px; }
.stat { background: #fff; border: 1px solid #ebeef5; border-radius: 4px; padding: 9px 12px; }
.stat .k { color: #909399; font-size: 12px; }
.stat .v { font-size: 22px; font-weight: 700; color: #303133; font-variant-numeric: tabular-nums; }
.stat .n { color: #c0c4cc; font-size: 11px; }
.stat.flagged .v { color: #f56c6c; }
.excluded { background: #fff; border: 1px solid #ebeef5; border-left: 3px solid #409EFF;
  border-radius: 3px; padding: 7px 12px; margin-bottom: 12px; color: #606266; font-size: 12px; }
.tools { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.grow { flex: 1 1 auto; }
.diagram { margin-bottom: 12px; }
.codecell { display: flex; align-items: center; white-space: nowrap; }
.indent { display: inline-block; flex: 0 0 auto; }
.code { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 11.5px; color: #606266; }
.caret { display: inline-block; width: 18px; flex: 0 0 auto; padding: 0; }
.cell :deep(.el-input__wrapper), .cell :deep(.el-select__wrapper) { box-shadow: none; background: transparent; padding: 0 4px; }
.cell :deep(.el-input__wrapper):hover, .cell :deep(.el-select__wrapper):hover { box-shadow: 0 0 0 1px #dcdfe6 inset; }
.num :deep(input) { text-align: right; font-variant-numeric: tabular-nums; }
.status :deep(.el-select__wrapper) { background: inherit; }
.roll { font-variant-numeric: tabular-nums; color: #606266; }
.roll .tag { font-style: normal; font-size: 10px; color: #c0c4cc; margin-left: 3px; }
.warn { color: #f56c6c; background: #fdecec; border-radius: 2px; padding: 0 5px; font-size: 11px; margin-left: 4px; cursor: help; }
.del { color: #909399; }
.del:hover { color: #f56c6c; }
.muted { color: #909399; }
:deep(.el-table .flagged td:first-child) { box-shadow: inset 3px 0 0 #f56c6c; }
:deep(.el-table .parent) { background: #fafbfc; font-weight: 600; }
:deep(.datecell) { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 11.5px; cursor: text; }
:deep(.datecell.blank) { color: #c0c4cc; }
.notes { margin-top: 18px; background: #fff; border: 1px solid #ebeef5; border-radius: 4px; padding: 12px 16px; }
.notes h3 { margin: 0 0 8px; font-size: 13px; color: #c7000b; }
.notes li { color: #606266; margin-bottom: 7px; font-size: 12.5px; line-height: 1.7; }
.notes code { background: #f5f7fa; border-radius: 2px; padding: 0 4px; font-size: 11.5px; }
.dcode { color: #909399; font-size: 12px; margin-bottom: 10px; }
</style>
