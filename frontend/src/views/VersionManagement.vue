<template>
  <div>
    <!-- Project tabs -->
    <el-tabs v-model="activeTab" @tab-change="onTabChange" class="project-tabs">
      <el-tab-pane
        v-for="proj in projects"
        :key="proj.id"
        :label="proj.name"
        :name="String(proj.id)"
      />
      <el-tab-pane label="现场调试版本" name="debug" />
    </el-tabs>

    <DebugVersionPanel v-if="activeTab === 'debug'" />

    <template v-else>
    <VersionTimeline v-if="majorVersions.length" :majors="majorVersions" />

    <el-card shadow="never">
      <div class="toolbar">
        <el-button v-if="isAdmin" type="primary" :icon="Plus" @click="openCreateMajor">新增大版本</el-button>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
        <span class="tip">
          大版本（C10SPC100）→ 版本（C10SPC101）→ 迭代版本（C10SPC101B001）
          ｜大版本按「开始时间」倒序，最新的在最上面，没填开始时间的排在最后
          <template v-if="isAdmin">｜版本与迭代版本可以用 ↑↓ 排成你要的顺序；放错父级的用「编辑」改所属</template>
        </span>
      </div>

      <el-table
        :data="majorVersions"
        v-loading="loading"
        row-key="id"
        border
        stripe
        style="width: 100%"
      >
        <!-- ── 展开：版本 ───────────────────────────────────────────── -->
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="expand-area">
              <div class="expand-header">
                <span class="expand-title">版本（共 {{ row.release_versions?.length || 0 }} 个）</span>
                <el-button
                  v-if="isAdmin"
                  size="small"
                  type="primary"
                  :icon="Plus"
                  @click.stop="openCreateRelease(row)"
                >
                  新增版本
                </el-button>
              </div>
              <el-table
                :data="row.release_versions || []"
                row-key="id"
                border
                size="small"
                style="width: 100%"
              >
                <!-- ── 展开：迭代版本 ───────────────────────────────── -->
                <el-table-column type="expand">
                  <template #default="{ row: rv }">
                    <div class="expand-area expand-area-inner">
                      <div class="expand-header">
                        <span class="expand-title">迭代版本（共 {{ rv.iteration_versions?.length || 0 }} 个）</span>
                        <el-button
                          v-if="isAdmin"
                          size="small"
                          type="primary"
                          :icon="Plus"
                          @click.stop="openCreateIter(rv)"
                        >
                          新增迭代版本
                        </el-button>
                      </div>
                      <el-table
                        :data="rv.iteration_versions || []"
                        border
                        size="small"
                        style="width: 100%"
                      >
                        <el-table-column prop="version_no" label="版本号" width="170" />
                        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
                        <el-table-column prop="planned_date" label="预计发布日期" width="130">
                          <template #default="{ row: ir }">{{ fmtDate(ir.planned_date) }}</template>
                        </el-table-column>
                        <el-table-column prop="actual_release_date" label="实际发布" width="120">
                          <template #default="{ row: ir }">
                            <el-tag v-if="ir.actual_release_date" type="success" size="small">
                              {{ fmtDate(ir.actual_release_date) }}
                            </el-tag>
                            <span v-else class="muted">未发布</span>
                          </template>
                        </el-table-column>
                        <el-table-column label="合入需求" width="100" align="center">
                          <template #default="{ row: ir }">
                            <el-button link type="primary" size="small" @click.stop="openMerge(ir)">查看</el-button>
                          </template>
                        </el-table-column>
                        <el-table-column v-if="isAdmin" label="操作" width="200" fixed="right">
                          <template #default="{ row: ir, $index: i }">
                            <el-button size="small" title="上移" :icon="Top" :disabled="i === 0"
                              @click.stop="moveIter(rv, i, -1)" />
                            <el-button size="small" title="下移" :icon="Bottom"
                              :disabled="i === (rv.iteration_versions?.length || 0) - 1"
                              @click.stop="moveIter(rv, i, 1)" />
                            <el-button size="small" @click.stop="openEditIter(ir, rv)">编辑</el-button>
                            <el-button size="small" type="danger" @click.stop="onDeleteIter(ir)">删除</el-button>
                          </template>
                        </el-table-column>
                      </el-table>
                    </div>
                  </template>
                </el-table-column>

                <el-table-column prop="version_no" label="版本号" width="140" />
                <el-table-column prop="title" label="标题" min-width="160" show-overflow-tooltip />
                <el-table-column prop="description" label="版本说明" min-width="180" show-overflow-tooltip />
                <el-table-column prop="planned_date" label="计划发布" width="120">
                  <template #default="{ row: rv }">{{ fmtDate(rv.planned_date) || '—' }}</template>
                </el-table-column>
                <el-table-column prop="actual_release_date" label="实际发布" width="120">
                  <template #default="{ row: rv }">
                    <el-tag v-if="rv.actual_release_date" type="success" size="small">
                      {{ fmtDate(rv.actual_release_date) }}
                    </el-tag>
                    <span v-else style="color:#c0c4cc">待发布</span>
                  </template>
                </el-table-column>
                <el-table-column label="迭代数" width="70" align="center">
                  <template #default="{ row: rv }">
                    <el-tag type="info" size="small">{{ rv.iteration_versions?.length || 0 }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column v-if="isAdmin" label="操作" width="210" fixed="right">
                  <template #default="{ row: rv, $index: i }">
                    <el-button size="small" title="上移" :icon="Top" :disabled="i === 0"
                      @click.stop="moveRelease(row, i, -1)" />
                    <el-button size="small" title="下移" :icon="Bottom"
                      :disabled="i === (row.release_versions?.length || 0) - 1"
                      @click.stop="moveRelease(row, i, 1)" />
                    <el-button size="small" @click.stop="openEditRelease(rv, row)">编辑</el-button>
                    <el-button size="small" type="danger" @click.stop="onDeleteRelease(rv)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="version_no" label="大版本号" width="130" />
        <el-table-column label="代码线" width="180">
          <template #default="{ row }">
            <el-tag v-if="row.line === 'master'" type="success" size="small" effect="dark">主干</el-tag>
            <template v-else>
              <el-tag type="info" size="small">分支</el-tag>
              <span class="branch-meta">
                {{ row.branch_name || '—' }}
                <template v-if="row.branched_at">（{{ fmtDate(row.branched_at) }} 起）</template>
              </span>
            </template>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="140" />
        <el-table-column prop="description" label="版本说明" min-width="160" show-overflow-tooltip />
        <el-table-column label="版本范围（按开始时间倒序）" width="210">
          <template #default="{ row }">
            <span v-if="row.range_start || row.range_end">
              {{ fmtDate(row.range_start) }} ~ {{ fmtDate(row.range_end) }}
            </span>
            <span v-else style="color:#c0c4cc">—</span>
          </template>
        </el-table-column>
        <!-- 两个数都摆在收起态的行上：只显示「版本数」时，一眼分不清是「没展开」
             还是「下面真的空了」——迁移出问题时正是后者，得能立刻看出来 -->
        <el-table-column label="下辖" width="140" align="center">
          <template #default="{ row }">
            <el-tag type="info" size="small">{{ row.release_versions?.length || 0 }} 版本</el-tag>
            <el-tag type="info" size="small" effect="plain" style="margin-left:4px">
              {{ buildCount(row) }} 构建
            </el-tag>
          </template>
        </el-table-column>
        <!-- 大版本没有 ↑↓：这一层的顺序由「版本范围开始」决定（倒序），不手排 -->
        <el-table-column v-if="isAdmin" label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEditMajor(row)">编辑</el-button>
            <el-button
              v-if="row.line !== 'master'"
              size="small"
              type="warning"
              @click="onSetMaster(row)"
            >设为主干</el-button>
            <el-button size="small" type="danger" @click="onDeleteMajor(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    </template>

    <!-- 大版本 -->
    <el-dialog
      v-model="majorDialogVisible"
      :title="editingMajor ? '编辑大版本' : '新增大版本'"
      width="600px"
      @closed="editingMajor = null"
    >
      <el-form :model="majorForm" label-width="110px">
        <el-form-item label="大版本号" required>
          <el-input v-model="majorForm.version_no" placeholder="例如 C10SPC100" />
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="majorForm.title" placeholder="例如 春季正式版" />
        </el-form-item>
        <el-form-item label="版本说明">
          <el-input v-model="majorForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="版本范围开始">
          <el-date-picker v-model="majorForm.range_start" type="date"
            value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
        </el-form-item>
        <el-form-item label="版本范围结束">
          <el-date-picker v-model="majorForm.range_end" type="date"
            value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
        </el-form-item>
        <el-form-item label="分支名">
          <el-input v-model="majorForm.branch_name" placeholder="例如 release/C10SPC100；在主干上则留空" />
          <div class="form-tip">主干/分支状态用列表里的「设为主干」切换——同一项目只会有一个主干。</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="majorDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSubmitMajor">保存</el-button>
      </template>
    </el-dialog>

    <!-- 版本 -->
    <el-dialog
      v-model="releaseDialogVisible"
      :title="editingRelease ? '编辑版本' : '新增版本'"
      width="560px"
      @closed="editingRelease = null"
    >
      <el-form :model="releaseForm" label-width="110px">
        <el-form-item label="所属大版本" required>
          <el-select v-model="releaseForm.major_version_id" filterable style="width: 100%">
            <el-option v-for="m in majorVersions" :key="m.id" :value="m.id"
              :label="m.title ? `${m.version_no} · ${m.title}` : m.version_no" />
          </el-select>
          <div v-if="editingRelease" class="form-tip">
            改这里就是把这个版本整个挪到别的大版本下，它名下的迭代版本会跟着走，排在末尾。
          </div>
        </el-form-item>
        <el-form-item label="版本号" required>
          <el-input v-model="releaseForm.version_no" placeholder="例如 C10SPC101" />
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="releaseForm.title" />
        </el-form-item>
        <el-form-item label="版本说明">
          <el-input v-model="releaseForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="计划发布">
          <el-date-picker v-model="releaseForm.planned_date" type="date"
            value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
        </el-form-item>
        <el-form-item label="实际发布">
          <el-date-picker v-model="releaseForm.actual_release_date" type="date"
            value-format="YYYY-MM-DDTHH:mm:ss" placeholder="发布后填写" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="releaseDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSubmitRelease">保存</el-button>
      </template>
    </el-dialog>

    <!-- 合入需求查看对话框 -->
    <VersionMergeDialog
      v-model="mergeVisible"
      :version-id="mergeVersion.id"
      :version-no="mergeVersion.version_no"
      :version-title="mergeVersion.title"
    />

    <!-- 迭代版本 -->
    <el-dialog
      v-model="iterDialogVisible"
      :title="editingIter ? '编辑迭代版本' : '新增迭代版本'"
      width="520px"
      @closed="editingIter = null"
    >
      <el-form :model="iterForm" label-width="110px">
        <el-form-item label="所属版本" required>
          <el-select v-model="iterForm.release_version_id" filterable style="width: 100%">
            <el-option-group v-for="g in releaseOptions" :key="g.majorId" :label="g.majorLabel">
              <el-option v-for="rv in g.items" :key="rv.id" :value="rv.id"
                :label="rv.title ? `${rv.version_no} · ${rv.title}` : rv.version_no" />
            </el-option-group>
          </el-select>
          <div v-if="editingIter" class="form-tip">
            改这里就是把这个迭代版本挪到别的版本下，会排在目标版本的末尾。
          </div>
        </el-form-item>
        <el-form-item label="版本号" required>
          <el-input v-model="iterForm.version_no" placeholder="例如 C10SPC101B001" />
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="iterForm.title" placeholder="例如 第1迭代" />
        </el-form-item>
        <el-form-item label="预计发布日期">
          <el-date-picker v-model="iterForm.planned_date" type="date"
            value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
        </el-form-item>
        <el-form-item label="实际发布日期">
          <el-date-picker v-model="iterForm.actual_release_date" type="date"
            value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
          <div class="form-tip">
            填了并且这天过了之后，迭代管理的「计划交付版本」下拉里就不再列这个构建了。
            所属版本一旦发布，它名下的构建也一并收起来。
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="iterDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSubmitIter">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Bottom, Plus, Refresh, Top } from '@element-plus/icons-vue'
import { majorVersionApi, roadmapApi } from '../api'
import { fmtDate, naturalCompare } from '../utils/format'
import { auth } from '../store/auth'
import VersionTimeline from '../components/VersionTimeline.vue'
import DebugVersionPanel from '../components/DebugVersionPanel.vue'
import VersionMergeDialog from '../components/VersionMergeDialog.vue'

