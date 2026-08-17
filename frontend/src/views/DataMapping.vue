<template>
  <div>
    <el-card shadow="never">
      <div class="header">
        <h3 style="margin: 0">数据对账</h3>
        <span class="muted-hint">
          把历史字符串字段（客户名 / 人员姓名）绑定到主数据。先尝试自动匹配，剩下的手动认。
        </span>
      </div>

      <el-tabs v-model="active">
        <!-- 客户对账 -->
        <el-tab-pane label="客户对账" name="customer">
          <div class="bar">
            <el-button type="primary" @click="onAutoFillCustomers" :loading="customer.autoFilling">
              自动按 code/别名 回填
            </el-button>
            <el-button :icon="Refresh" @click="loadCustomers">刷新</el-button>
            <span class="muted-hint" v-if="customer.lastResult">
              上次：匹配 {{ customer.lastResult.matched }} 条，剩余 {{ customer.lastResult.unmatched }} 条未匹配
            </span>
          </div>

          <el-table
            :data="customer.rows"
            v-loading="customer.loading"
            border
            stripe
            size="small"
            empty-text="没有未对账的客户记录 🎉"
          >
            <el-table-column label="来源" width="180">
              <template #default="{ row }">
                <el-tag size="small" :type="row.source === 'customer_status' ? 'primary' : 'success'">
                  {{ row.source === 'customer_status' ? '客户面状态' : '战场矩阵' }}
                </el-tag>
                <span class="muted" style="margin-left: 6px">#{{ row.id }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="battlefield" label="原字符串值" min-width="180" />
            <el-table-column prop="extra" label="辅助信息" width="160" />
            <el-table-column label="绑定到客户" min-width="240">
              <template #default="{ row }">
                <el-select
                  v-model="row._pickCustomerId"
                  filterable
                  clearable
                  placeholder="选择客户"
                  style="width: 100%"
                >
                  <el-option
                    v-for="cu in customers"
                    :key="cu.id"
                    :value="cu.id"
                    :label="`${cu.code}${cu.display_name ? ' / ' + cu.display_name : ''}`"
                  />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="primary" @click="assignCustomer(row)">绑定</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 人员对账 -->
        <el-tab-pane label="人员对账" name="person">
          <div class="bar">
            <el-button type="primary" @click="onAutoFillPersons" :loading="person.autoFilling">
              自动按工号/姓名匹配
            </el-button>
            <el-button :icon="Refresh" @click="loadPersons">刷新</el-button>
            <span class="muted-hint" v-if="person.lastResult">
              上次：工号匹配 {{ person.lastResult.matched_by_emp_no }}，姓名匹配 {{ person.lastResult.matched_by_name }}，剩余 {{ person.lastResult.unmatched }}
            </span>
          </div>

          <el-table
            :data="person.rows"
            v-loading="person.loading"
            border
            stripe
            size="small"
            empty-text="没有未对账的阵型成员 🎉"
          >
            <el-table-column prop="name" label="姓名" width="100" />
            <el-table-column prop="emp_no" label="工号" width="100" />
            <el-table-column prop="pl_group" label="PL组" width="120" />
            <el-table-column prop="role" label="角色" width="100" />
            <el-table-column label="系统建议" width="180">
              <template #default="{ row }">
                <span v-if="row.suggest_user_id">
                  <el-tag size="small" :type="row.suggest_reason === 'emp_no' ? 'success' : 'warning'">
                    {{ row.suggest_reason === 'emp_no' ? '工号匹配' : '姓名匹配' }}
                  </el-tag>
                  {{ row.suggest_user_name }}
                </span>
                <span v-else class="muted">无</span>
              </template>
            </el-table-column>
            <el-table-column label="绑定到用户" min-width="240">
              <template #default="{ row }">
                <el-select
                  v-model="row._pickUserId"
                  filterable
                  clearable
                  placeholder="选择 User"
                  style="width: 100%"
                >
                  <el-option
                    v-for="u in userOptions"
                    :key="u.id"
                    :value="u.id"
                    :label="`${u.full_name || u.username}${u.emp_no ? ' (' + u.emp_no + ')' : ''}`"
                  />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="primary" @click="assignPerson(row)">绑定</el-button>
                <el-button size="small" @click="openCreateFromMember(row)">建档</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 一键建档对话框 -->
    <el-dialog v-model="createDialog.visible" title="一键建档" width="460px">
      <p>
        将为阵型成员
        <b>{{ createDialog.member?.name }}</b>
        创建一个"纯人员档案"账号（不能登录），并自动绑定。
      </p>
      <el-form :model="createDialog.form" label-width="80px">
        <el-form-item label="登录名">
          <el-input v-model="createDialog.form.username" placeholder="建议使用工号" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="submitCreateFromMember">创建并绑定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { customerApi, mappingApi, userApi } from '../api'

