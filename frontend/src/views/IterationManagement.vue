<template>
  <div>
    <el-card shadow="never">
      <div class="toolbar">
        <span>年度：</span>
        <el-select v-model="year" style="width: 140px" @change="load">
          <el-option v-for="y in years" :key="y" :label="`${y} 年`" :value="y" />
        </el-select>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
        <span class="tip">每年 12 个迭代（每月一个），点击「迭代名称」进入需求子页面</span>
      </div>

      <el-table :data="list" v-loading="loading" border stripe style="width: 100%">
        <el-table-column label="月份" width="80" align="center">
          <template #default="{ row }">{{ row.month }} 月</template>
        </el-table-column>
        <el-table-column label="迭代名称" min-width="240">
          <template #default="{ row }">
            <el-link type="primary" @click="goDetail(row)">{{ row.name || `${row.year}年${row.month}月迭代` }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="负责人" width="160">
          <template #default="{ row }">
            <template v-if="isAdmin">
              <el-input
                v-if="isEditing(row, 'owner')"
                v-model="row.owner"
                size="small"
                autofocus
                @blur="commit(row, 'owner')"
                @keyup.enter="commit(row, 'owner')"
                @keyup.esc="cancel(row, 'owner')"
              />
              <div v-else class="editable-cell" @dblclick="startEdit(row, 'owner')">
                {{ row.owner || '—' }}
              </div>
            </template>
            <span v-else>{{ row.owner || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="140">
          <template #default="{ row }">
            <el-select
              v-if="isAdmin"
              :model-value="row.status"
              size="small"
              @change="(v) => onStatusChange(row, v)"
            >
              <el-option v-for="s in STATUS_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
            </el-select>
            <el-tag v-else :type="statusTag(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="迭代目标" min-width="280">
          <template #default="{ row }">
            <template v-if="isAdmin">
              <el-input
                v-if="isEditing(row, 'goal')"
                v-model="row.goal"
                size="small"
                autofocus
                type="textarea"
                :rows="2"
                @blur="commit(row, 'goal')"
                @keyup.esc="cancel(row, 'goal')"
              />
              <div v-else class="editable-cell" @dblclick="startEdit(row, 'goal')">
                {{ row.goal || '—' }}
              </div>
            </template>
            <span v-else>{{ row.goal || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="goDetail(row)">进入</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { annualIterationApi } from '../api'
import { auth } from '../store/auth'

const router = useRouter()
const isAdmin = auth.isAdmin

const STATUS_OPTIONS = [
  { value: 'planning', label: '规划中' },
  { value: 'in_progress', label: '进行中' },
  { value: 'done', label: '已完成' },
]
const STATUS_LABEL = Object.fromEntries(STATUS_OPTIONS.map(s => [s.value, s.label]))
const STATUS_TAG = { planning: 'info', in_progress: 'warning', done: 'success' }

const years = ref([new Date().getFullYear()])
const year = ref(new Date().getFullYear())
const list = ref([])
const loading = ref(false)
const editingCell = ref(null)

async function loadYears() {
  try {
    const { data } = await annualIterationApi.years()
    if (data.length) {
      years.value = data
      if (!data.includes(year.value)) year.value = data[0]
    }
  } catch (e) {
    /* 不阻塞 */
  }
}

async function load() {
  loading.value = true
  try {
    const { data } = await annualIterationApi.list(year.value)
    list.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

function goDetail(row) {
  router.push({ path: `/iterations/${row.id}` })
}

function statusLabel(s) { return STATUS_LABEL[s] || s }
function statusTag(s) { return STATUS_TAG[s] || '' }

// ===== 行内编辑（admin only） =====
function isEditing(row, field) {
  return editingCell.value && editingCell.value.id === row.id && editingCell.value.field === field
}

function startEdit(row, field) {
  if (!isAdmin.value) return
  editingCell.value = { id: row.id, field, original: row[field] }
}

function cancel(row, field) {
  if (!editingCell.value) return
  row[field] = editingCell.value.original
  editingCell.value = null
}

async function commit(row, field) {
  if (!editingCell.value) return
  const original = editingCell.value.original
  const newVal = row[field]
  editingCell.value = null
  if (newVal === original) return
  try {
    await annualIterationApi.update(row.id, { [field]: newVal })
    ElMessage.success('已保存')
  } catch (e) {
    row[field] = original
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function onStatusChange(row, value) {
  const original = row.status
  if (value === original) return
  try {
    await annualIterationApi.update(row.id, { status: value })
    row.status = value
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

onMounted(async () => {
  await loadYears()
  load()
})
</script>

<style scoped>
.toolbar {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.tip {
  margin-left: auto;
  color: #909399;
  font-size: 12px;
}
.editable-cell {
  cursor: text;
  min-height: 22px;
  white-space: pre-wrap;
}
</style>