const isAdmin = auth.isAdmin

const projects = ref([])
const activeTab = ref('debug')   // 默认若无项目则停留在「现场调试版本」
const majorVersions = ref([])
const loading = ref(false)

// 合入需求查看对话框（按迭代版本看其关联的产品/领域需求）
const mergeVisible = ref(false)
const mergeVersion = ref({ id: null, version_no: '', title: '' })
function openMerge(ir) {
  mergeVersion.value = { id: ir.id, version_no: ir.version_no, title: ir.title }
  mergeVisible.value = true
}

const majorDialogVisible = ref(false)
const editingMajor = ref(null)
const majorForm = reactive(defaultMajorForm())

const releaseDialogVisible = ref(false)
const editingRelease = ref(null)
const currentMajor = ref(null)
const releaseForm = reactive(defaultReleaseForm())

const iterDialogVisible = ref(false)
const editingIter = ref(null)
const currentRelease = ref(null)
const iterForm = reactive(defaultIterForm())

// 大版本下所有构建的条数（跨它名下的全部版本）
function buildCount(major) {
  return (major.release_versions || []).reduce(
    (n, rv) => n + (rv.iteration_versions?.length || 0), 0)
}

// 「所属版本」下拉：当前项目下所有版本，按大版本分组，便于把放错地方的迭代版本挪走
const releaseOptions = computed(() => majorVersions.value.map((m) => ({
  majorId: m.id,
  majorLabel: m.title ? `${m.version_no} · ${m.title}` : m.version_no,
  items: m.release_versions || [],
})).filter((g) => g.items.length))

