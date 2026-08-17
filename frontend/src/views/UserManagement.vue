<template>
  <div>
    <el-card shadow="never">
      <div class="toolbar">
        <el-button type="primary" :icon="Plus" @click="openCreate">新增用户/人员</el-button>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
        <el-select
          v-model="filterGroupId"
          placeholder="按 PL 组筛选"
          clearable
          filterable
          style="width: 200px"
        >
          <el-option v-for="g in plGroups" :key="g.id" :value="g.id" :label="`${g.parent_name || '—'} / ${g.name}`" />
        </el-select>
        <el-input v-model="filter" placeholder="搜索登录名/姓名/工号" clearable style="margin-left: auto; width: 240px" />
      </div>

      <el-table :data="filtered" v-loading="loading" border stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="登录名" width="140" />
        <el-table-column prop="full_name" label="姓名" width="120" />
        <el-table-column prop="emp_no" label="工号" width="110">
          <template #default="{ row }">{{ row.emp_no || '—' }}</template>
        </el-table-column>
        <el-table-column label="部门 / PL 组" width="220">
          <template #default="{ row }">
            <span v-if="row.group_id">{{ row.dept_name || '—' }} / {{ row.group_name || '—' }}</span>
            <span v-else class="muted">未挂靠</span>
          </template>
        </el-table-column>
        <el-table-column prop="job_title" label="岗位" width="100">
          <template #default="{ row }">{{ row.job_title || '—' }}</template>
        </el-table-column>
        <el-table-column label="角色" width="90">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'info'" effect="dark" size="small">
              {{ row.role === 'admin' ? '管理员' : '普通用户' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="登录" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.can_login ? 'success' : 'warning'" size="small">
              {{ row.can_login ? '可登录' : '档案' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button
              size="small"
              type="danger"
              :disabled="row.id === auth.state.user?.id"
              @click="onDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑用户/人员' : '新增用户/人员'" width="560px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="允许登录">
          <el-switch v-model="form.can_login" />
          <span class="hint" v-if="!form.can_login">关闭后是"纯人员档案"，不参与登录，但可作为 owner 被选择</span>
        </el-form-item>
        <el-form-item label="登录名" required>
          <el-input v-model="form.username" :disabled="!!editing" placeholder="纯档案也建议给一个唯一标识，如 emp_no" />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="form.full_name" />
        </el-form-item>
        <el-form-item label="工号">
          <el-input v-model="form.emp_no" placeholder="可选" />
        </el-form-item>
        <el-form-item label="所属 PL 组">
          <el-select v-model="form.group_id" filterable clearable placeholder="选择 PL 组（部门由 PL 组反推）">
            <el-option
              v-for="g in plGroups"
              :key="g.id"
              :value="g.id"
              :label="`${g.parent_name || '—'} / ${g.name}`"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="岗位">
          <el-input v-model="form.job_title" placeholder="如 开发 / PM / 测试" />
        </el-form-item>
        <el-form-item v-if="form.can_login" :label="editing ? '重置密码' : '密码'">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :placeholder="editing ? '留空表示不修改' : '请输入密码'"
          />
        </el-form-item>
        <el-form-item v-if="form.can_login" label="角色">
          <el-select v-model="form.role" style="width: 100%">
            <el-option label="管理员" value="admin" />
            <el-option label="普通用户" value="normal" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="editing" label="启用状态">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { resourceGroupApi, userApi } from '../api'
import { auth } from '../store/auth'

const list = ref([])
const plGroups = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const editing = ref(null)
const filter = ref('')
const filterGroupId = ref(null)
const form = reactive(defaultForm())

function defaultForm() {
  return {
    username: '',
    full_name: '',
    emp_no: '',
    group_id: null,
    job_title: '',
    password: '',
    role: 'normal',
    can_login: true,
    is_active: true,
  }
}

const filtered = computed(() => {
  const kw = filter.value.trim().toLowerCase()
  return list.value.filter((u) => {
    if (filterGroupId.value && u.group_id !== filterGroupId.value) return false
    if (!kw) return true
    return (
      (u.username || '').toLowerCase().includes(kw) ||
      (u.full_name || '').toLowerCase().includes(kw) ||
      (u.emp_no || '').toLowerCase().includes(kw)
    )
  })
})

async function load() {
  loading.value = true
  try {
    const [{ data: users }, { data: gs }] = await Promise.all([
      userApi.list(),
      resourceGroupApi.list({ kind: 'pl', include_inactive: false }),
    ])
    list.value = users
    plGroups.value = gs
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  Object.assign(form, defaultForm())
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, {
    username: row.username,
    full_name: row.full_name || '',
    emp_no: row.emp_no || '',
    group_id: row.group_id,
    job_title: row.job_title || '',
    password: '',
    role: row.role || 'normal',
    can_login: row.can_login !== false,
    is_active: row.is_active,
  })
  dialogVisible.value = true
}

async function onSubmit() {
  if (!editing.value && !form.username) {
    ElMessage.warning('登录名必填')
    return
  }
  if (!editing.value && form.can_login && !form.password) {
    ElMessage.warning('允许登录的账号必须设置密码')
    return
  }
  try {
    if (editing.value) {
      const payload = {
        full_name: form.full_name,
        emp_no: form.emp_no,
        group_id: form.group_id,
        job_title: form.job_title,
        role: form.role,
        is_active: form.is_active,
        can_login: form.can_login,
      }
      if (form.password) payload.password = form.password
      await userApi.update(editing.value.id, payload)
      ElMessage.success('已更新')
    } else {
      await userApi.create({
        username: form.username,
        password: form.password,
        full_name: form.full_name,
        emp_no: form.emp_no,
        group_id: form.group_id,
        job_title: form.job_title,
        role: form.role,
        can_login: form.can_login,
      })
      ElMessage.success('已创建')
    }
    dialogVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function onDelete(row) {
  await ElMessageBox.confirm(`确认删除「${row.full_name || row.username}」吗？`, '提示', { type: 'warning' })
  try {
    await userApi.remove(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.muted { color: #c0c4cc; }
.hint { color: #909399; font-size: 12px; margin-left: 8px; }
</style>