const active = ref('customer')

const customers = ref([])
const userOptions = ref([])

const customer = reactive({ rows: [], loading: false, autoFilling: false, lastResult: null })
const person = reactive({ rows: [], loading: false, autoFilling: false, lastResult: null })

async function loadCustomers() {
  customer.loading = true
  try {
    const [{ data: rows }, { data: cs }] = await Promise.all([
      mappingApi.customerUnmapped(),
      customerApi.list(true),
    ])
    customer.rows = rows.map((r) => ({ ...r, _pickCustomerId: null }))
    customers.value = cs
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    customer.loading = false
  }
}

async function loadPersons() {
  person.loading = true
  try {
    const [{ data: rows }, { data: us }] = await Promise.all([
      mappingApi.personUnmapped(),
      userApi.options({ include_inactive: true }),
    ])
    person.rows = rows.map((r) => ({ ...r, _pickUserId: r.suggest_user_id || null }))
    userOptions.value = us
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    person.loading = false
  }
}

async function onAutoFillCustomers() {
  customer.autoFilling = true
  try {
    const { data } = await mappingApi.customerAutoFill()
    customer.lastResult = data
    ElMessage.success(`已自动匹配 ${data.matched} 条，剩余 ${data.unmatched} 条`)
    await loadCustomers()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '自动匹配失败')
  } finally {
    customer.autoFilling = false
  }
}

async function onAutoFillPersons() {
  person.autoFilling = true
  try {
    const { data } = await mappingApi.personAutoFill()
    person.lastResult = data
    ElMessage.success(
      `按工号匹配 ${data.matched_by_emp_no}，按姓名匹配 ${data.matched_by_name}，剩余 ${data.unmatched}`
    )
    await loadPersons()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '自动匹配失败')
  } finally {
    person.autoFilling = false
  }
}

async function assignCustomer(row) {
  if (!row._pickCustomerId) {
    ElMessage.warning('请先选择客户')
    return
  }
  try {
    await mappingApi.customerAssign({
      source: row.source,
      id: row.id,
      customer_id: row._pickCustomerId,
    })
    ElMessage.success('已绑定')
    await loadCustomers()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '绑定失败')
  }
}

async function assignPerson(row) {
  if (!row._pickUserId) {
    ElMessage.warning('请先选择 User')
    return
  }
  try {
    await mappingApi.personAssign({
      member_id: row.id,
      user_id: row._pickUserId,
    })
    ElMessage.success('已绑定')
    await loadPersons()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '绑定失败')
  }
}

// ─── 一键建档 ────────────────────────────────────────────
const createDialog = reactive({ visible: false, member: null, form: { username: '' } })

function openCreateFromMember(row) {
  createDialog.member = row
  createDialog.form.username = row.emp_no || row.name || ''
  createDialog.visible = true
}

async function submitCreateFromMember() {
  if (!createDialog.form.username.trim()) {
    ElMessage.warning('请填写登录名')
    return
  }
  try {
    await mappingApi.personCreateFromMember({
      member_id: createDialog.member.id,
      username: createDialog.form.username.trim(),
    })
    ElMessage.success('已创建并绑定')
    createDialog.visible = false
    await loadPersons()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '建档失败')
  }
}

onMounted(() => {
  loadCustomers()
  loadPersons()
})
</script>

<style scoped>
.header { display: flex; align-items: baseline; gap: 16px; margin-bottom: 12px; }
.muted-hint { color: #909399; font-size: 12px; }
.bar { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }
.muted { color: #c0c4cc; font-size: 12px; }
</style>