// ── 手工排序 ────────────────────────────────────────────────────────────────
// 整体提交新顺序而不是逐个改 sort_order：后者中途失败就留下一个「排到一半」的顺序，
// 而顺序错了不会报错，只是看着不对，没人会当 bug 报
function movedIds(list, index, delta) {
  const ids = (list || []).map((x) => x.id)
  const to = index + delta
  if (index < 0 || to < 0 || to >= ids.length) return null
  ids.splice(to, 0, ids.splice(index, 1)[0])
  return ids
}

async function applyOrder(fn, parentId, ids) {
  if (!ids) return
  try {
    await fn(parentId, ids)
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '排序保存失败')
    await load()          // 失败也重载：别让页面停在一个没落库的顺序上
  }
}

// 大版本没有 moveMajor：那一层的顺序来自 range_start（服务端倒序），不是手排的
function moveRelease(major, index, delta) {
  applyOrder(majorVersionApi.reorderReleases, major.id,
             movedIds(major.release_versions, index, delta))
}
function moveIter(release, index, delta) {
  applyOrder(majorVersionApi.reorderIterVersions, release.id,
             movedIds(release.iteration_versions, index, delta))
}

function defaultMajorForm() {
  return { version_no: '', title: '', description: '', range_start: null, range_end: null, branch_name: '' }
}
// sort_order 也放进默认值：漏了它，新建时塞进来的那个值会残留到下一次「编辑」，
// 把别人排好的顺序悄悄改掉
function defaultReleaseForm() {
  return { version_no: '', title: '', description: '', planned_date: null,
           actual_release_date: null, sort_order: 0, major_version_id: null }
}
function defaultIterForm() {
  return { version_no: '', title: '', planned_date: null, actual_release_date: null,
           sort_order: 0, release_version_id: null }
}

