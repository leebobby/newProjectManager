<template>
  <el-dialog
    :model-value="modelValue"
    :title="`合入需求 · ${versionNo || ''}${versionTitle ? ' ' + versionTitle : ''}`"
    width="1000px"
    top="6vh"
    @update:model-value="(v) => emit('update:modelValue', v)"
    @opened="load"
  >
    <el-tabs v-model="activeTab">
      <!-- 产品需求 -->
      <el-tab-pane :label="`产品需求 (${products.length})`" name="product">
        <el-table :data="products" v-loading="loading" border stripe size="small" max-height="460" style="width: 100%">
          <el-table-column prop="seq" label="序号" width="60" align="center" />
          <el-table-column label="需求编号" width="150" show-overflow-tooltip>
            <template #default="{ row }">
              <el-link v-if="row.req_url" :href="row.req_url" type="primary" target="_blank">
                {{ row.req_no || '（链接）' }}
              </el-link>
              <span v-else>{{ row.req_no || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="title" label="需求标题" min-width="220" show-overflow-tooltip />
          <el-table-column prop="priority" label="优先级" width="80" align="center" />
          <el-table-column prop="feature" label="所属特性" width="120" show-overflow-tooltip />
          <el-table-column label="测试结论" width="100" align="center">
            <template #default="{ row }">
              <span :style="statusStyle(row.progress_test_result)">{{ row.progress_test_result || '—' }}</span>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!loading && !products.length" description="该版本暂无关联产品需求" :image-size="80" />
      </el-tab-pane>

      <!-- 领域需求 -->
      <el-tab-pane :label="`领域需求 (${domains.length})`" name="domain">
        <el-table :data="domains" v-loading="loading" border stripe size="small" max-height="460" style="width: 100%">
          <el-table-column prop="seq" label="序号" width="60" align="center" />
          <el-table-column label="需求编号" width="150" show-overflow-tooltip>
            <template #default="{ row }">
              <el-link v-if="row.req_url" :href="row.req_url" type="primary" target="_blank">
                {{ row.req_no || '（链接）' }}
              </el-link>
              <span v-else>{{ row.req_no || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="title" label="需求标题" min-width="220" show-overflow-tooltip />
          <el-table-column prop="owner" label="责任人" width="100" show-overflow-tooltip />
          <el-table-column prop="owner_group" label="PL组" width="120" show-overflow-tooltip />
          <el-table-column prop="priority" label="优先级" width="80" align="center" />
          <el-table-column label="转测澄清" width="100" align="center">
            <template #default="{ row }">
              <span :style="statusStyle(row.progress_clarify)">{{ row.progress_clarify || '—' }}</span>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!loading && !domains.length" description="该版本暂无关联领域需求" :image-size="80" />
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { iterationRequirementApi, productRequirementApi } from '../api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  versionId: { type: Number, default: null },
  versionNo: { type: String, default: '' },
  versionTitle: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const activeTab = ref('product')
const loading = ref(false)
const products = ref([])
const domains = ref([])

// 进展着色：与迭代页一致——已完成→绿、已延期→红
function statusStyle(v) {
  if (v === '已完成') return { color: '#529b2e', fontWeight: 600 }
  if (v === '已延期') return { color: '#c45656', fontWeight: 600 }
  return {}
}

async function load() {
  if (!props.versionId) {
    products.value = []
    domains.value = []
    return
  }
  loading.value = true
  try {
    const [p, d] = await Promise.all([
      productRequirementApi.byVersion(props.versionId),
      iterationRequirementApi.byVersion(props.versionId),
    ])
    products.value = p.data
    domains.value = d.data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载合入需求失败')
  } finally {
    loading.value = false
  }
}

// 切换版本时若对话框已开着，重新加载
watch(() => props.versionId, () => { if (props.modelValue) load() })
</script>
