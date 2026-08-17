<template>
  <div>
    <el-card shadow="never">
      <div class="toolbar">
        <el-input
          v-model="filters.username"
          placeholder="用户"
          clearable
          style="width: 140px"
          @change="reload(1)"
        />
        <el-select
          v-model="filters.action"
          placeholder="操作"
          clearable
          style="width: 140px"
          @change="reload(1)"
        >
          <el-option v-for="o in options.actions" :key="o" :label="o" :value="o" />
        </el-select>
        <el-select
          v-model="filters.target"
          placeholder="对象"
          clearable
          style="width: 160px"
          @change="reload(1)"
        >
          <el-option v-for="o in options.targets" :key="o" :label="o" :value="o" />
        </el-select>
        <el-input
          v-model="filters.keyword"
          placeholder="关键字（详情/对象编号）"
          clearable
          style="width: 220px"
          @change="reload(1)"
        />
        <el-date-picker
          v-model="filters.range"
          type="datetimerange"
          range-separator="-"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          value-format="YYYY-MM-DDTHH:mm:ss"
          style="width: 360px"
          @change="reload(1)"
        />
        <el-button :icon="Refresh" @click="reload()">刷新</el-button>
        <el-button @click="onReset">重置</el-button>
        <span class="total">共 {{ total }} 条</span>
      </div>

      <el-table :data="rows" v-loading="loading" border stripe size="small" style="width: 100%">
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="username" label="用户" width="120" />
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <el-tag :type="actionTagType(row.action)" size="small" effect="plain">
              {{ row.action }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="target" label="对象" width="130" />
        <el-table-column prop="target_id" label="对象编号" width="100" />
        <el-table-column prop="detail" label="详情" min-width="280" show-overflow-tooltip />
        <el-table-column prop="ip" label="IP" width="130" />
        <el-table-column prop="user_agent" label="UA" min-width="180" show-overflow-tooltip />
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100, 200]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="reload()"
          @size-change="reload(1)"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { opLogApi } from '../api'

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)

const filters = reactive({
  username: '',
  action: '',
  target: '',
  keyword: '',
  range: null,
})

const options = ref({ actions: [], targets: [], usernames: [] })

async function loadOptions() {
  try {
    const { data } = await opLogApi.options()
    options.value = data
  } catch {
    // 静默
  }
}

async function reload(toPage) {
  if (toPage) page.value = toPage
  loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
    }
    if (filters.username) params.username = filters.username
    if (filters.action) params.action = filters.action
    if (filters.target) params.target = filters.target
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.range && filters.range.length === 2) {
      params.date_from = filters.range[0]
      params.date_to = filters.range[1]
    }
    const { data } = await opLogApi.list(params)
    rows.value = data.items
    total.value = data.total
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

function onReset() {
  filters.username = ''
  filters.action = ''
  filters.target = ''
  filters.keyword = ''
  filters.range = null
  reload(1)
}

function formatTime(d) {
  if (!d) return ''
  return new Date(d).toLocaleString()
}

function actionTagType(action) {
  if (!action) return 'info'
  if (action.includes('失败')) return 'danger'
  if (action === '登录' || action === '登出') return 'success'
  if (action === '新增') return 'success'
  if (action === '删除') return 'danger'
  if (action === '修改' || action.startsWith('修改')) return 'warning'
  if (action === '导出PPT' || action === '导入' || action === '运行脚本') return 'info'
  return 'info'
}

onMounted(() => {
  loadOptions()
  reload(1)
})
</script>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}
.toolbar .total {
  margin-left: auto;
  color: #909399;
  font-size: 13px;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
