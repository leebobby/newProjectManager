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
      </div>

      <el-empty v-if="!items.length" description="这份 WBS 还是空的">
        <span class="muted">可以「套用标准调试模板」一次生成 6 个分组，再往里逐层拆；也可以直接新增一个分组。</span>
      </el-empty>

      <el-table v-else :data="visible" border size="small" row-key="id"
                :row-class-name="rowClass">
        <el-table-column label="编号" width="104">
          <template #default="{ row }">
            <span :style="{ paddingLeft: (row.depth - 1) * 16 + 'px' }" />
            <el-button v-if="!row.is_leaf" link class="caret" @click="toggle(row.id)">
              {{ collapsed.has(row.id) ? '▸' : '▾' }}
            </el-button>
            <span v-else class="caret" />
            <span class="code">{{ row.code }}</span>
          </template>
        </el-table-column>
        <el-table-column label="工作包" min-width="230">
          <template #default="{ row }">
            <el-input v-model="row.name" size="small" class="cell"
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

      <el-drawer v-model="drawer" :title="drawerRow?.name || '工作包详情'" size="440px">
        <div class="dcode">WBS {{ drawerRow?.code }} · 第 {{ drawerRow?.depth }} 层 ·
          {{ drawerRow?.is_leaf ? '叶子（可填人天/完成度/状态）' : '父行（人天、完成度、日期均为汇总）' }}</div>
        <el-form label-position="top">
          <el-form-item label="交付物"><el-input v-model="dform.deliverable" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="完成标准（DoD）"><el-input v-model="dform.dod" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="前置 WBS（编号，逗号分隔）"><el-input v-model="dform.predecessor" /></el-form-item>
          <el-form-item label="假设 · 范围外 · 风险"><el-input v-model="dform.remark" type="textarea" :rows="3" /></el-form-item>
        </el-form>
        <el-button type="primary" @click="saveDrawer">保存</el-button>
        <el-button @click="drawer = false">关闭</el-button>
      </el-drawer>
    </template>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElDatePicker, ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { apiError, resourceGroupApi, userApi, wbsApi } from '../api'
import { auth } from '../store/auth'
import { reloadWbs } from '../store/wbs'

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
const dform = reactive({ deliverable: '', dod: '', predecessor: '', remark: '' })

const ymd = (v) => (v ? String(v).slice(0, 10) : '—')
const numOrNull = (v) => (v === '' || v === null || v === undefined ? null : Number(v))
const clampPct = (v) => Math.max(0, Math.min(100, Number(v) || 0))
const statusStyle = (s) => (FILL[s] ? { background: FILL[s], color: '#1F242E' } : {})

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
function rowClass({ row }) { return row.issues.length ? 'flagged' : (row.is_leaf ? 'leaf' : 'parent') }
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
    predecessor: row.predecessor || '', remark: row.remark || '',
  })
  drawer.value = true
}
async function saveDrawer() {
  if (await patch(drawerRow.value, { ...dform })) drawer.value = false
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
.tools { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.code { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 11.5px; color: #606266; }
.caret { display: inline-block; width: 18px; padding: 0; }
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