// ── 版本号建议 ────────────────────────────────────────────────────────────
// 尾部数字 +1、位宽不变：C10SPC100 → C10SPC101，C10SPC101B001 → C10SPC101B002。
// 只是个默认值，输入框仍可改——号段规则各项目未必一致，别在这里硬校验。
function bumpTail(s) {
  const m = /^(.*?)(\d+)$/.exec(s || '')
  if (!m) return s || ''
  return m[1] + String(Number(m[2]) + 1).padStart(m[2].length, '0')
}
function maxNo(list) {
  const nos = (list || []).map(v => v.version_no).filter(Boolean)
  if (!nos.length) return ''
  return nos.slice().sort(naturalCompare)[nos.length - 1]
}
function suggestReleaseNo(major) {
  // 已有版本就接着往下排；一个都没有时从大版本号本身 +1（C10SPC100 → C10SPC101）
  return bumpTail(maxNo(major.release_versions) || major.version_no || '')
}
function suggestIterNo(release) {
  const top = maxNo(release.iteration_versions)
  return top ? bumpTail(top) : `${release.version_no || ''}B001`
}

async function loadProjects() {
  try {
    const { data } = await roadmapApi.listProjects(true)
    projects.value = data
    if (data.length > 0 && activeTab.value === 'debug') {
      activeTab.value = String(data[0].id)
    }
    load()
  } catch (e) {
    ElMessage.error('加载项目列表失败')
  }
}

