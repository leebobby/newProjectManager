<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>WBS</h2>
        <div class="sub">
          一份 WBS 挂在一个<b>专项</b>或一台<b>机台调试</b>上，层数不限。
          左侧「WBS」下的二级菜单里一份一条，点进去是它自己的页面。
        </div>
      </div>
      <el-button type="primary" :icon="Plus" @click="openNew">新建 WBS</el-button>
    </div>

    <el-alert v-if="!loading && !plans.length" type="info" :closable="false" show-icon
              title="还没有 WBS" style="margin-bottom: 12px">
      比如「视觉标定特性调试 WBS」挂在专项下，「西安3号机现场调试 WBS」挂在机台下。
      建完可以一键套用标准调试模板，再往里逐层拆。
    </el-alert>

    <el-table v-loading="loading" :data="plans" border stripe size="small"
              @row-click="(r) => router.push(`/wbs/${r.id}`)" class="clickable">
      <el-table-column prop="name" label="名称" min-width="220">
        <template #default="{ row }"><span class="nm">{{ row.name }}</span></template>
      </el-table-column>
      <el-table-column label="归属" min-width="200">
        <template #default="{ row }">
          <el-tag size="small" :type="row.kind === 'machine' ? 'warning' : 'info'" effect="plain">
            {{ row.kind_label }}
          </el-tag>
          <span style="margin-left: 6px">{{ row.ref_name || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="owner" label="负责人" width="100">
        <template #default="{ row }">{{ row.owner || '—' }}</template>
      </el-table-column>
      <el-table-column label="工作包" width="90" align="right">
        <template #default="{ row }"><span class="num">{{ row.leaf_count || '—' }}</span></template>
      </el-table-column>
      <el-table-column label="人天" width="86" align="right">
        <template #default="{ row }"><span class="num">{{ row.total_days || '—' }}</span></template>
      </el-table-column>
      <el-table-column label="完成度" width="150">
        <template #default="{ row }">
          <el-progress :percentage="row.progress_pct" :stroke-width="10" />
        </template>
      </el-table-column>
      <el-table-column label="计划窗口" width="210">
        <template #default="{ row }">
          <span class="num">{{ ymd(row.planned_start) }} → {{ ymd(row.planned_end) }}</span>
        </template>
      </el-table-column>
      <!-- 待补录单独一列：列表页存在的意义就是横着扫一眼哪份该去催，
           点进去一份份看的话这一列就白算了 -->
      <el-table-column label="待补录" width="96">
        <template #default="{ row }">
          <span :class="row.flagged ? 'flag' : 'muted'">{{ row.flagged ? row.flagged + ' 条' : '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="层深" width="72" align="center">
        <template #default="{ row }"><span class="muted">{{ row.max_depth || 0 }} 层</span></template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dlg" title="新建 WBS" width="520px">
      <el-form label-width="86px">
        <el-form-item label="归属">
          <el-radio-group v-model="form.kind" @change="onKind">
            <el-radio-button label="special">专项</el-radio-button>
            <el-radio-button label="machine">机台调试</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="form.kind === 'special' ? '专项' : '机台'">
          <el-select v-model="refId" filterable placeholder="请选择" style="width: 100%" @change="onRef">
            <el-option v-for="o in refOptions" :key="o.id" :label="o.label" :value="o.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" :placeholder="namePlaceholder" />
        </el-form-item>
        <el-form-item label="负责人">
          <el-select v-model="form.owner_user_id" filterable clearable placeholder="未指定" style="width: 100%">
            <el-option v-for="u in users" :key="u.id" :label="u.full_name || u.username" :value="u.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { apiError, customerStatusApi, specialApi, userApi, wbsApi } from '../api'
import { reloadWbs } from '../store/wbs'

const router = useRouter()
const plans = ref([])
const specials = ref([])
const machines = ref([])
const users = ref([])
const loading = ref(false)
const saving = ref(false)
const dlg = ref(false)
const refId = ref(null)
const form = reactive({ name: '', kind: 'special', special_id: null, machine_status_id: null, owner_user_id: null })

// 日期是用户填的，服务端不转时区，这里也只取日期部分（同 CLAUDE.md「时间」那一节）
const ymd = (v) => (v ? String(v).slice(0, 10) : '—')

const refOptions = computed(() =>
  form.kind === 'special'
    ? specials.value.map((s) => ({ id: s.id, label: s.name }))
    : machines.value.map((m) => ({ id: m.id, label: `${m.customer_name || ''} ${m.machine_id || ''}`.trim() })))
const namePlaceholder = computed(() => {
  const o = refOptions.value.find((x) => x.id === refId.value)
  return o ? `留空则用「${o.label} WBS」` : '如：视觉标定特性调试 WBS'
})

async function load() {
  loading.value = true
  try {
    const [p, s, m, u] = await Promise.all([
      wbsApi.listPlans(), specialApi.list(false), customerStatusApi.list(), userApi.list(),
    ])
    plans.value = p.data
    specials.value = s.data
    machines.value = m.data
    users.value = u.data
  } catch (e) {
    // 提示带上 HTTP 状态：500 / 超时 / 连不上是三种完全不同的故障
    ElMessage.error(apiError(e, '加载 WBS 列表失败'))
  } finally {
    loading.value = false
  }
}
function openNew() {
  form.name = ''
  form.kind = 'special'
  form.owner_user_id = null
  refId.value = null
  dlg.value = true
}
function onKind() { refId.value = null; onRef() }
function onRef() {
  form.special_id = form.kind === 'special' ? refId.value : null
  form.machine_status_id = form.kind === 'machine' ? refId.value : null
}
async function save() {
  onRef()
  if (!refId.value) { ElMessage.warning('先选一个归属对象'); return }
  const o = refOptions.value.find((x) => x.id === refId.value)
  const payload = { ...form, name: form.name.trim() || `${o ? o.label : ''} WBS`.trim() }
  saving.value = true
  try {
    const { data } = await wbsApi.createPlan(payload)
    dlg.value = false
    await reloadWbs()          // 侧栏二级菜单当场多一条
    router.push(`/wbs/${data.id}`)
  } catch (e) {
    ElMessage.error(apiError(e, '新建失败'))
  } finally {
    saving.value = false
  }
}
onMounted(load)
</script>

<style scoped>
.page { padding: 4px 2px 24px; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
.page-head h2 { margin: 0 0 4px; font-size: 18px; }
.sub { color: #909399; font-size: 12.5px; line-height: 1.7; max-width: 720px; }
.sub b { color: #606266; }
.clickable :deep(.el-table__row) { cursor: pointer; }
.nm { color: #409EFF; font-weight: 600; }
.num { font-variant-numeric: tabular-nums; }
.muted { color: #c0c4cc; }
.flag { color: #f56c6c; font-weight: 600; }
</style>
