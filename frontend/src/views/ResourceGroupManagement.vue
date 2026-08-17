<template>
  <div class="rg-page">
    <el-card shadow="never">
      <div class="toolbar">
        <el-button type="primary" :icon="Plus" @click="openDeptDialog()">新增部门</el-button>
        <el-button :icon="Plus" :disabled="!selectedDept" @click="openPlDialog()">
          {{ selectedDept ? `新增 PL 组到「${selectedDept.name}」` : '新增 PL 组（先选部门）' }}
        </el-button>
        <el-button :icon="Refresh" @click="loadAll">刷新</el-button>
        <el-checkbox v-model="includeInactive" @change="loadAll">显示停用</el-checkbox>
        <span class="muted-hint">两级结构：部门 → PL 组。code 创建后不可改；删除前需先把成员/子组挪走。</span>
      </div>

      <div class="two-pane">
        <!-- 左侧：部门列表 -->
        <div class="pane left">
          <div class="pane-header">
            部门 <span class="muted">（{{ depts.length }}）</span>
          </div>
          <div class="dept-list" v-loading="loading">
            <div
              v-for="d in depts"
              :key="d.id"
              class="dept-card"
              :class="{ active: selectedDeptId === d.id, dim: !d.is_active }"
              @click="selectedDeptId = d.id"
            >
              <div class="dept-name">
                {{ d.name }}
                <el-tag v-if="!d.is_active" size="small" type="info" effect="plain">停用</el-tag>
              </div>
              <div class="dept-meta">
                <span class="code">{{ d.code }}</span>
                <span class="muted" v-if="d.leader_name">负责人：{{ d.leader_name }}</span>
              </div>
              <div class="dept-actions">
                <el-button size="small" link @click.stop="openDeptDialog(d)">编辑</el-button>
                <el-button size="small" link type="danger" @click.stop="onRemoveGroup(d)">删除</el-button>
              </div>
            </div>
            <el-empty v-if="!depts.length" description="暂无部门" />
          </div>
        </div>

        <!-- 右侧：选中部门下的 PL 组 -->
        <div class="pane right">
          <div class="pane-header">
            PL 组
            <span class="muted" v-if="selectedDept">— {{ selectedDept.name }}（{{ plsOfSelected.length }}）</span>
          </div>
          <el-table :data="plsOfSelected" border stripe size="small" v-loading="loading">
            <el-table-column type="index" label="#" width="50" align="center" />
            <el-table-column prop="code" label="Code" width="120" />
            <el-table-column prop="name" label="名称" min-width="160" />
            <el-table-column label="负责人" width="140">
              <template #default="{ row }">{{ row.leader_name || '—' }}</template>
            </el-table-column>
            <el-table-column label="成员数" width="80" align="center">
              <template #default="{ row }">{{ row.member_count || 0 }}</template>
            </el-table-column>
            <el-table-column label="状态" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                  {{ row.is_active ? '启用' : '停用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="sort_order" label="排序" width="80" align="center" />
            <el-table-column label="操作" width="160" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="openPlDialog(row)">编辑</el-button>
                <el-button size="small" type="danger" @click="onRemoveGroup(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="selectedDept && !plsOfSelected.length" description="该部门下还没有 PL 组" />
          <el-empty v-if="!selectedDept" description="请选择左侧部门查看其 PL 组" />
        </div>
      </div>
    </el-card>

    <!-- 新增/编辑部门 -->
    <el-dialog v-model="deptDialog.visible" :title="deptDialog.id ? '编辑部门' : '新增部门'" width="520px">
      <el-form :model="deptDialog.form" label-width="100px">
        <el-form-item label="Code" required>
          <el-input
            v-model="deptDialog.form.code"
            :disabled="!!deptDialog.id"
            placeholder="如 DEPT-FW（创建后不可改）"
          />
        </el-form-item>
        <el-form-item label="部门名" required>
          <el-input v-model="deptDialog.form.name" placeholder="如 固件部" />
        </el-form-item>
        <el-form-item label="部门长">
          <el-select v-model="deptDialog.form.leader_id" filterable clearable placeholder="可不选">
            <el-option
              v-for="u in userOptions"
              :key="u.id"
              :value="u.id"
              :label="u.full_name || u.username"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="deptDialog.form.sort_order" :min="0" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="deptDialog.form.is_active" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="deptDialog.form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="deptDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="submitDept">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新增/编辑 PL 组 -->
    <el-dialog v-model="plDialog.visible" :title="plDialog.id ? '编辑 PL 组' : '新增 PL 组'" width="520px">
      <el-form :model="plDialog.form" label-width="100px">
        <el-form-item label="Code" required>
          <el-input
            v-model="plDialog.form.code"
            :disabled="!!plDialog.id"
            placeholder="如 PL-FW-CORE（创建后不可改）"
          />
        </el-form-item>
        <el-form-item label="所属部门" required>
          <el-select v-model="plDialog.form.parent_id" placeholder="选择部门">
            <el-option
              v-for="d in depts"
              :key="d.id"
              :value="d.id"
              :label="d.name"
              :disabled="!d.is_active"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="PL 组名" required>
          <el-input v-model="plDialog.form.name" placeholder="如 固件核心组" />
        </el-form-item>
        <el-form-item label="组长">
          <el-select v-model="plDialog.form.leader_id" filterable clearable placeholder="可不选">
            <el-option
              v-for="u in userOptions"
              :key="u.id"
              :value="u.id"
              :label="u.full_name || u.username"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="plDialog.form.sort_order" :min="0" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="plDialog.form.is_active" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="plDialog.form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="plDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="submitPl">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { resourceGroupApi, userApi } from '../api'

const loading = ref(false)
const includeInactive = ref(true)
const groups = ref([])                  // 全部（部门 + PL组）
const userOptions = ref([])

const selectedDeptId = ref(null)
const depts = computed(() => groups.value.filter((g) => g.kind === 'dept'))
const selectedDept = computed(() => depts.value.find((d) => d.id === selectedDeptId.value))
const plsOfSelected = computed(() =>
  groups.value.filter((g) => g.kind === 'pl' && g.parent_id === selectedDeptId.value)
)

async function loadAll() {
  loading.value = true
  try {
    const [{ data: gs }, { data: us }] = await Promise.all([
      resourceGroupApi.list({ include_inactive: includeInactive.value }),
      userApi.options({ only_can_login: false }),
    ])
    groups.value = gs
    userOptions.value = us
    // 默认选中第一个启用的部门
    if (!selectedDeptId.value || !depts.value.find((d) => d.id === selectedDeptId.value)) {
      const first = depts.value.find((d) => d.is_active) || depts.value[0]
      selectedDeptId.value = first ? first.id : null
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)

// ─── 部门 ───────────────────────────────────────────
const deptDialog = reactive({ visible: false, id: null, form: defaultDeptForm() })

function defaultDeptForm() {
  return { code: '', name: '', leader_id: null, sort_order: 0, is_active: true, remark: '' }
}

function openDeptDialog(row) {
  if (row) {
    deptDialog.id = row.id
    Object.assign(deptDialog.form, {
      code: row.code,
      name: row.name,
      leader_id: row.leader_id,
      sort_order: row.sort_order || 0,
      is_active: !!row.is_active,
      remark: row.remark || '',
    })
  } else {
    deptDialog.id = null
    Object.assign(deptDialog.form, defaultDeptForm(), { sort_order: depts.value.length })
  }
  deptDialog.visible = true
}

async function submitDept() {
  const f = deptDialog.form
  if (!f.code.trim() || !f.name.trim()) {
    ElMessage.warning('code 和 name 必填')
    return
  }
  try {
    if (deptDialog.id) {
      await resourceGroupApi.update(deptDialog.id, {
        name: f.name.trim(),
        leader_id: f.leader_id,
        sort_order: f.sort_order,
        is_active: f.is_active,
        remark: f.remark,
      })
    } else {
      await resourceGroupApi.create({
        code: f.code.trim(),
        name: f.name.trim(),
        kind: 'dept',
        parent_id: null,
        leader_id: f.leader_id,
        sort_order: f.sort_order,
        is_active: f.is_active,
        remark: f.remark,
      })
    }
    ElMessage.success('已保存')
    deptDialog.visible = false
    await loadAll()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

// ─── PL 组 ──────────────────────────────────────────
const plDialog = reactive({ visible: false, id: null, form: defaultPlForm() })

function defaultPlForm() {
  return { code: '', name: '', parent_id: null, leader_id: null, sort_order: 0, is_active: true, remark: '' }
}

function openPlDialog(row) {
  if (row) {
    plDialog.id = row.id
    Object.assign(plDialog.form, {
      code: row.code,
      name: row.name,
      parent_id: row.parent_id,
      leader_id: row.leader_id,
      sort_order: row.sort_order || 0,
      is_active: !!row.is_active,
      remark: row.remark || '',
    })
  } else {
    plDialog.id = null
    Object.assign(plDialog.form, defaultPlForm(), {
      parent_id: selectedDeptId.value,
      sort_order: plsOfSelected.value.length,
    })
  }
  plDialog.visible = true
}

async function submitPl() {
  const f = plDialog.form
  if (!f.code.trim() || !f.name.trim()) {
    ElMessage.warning('code 和 name 必填')
    return
  }
  if (!f.parent_id) {
    ElMessage.warning('请选择所属部门')
    return
  }
  try {
    if (plDialog.id) {
      await resourceGroupApi.update(plDialog.id, {
        name: f.name.trim(),
        parent_id: f.parent_id,
        leader_id: f.leader_id,
        sort_order: f.sort_order,
        is_active: f.is_active,
        remark: f.remark,
      })
    } else {
      await resourceGroupApi.create({
        code: f.code.trim(),
        name: f.name.trim(),
        kind: 'pl',
        parent_id: f.parent_id,
        leader_id: f.leader_id,
        sort_order: f.sort_order,
        is_active: f.is_active,
        remark: f.remark,
      })
    }
    ElMessage.success('已保存')
    plDialog.visible = false
    await loadAll()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function onRemoveGroup(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除「${row.name}」？${row.kind === 'dept' ? '该部门下不能再有 PL 组' : '该 PL 组下不能再有成员'}`,
      '提示',
      { type: 'warning' }
    )
  } catch { return }
  try {
    await resourceGroupApi.remove(row.id)
    ElMessage.success('已删除')
    await loadAll()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}
</script>

<style scoped>
.rg-page { padding: 0; }
.toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.muted-hint { color: #909399; font-size: 12px; margin-left: auto; }
.two-pane { display: grid; grid-template-columns: 320px 1fr; gap: 16px; }
.pane { background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px; padding: 10px 12px; min-height: 320px; }
.pane-header { font-weight: 600; color: #303133; padding-bottom: 8px; border-bottom: 1px solid #ebeef5; margin-bottom: 8px; }
.muted { color: #909399; font-size: 12px; font-weight: normal; }
.dept-list { display: flex; flex-direction: column; gap: 6px; }
.dept-card {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: white;
  padding: 8px 10px;
  cursor: pointer;
  transition: all 0.15s;
}
.dept-card:hover { border-color: #409eff; }
.dept-card.active { border-color: #409eff; background: #ecf5ff; }
.dept-card.dim { opacity: 0.6; }
.dept-name { font-weight: 600; color: #303133; display: flex; align-items: center; gap: 6px; }
.dept-meta { color: #909399; font-size: 12px; margin-top: 4px; display: flex; gap: 12px; }
.dept-meta .code { font-family: monospace; color: #606266; }
.dept-actions { margin-top: 4px; text-align: right; }
</style>
