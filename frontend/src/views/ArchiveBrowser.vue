<template>
  <div class="arch-page">
    <div class="arch-head">
      <span class="arch-note">
        每周一早上自动给每个专项 / 领域 / 客户面 / 硬件清零各存一份整页存档；
        也可以在对应页面上点「存一份档」随时存。
        <b>图片是按文件名现取的</b>，图被换掉的话存档里也跟着变。
      </span>
    </div>

    <el-tabs v-model="kind" @tab-change="onKindChange">
      <el-tab-pane v-for="k in kinds" :key="k.kind" :label="k.label" :name="k.kind" />
    </el-tabs>

    <div class="arch-body">
      <div class="arch-col arch-targets">
        <el-input v-model="keyword" size="small" placeholder="搜索" clearable />
        <el-scrollbar class="arch-scroll">
          <div
            v-for="t in filteredTargets"
            :key="t.ref_id"
            class="arch-row"
            :class="{ active: t.ref_id === refId }"
            @click="selectTarget(t.ref_id)"
          >
            <span class="arch-row-title">{{ t.title || `#${t.ref_id}` }}</span>
            <span class="arch-row-meta">{{ t.count }} 份 · {{ t.latest }}</span>
          </div>
          <el-empty v-if="!filteredTargets.length" description="还没有存档" :image-size="60" />
        </el-scrollbar>
      </div>

      <div class="arch-col arch-dates">
        <el-scrollbar class="arch-scroll">
          <div
            v-for="s in snapshots"
            :key="s.id"
            class="arch-row"
            :class="{ active: s.id === currentId }"
            @click="openSnapshot(s.id)"
          >
            <span class="arch-row-title">{{ s.label }}</span>
            <el-tag size="small" :type="s.reason === 'weekly' ? 'info' : 'success'"
                    disable-transitions>
              {{ s.reason === 'weekly' ? '每周' : '手工' }}
            </el-tag>
          </div>
          <el-empty v-if="refId != null && !snapshots.length" description="这个对象还没有存档"
                    :image-size="60" />
        </el-scrollbar>
      </div>

      <div class="arch-col arch-view">
        <div class="arch-toolbar">
          <span class="arch-cur">{{ currentLabel }}</span>
          <el-button v-if="currentId" size="small" @click="downloadHtml">另存为 HTML</el-button>
          <el-button v-if="currentId && isAdmin" size="small" type="danger" plain
                     @click="removeCurrent">删除这份档</el-button>
        </div>
        <!-- sandbox 留空＝不给脚本、不给表单：存档正文里本来就只该有文字、表格和图 -->
        <iframe v-if="html" class="arch-frame" sandbox :srcdoc="html" />
        <el-empty v-else description="选一份存档看看" :image-size="80" />
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 历史存档浏览：按「类型 → 对象 → 存档日」翻回去看那一天整页长什么样。
 *
 * 三列都不重算口径——类型、对象清单、渲染都由服务端给：
 * 类型中文名来自 /archives/kinds，对象清单是从存档表自己聚合出来的
 * （对象被删了它的存档还在，这正是要能翻的情况），HTML 由服务端渲染，
 * 专项走的就是周报那一份，前端再写一套必然分叉。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { apiError, archiveApi, downloadBlob } from '../api'
import { auth } from '../store/auth'

const kinds = ref([])
const kind = ref('special')
const targets = ref([])
const snapshots = ref([])
const refId = ref(null)
const currentId = ref(null)
const html = ref('')
const keyword = ref('')

const isAdmin = auth.isAdmin

const filteredTargets = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return targets.value
  return targets.value.filter((t) => (t.title || '').toLowerCase().includes(kw))
})

const currentLabel = computed(() => {
  const s = snapshots.value.find((x) => x.id === currentId.value)
  if (!s) return ''
  return `${s.title || ''} · ${s.label}${s.created_by ? ` · ${s.created_by}` : ''}`
})

async function loadKinds() {
  try {
    const { data } = await archiveApi.kinds()
    kinds.value = data
    if (data.length && !data.some((k) => k.kind === kind.value)) kind.value = data[0].kind
  } catch (e) {
    ElMessage.error(apiError(e, '加载存档类型失败'))
  }
}

async function loadTargets() {
  refId.value = null
  snapshots.value = []
  currentId.value = null
  html.value = ''
  try {
    const { data } = await archiveApi.targets(kind.value)
    targets.value = data
    if (data.length) await selectTarget(data[0].ref_id)
  } catch (e) {
    ElMessage.error(apiError(e, '加载存档清单失败'))
  }
}

async function selectTarget(id) {
  refId.value = id
  currentId.value = null
  html.value = ''
  try {
    const { data } = await archiveApi.list({ kind: kind.value, ref_id: id })
    snapshots.value = data
    if (data.length) await openSnapshot(data[0].id)
  } catch (e) {
    ElMessage.error(apiError(e, '加载存档列表失败'))
  }
}

async function openSnapshot(id) {
  currentId.value = id
  html.value = ''
  try {
    const { data } = await archiveApi.view(id)
    html.value = data
  } catch (e) {
    ElMessage.error(apiError(e, '打开存档失败'))
  }
}

function downloadHtml() {
  const s = snapshots.value.find((x) => x.id === currentId.value)
  const name = `${s?.title || '存档'}_${s?.label || ''}.html`
  downloadBlob(new Blob([html.value], { type: 'text/html;charset=utf-8' }), name)
}

async function removeCurrent() {
  const s = snapshots.value.find((x) => x.id === currentId.value)
  try {
    await ElMessageBox.confirm(
      `删除「${s?.title || ''} · ${s?.label || ''}」这份存档？删掉之后这一天的样子就找不回来了。`,
      '确认删除', { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await archiveApi.remove(currentId.value)
    ElMessage.success('已删除')
    await selectTarget(refId.value)
  } catch (e) {
    ElMessage.error(apiError(e, '删除失败'))
  }
}

function onKindChange() {
  keyword.value = ''
  loadTargets()
}

onMounted(async () => {
  await loadKinds()
  await loadTargets()
})
</script>

<style scoped>
.arch-page {
  padding: 12px 16px;
}
.arch-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}
.arch-note {
  color: #909399;
  font-size: 12px;
}
.arch-body {
  display: grid;
  grid-template-columns: 240px 160px 1fr;
  gap: 10px;
  height: calc(100vh - 190px);
  min-height: 380px;
}
.arch-col {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.arch-scroll {
  flex: 1;
  margin-top: 6px;
}
.arch-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 13px;
}
.arch-row:hover {
  background: #f5f7fa;
}
.arch-row.active {
  background: #ecf5ff;
  color: #409eff;
}
.arch-row-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.arch-row-meta {
  color: #909399;
  font-size: 12px;
}
.arch-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid #ebeef5;
}
.arch-cur {
  flex: 1;
  font-size: 13px;
  color: #606266;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.arch-frame {
  flex: 1;
  width: 100%;
  border: 0;
  margin-top: 6px;
}
</style>
