<template>
  <div>
    <el-page-header @back="goBack">
      <template #content>
        <span v-if="iteration">
          {{ iteration.year }}年{{ iteration.month }}月迭代 · {{ iteration.name || '未命名' }}
        </span>
        <span v-else>加载中…</span>
      </template>
      <template #extra>
        <el-button v-if="isAdmin" :icon="Download" type="success" @click="onExport">导出 PPT</el-button>
      </template>
    </el-page-header>

    <el-card shadow="never" class="card">
      <el-tabs v-model="activeTab" class="req-tabs">
        <el-tab-pane label="产品需求" name="product">
          <ProductRequirementTab
            v-if="activeTab === 'product' || productMounted"
            :iteration-id="iterationId"
            :version-groups="versionGroups"
            @vue:mounted="productMounted = true"
          />
        </el-tab-pane>
        <el-tab-pane label="领域需求" name="domain">
          <DomainRequirementTab
            v-if="activeTab === 'domain' || domainMounted"
            :iteration-id="iterationId"
            :version-groups="versionGroups"
            @vue:mounted="domainMounted = true"
          />
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { annualIterationApi, downloadBlob, majorVersionApi } from '../api'
import { auth } from '../store/auth'
import DomainRequirementTab from '../components/iteration/DomainRequirementTab.vue'
import ProductRequirementTab from '../components/iteration/ProductRequirementTab.vue'

const route = useRoute()
const router = useRouter()
const isAdmin = auth.isAdmin

const iterationId = Number(route.params.id)
const iteration = ref(null)
const versionGroups = ref([])
const activeTab = ref('product')
const productMounted = ref(false)
const domainMounted = ref(false)

async function loadIteration() {
  try {
    const { data } = await annualIterationApi.get(iterationId)
    iteration.value = data
  } catch (e) {
    ElMessage.error('迭代不存在')
    router.push('/iterations')
  }
}

async function loadVersionGroups() {
  try {
    const { data } = await majorVersionApi.allIterationVersions()
    const map = new Map()
    for (const v of data) {
      const groupLabel = v.project_name
        ? `${v.project_name} · ${v.major_version_no}`
        : v.major_version_no
      if (!map.has(groupLabel)) map.set(groupLabel, [])
      map.get(groupLabel).push(v)
    }
    versionGroups.value = Array.from(map.entries()).map(([label, options]) => ({ label, options }))
  } catch (e) {
    /* 下拉为空不阻塞 */
  }
}

function goBack() {
  router.push('/iterations')
}

async function onExport() {
  try {
    const resp = await annualIterationApi.exportPptx(iterationId)
    const tag = iteration.value ? `${iteration.value.year}-${String(iteration.value.month).padStart(2, '0')}` : iterationId
    downloadBlob(resp.data, `iteration-${tag}.pptx`)
    ElMessage.success('已导出')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导出失败')
  }
}

onMounted(() => {
  loadIteration()
  loadVersionGroups()
})
</script>

<style scoped>
.card {
  margin-top: 12px;
}
.req-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}
</style>