async function load() {
  // 「现场调试版本」tab 由 DebugVersionPanel 自行加载，这里不拉大版本
  if (activeTab.value === 'debug') { majorVersions.value = []; return }
  loading.value = true
  try {
    const { data } = await majorVersionApi.list(Number(activeTab.value))
    majorVersions.value = data
  } catch (e) {
    ElMessage.error('加载版本失败')
  } finally {
    loading.value = false
  }
}

function onTabChange() {
  load()
}

// ===== 大版本 =====
function openCreateMajor() {
  editingMajor.value = null
  Object.assign(majorForm, defaultMajorForm())
  majorDialogVisible.value = true
}

function openEditMajor(row) {
  editingMajor.value = row
  Object.assign(majorForm, {
    version_no: row.version_no,
    title: row.title,
    description: row.description,
    range_start: row.range_start,
    range_end: row.range_end,
    branch_name: row.branch_name || '',
  })
  majorDialogVisible.value = true
}

async function onSubmitMajor() {
  if (!majorForm.version_no.trim()) {
    ElMessage.warning('版本号不能为空')
    return
  }
  try {
    const projectId = Number(activeTab.value)
    if (editingMajor.value) {
      await majorVersionApi.update(editingMajor.value.id, majorForm)
      ElMessage.success('已更新')
    } else {
      await majorVersionApi.create({ ...majorForm, project_id: projectId })
      ElMessage.success('已创建，如需接管主干请点「设为主干」')
    }
    majorDialogVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function onSetMaster(row) {
  const cur = majorVersions.value.find(m => m.line === 'master' && m.id !== row.id)
  await ElMessageBox.confirm(
    cur
      ? `将「${row.version_no}」设为主干，「${cur.version_no}」会同时被拉为分支，确认吗？`
      : `将「${row.version_no}」设为主干？`,
    '切换主干',
    { type: 'warning' }
  )
  try {
    await majorVersionApi.setMaster(row.id)
    ElMessage.success('已切换主干')
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '切换失败')
  }
}

async function onDeleteMajor(row) {
  await ElMessageBox.confirm(
    `确认删除大版本「${row.version_no}」及其下所有版本、迭代版本吗？`,
    '警告',
    { type: 'warning' }
  )
  try {
    await majorVersionApi.remove(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

// ===== 版本 =====
function openCreateRelease(majorRow) {
  editingRelease.value = null
  currentMajor.value = majorRow
  Object.assign(releaseForm, defaultReleaseForm(), {
    version_no: suggestReleaseNo(majorRow),
    major_version_id: majorRow.id,
    sort_order: majorRow.release_versions?.length || 0,
  })
  releaseDialogVisible.value = true
}

function openEditRelease(rv, majorRow) {
  editingRelease.value = rv
  currentMajor.value = majorRow
  Object.assign(releaseForm, {
    version_no: rv.version_no,
    title: rv.title,
    description: rv.description,
    planned_date: rv.planned_date,
    actual_release_date: rv.actual_release_date,
    major_version_id: rv.major_version_id ?? majorRow.id,
    // 编辑时不带 sort_order：改挂大版本后由服务端排到新父级末尾，
    // 把旧序号原样传回去会让它插进目标那一堆的中间，看着像随机落点
    sort_order: undefined,
  })
  releaseDialogVisible.value = true
}

async function onSubmitRelease() {
  if (!releaseForm.version_no.trim()) {
    ElMessage.warning('版本号不能为空')
    return
  }
  if (!releaseForm.major_version_id) {
    ElMessage.warning('请选择所属大版本')
    return
  }
  try {
    if (editingRelease.value) {
      const moved = releaseForm.major_version_id !== editingRelease.value.major_version_id
      const { sort_order, ...rest } = releaseForm       // eslint-disable-line no-unused-vars
      await majorVersionApi.updateRelease(editingRelease.value.id, rest)
      ElMessage.success(moved ? '已挪到新的大版本下' : '已更新')
    } else {
      await majorVersionApi.createRelease({
        ...releaseForm,
        sort_order: releaseForm.sort_order ?? 0,
      })
      ElMessage.success('已创建')
    }
    releaseDialogVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function onDeleteRelease(rv) {
  const n = rv.iteration_versions?.length || 0
  await ElMessageBox.confirm(
    n ? `确认删除版本「${rv.version_no}」及其下 ${n} 个迭代版本吗？`
      : `确认删除版本「${rv.version_no}」吗？`,
    '警告',
    { type: 'warning' }
  )
  try {
    await majorVersionApi.removeRelease(rv.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

// ===== 迭代版本 =====
function openCreateIter(releaseRow) {
  editingIter.value = null
  currentRelease.value = releaseRow
  Object.assign(iterForm, defaultIterForm(), {
    version_no: suggestIterNo(releaseRow),
    release_version_id: releaseRow.id,
    sort_order: releaseRow.iteration_versions?.length || 0,
  })
  iterDialogVisible.value = true
}

function openEditIter(row, releaseRow) {
  editingIter.value = row
  currentRelease.value = releaseRow
  Object.assign(iterForm, {
    version_no: row.version_no,
    title: row.title,
    planned_date: row.planned_date,
    actual_release_date: row.actual_release_date,
    release_version_id: row.release_version_id ?? releaseRow.id,
    sort_order: undefined,      // 同上：改挂版本后由服务端排到末尾
  })
  iterDialogVisible.value = true
}

async function onSubmitIter() {
  if (!iterForm.version_no.trim()) {
    ElMessage.warning('版本号不能为空')
    return
  }
  if (!iterForm.release_version_id) {
    ElMessage.warning('请选择所属版本')
    return
  }
  try {
    if (editingIter.value) {
      const moved = iterForm.release_version_id !== editingIter.value.release_version_id
      const { sort_order, ...rest } = iterForm          // eslint-disable-line no-unused-vars
      await majorVersionApi.updateIterVersion(editingIter.value.id, rest)
      ElMessage.success(moved ? '已挪到新的版本下' : '已更新')
    } else {
      await majorVersionApi.createIterVersion({
        ...iterForm,
        sort_order: iterForm.sort_order ?? 0,
      })
      ElMessage.success('已创建')
    }
    iterDialogVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function onDeleteIter(row) {
  await ElMessageBox.confirm(`确认删除迭代版本「${row.version_no}」吗？`, '提示', { type: 'warning' })
  try {
    await majorVersionApi.removeIterVersion(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

onMounted(loadProjects)
</script>

<style scoped>
.project-tabs {
  margin-bottom: 0;
}
.toolbar {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.tip {
  margin-left: auto;
  color: #909399;
  font-size: 12px;
}
.expand-area {
  padding: 12px 20px 12px 40px;
  background: #fafafa;
}
.expand-area-inner {
  padding: 10px 16px 10px 28px;
  background: #f2f4f7;
}
.expand-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.expand-title {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
}
.branch-meta {
  margin-left: 6px;
  color: #909399;
  font-size: 12px;
}
.form-tip {
  color: #909399;
  font-size: 12px;
  line-height: 1.6;
}
.muted { color: #909399; }
</style>
