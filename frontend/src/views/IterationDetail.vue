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
            :projects="projects"
            v-model:project-scope="projectScope"
            @vue:mounted="productMounted = true"
          />
        </el-tab-pane>
        <el-tab-pane label="领域需求" name="domain">
          <DomainRequirementTab
            v-if="activeTab === 'domain' || domainMounted"
            :iteration-id="iterationId"
            :version-groups="versionGroups"
            :projects="projects"
            v-model:project-scope="projectScope"
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
import { annualIterationApi, downloadBlob, majorVersionApi, roadmapApi } from '../api'
import { auth } from '../store/auth'
import DomainRequirementTab from '../components/iteration/DomainRequirementTab.vue'
import ProductRequirementTab from '../components/iteration/ProductRequirementTab.vue'

const route = useRoute()
const router = useRouter()
const isAdmin = auth.isAdmin

const iterationId = Number(route.params.id)
const iteration = ref(null)
const versionGroups = ref([])
const projects = ref([])
const activeTab = ref('product')
// 项目标签放在这里而不是各自的 Tab 里：产品/领域两张表共用一个项目选择，
// 来回切标签页时筛选跟着走，否则会以为"切回来筛选自己变了"。
const projectScope = ref('all')
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
    // 需求的计划交付版本填的是**迭代版本**（构建号），分组按「大版本 · 版本」两层，
    // 否则同一个大版本下几十个构建挤在一组里根本挑不出来
    const { data } = await majorVersionApi.allIterationVersions()
    const map = new Map()
    for (const v of data) {
      const head = v.project_name ? `${v.project_name} · ${v.major_version_no}` : v.major_version_no
      const groupLabel = v.release_version_no ? `${head} · ${v.release_version_no}` : head
      if (!map.has(groupLabel)) map.set(groupLabel, [])
      map.get(groupLabel).push(v)
    }
    versionGroups.value = Array.from(map.entries()).map(([label, options]) => ({ label, options }))
  } catch (e) {
    /* 下拉为空不阻塞 */
  }
}

async function loadProjects() {
  // 迭代本身跨项目，项目挂在需求行上，两个 tab 共用这一份下拉。
  try {
    const { data } = await roadmapApi.listProjects()
    projects.value = data.map((p) => ({ id: p.id, name: p.name }))
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
  loadProjects()
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
