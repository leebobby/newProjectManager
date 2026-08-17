<template>
  <div class="stakeholder-page">
    <!-- 项目组沟通地图 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">
            <el-icon><UserFilled /></el-icon> 项目组沟通地图
          </span>
          <el-button v-if="isAdmin" type="primary" size="small" :icon="Plus" @click="openProjectDialog()">
            新增
          </el-button>
        </div>
      </template>

      <el-table :data="projectContacts" v-loading="loadingProject" border stripe class="contact-table">
        <el-table-column type="index" label="#" width="50" align="center" />
        <el-table-column prop="col1" label="角色" min-width="160" />
        <el-table-column prop="col2" label="姓名 / 工号" min-width="200" />
        <el-table-column v-if="isAdmin" label="操作" width="140" align="center">
          <template #default="{ row }">
            <el-button size="small" type="primary" text :icon="EditIcon" @click="openProjectDialog(row)">编辑</el-button>
            <el-popconfirm title="确认删除该条目？" @confirm="deleteProjectContact(row.id)">
              <template #reference>
                <el-button size="small" type="danger" text :icon="Delete">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!loadingProject && projectContacts.length === 0" class="empty-hint">
        暂无数据{{ isAdmin ? '，点击右上角「新增」添加条目' : '' }}
      </div>
    </el-card>

    <!-- 战场沟通矩阵 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">
            <el-icon><Grid /></el-icon> 战场沟通矩阵
          </span>
          <el-button v-if="isAdmin" type="primary" size="small" :icon="Plus" @click="openBattlefieldDialog()">
            新增
          </el-button>
        </div>
      </template>

      <el-table :data="battlefields" v-loading="loadingBattlefield" border stripe class="battlefield-table">
        <el-table-column type="index" label="#" width="50" align="center" />
        <el-table-column prop="battlefield" label="客户" min-width="120" />
        <el-table-column prop="region" label="地域" min-width="80" />
        <el-table-column prop="service" label="服务" min-width="120" />
        <el-table-column label="联系方式" min-width="180">
          <template #default="{ row }">
            <span class="pre-text">{{ row.contact1 }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="apps" label="APPS" min-width="120" />
        <el-table-column label="联系方式" min-width="180">
          <template #default="{ row }">
            <span class="pre-text">{{ row.contact2 }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin" label="操作" width="140" align="center">
          <template #default="{ row }">
            <el-button size="small" type="primary" text :icon="EditIcon" @click="openBattlefieldDialog(row)">编辑</el-button>
            <el-popconfirm title="确认删除该条目？" @confirm="deleteBattlefield(row.id)">
              <template #reference>
                <el-button size="small" type="danger" text :icon="Delete">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!loadingBattlefield && battlefields.length === 0" class="empty-hint">
        暂无数据{{ isAdmin ? '，点击右上角「新增」添加条目' : '' }}
      </div>
    </el-card>

    <!-- 项目阵型 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">
            <el-icon><DataAnalysis /></el-icon> 项目阵型
          </span>
        </div>
      </template>

      <el-tabs v-model="formationTab" class="formation-tabs">
        <!-- Tab 1: 阵型图 -->
        <el-tab-pane label="阵型图" name="image">
          <div class="formation-mode-bar">
            <el-radio-group v-model="formationMode" size="small">
              <el-radio-button value="org">组织阵型图（自动）</el-radio-button>
              <el-radio-button value="upload">上传图片</el-radio-button>
            </el-radio-group>
          </div>

          <!-- 自动组织树 -->
          <div v-if="formationMode === 'org'" class="org-tree-wrap">
            <div v-if="orgTree.length === 0" class="empty-hint">
              暂无组织架构，请先到「组织架构」页建立 部门 / PL 组，并在「用户管理」给成员挂上 PL 组
            </div>
            <div v-else class="org-tree">
              <div v-for="dept in orgTree" :key="dept.id" class="org-dept">
                <div class="org-dept-head">
                  <el-icon><OfficeBuilding /></el-icon>
                  <span class="org-dept-name">{{ dept.name }}</span>
                  <span v-if="dept.leader_name" class="org-leader">负责人：{{ dept.leader_name }}</span>
                  <span class="org-dept-count">{{ dept.memberCount }} 人</span>
                </div>
                <div class="org-pl-row">
                  <div v-for="pl in dept.pls" :key="pl.id" class="org-pl">
                    <div class="org-pl-head">
                      <span class="org-pl-name">{{ pl.name }}</span>
                      <span v-if="pl.leader_name" class="org-pl-leader">PL：{{ pl.leader_name }}</span>
                    </div>
                    <div class="org-members">
                      <div v-for="m in pl.members" :key="m.id" class="org-member">
                        <span class="m-name">{{ m.full_name || m.username }}</span>
                        <span v-if="m.job_title" class="m-title">{{ m.job_title }}</span>
                      </div>
                      <div v-if="pl.members.length === 0" class="org-member empty">（暂无成员）</div>
                    </div>
                  </div>
                  <div v-if="dept.pls.length === 0" class="org-pl-empty">该部门下暂无 PL 组</div>
                </div>
              </div>
            </div>
            <div class="org-tree-tip">
              此图由「组织架构 + 用户管理」自动生成，随组织调整实时更新；如需手绘版本，请切到「上传图片」。
            </div>
          </div>

          <!-- 上传图片（保留原功能）-->
          <div v-else class="formation-image-wrap">
            <div class="formation-image-toolbar">
              <el-upload
                v-if="isAdmin"
                :auto-upload="false"
                :on-change="onUploadFormationImage"
                :show-file-list="false"
                accept="image/*,.svg"
              >
                <el-button size="small">{{ formationImage.image_name ? '替换图片' : '上传阵型图' }}</el-button>
              </el-upload>
              <span v-if="formationImage.image_name" class="img-name">当前：{{ formationImage.image_name }}</span>
            </div>
            <div class="formation-image-body">
              <img v-if="formationImageSrc" :src="formationImageSrc" alt="项目阵型图" class="formation-img" />
              <div v-else class="formation-image-empty">尚未上传阵型图</div>
            </div>
          </div>
        </el-tab-pane>

        <!-- Tab 2: 工时名单 -->
        <el-tab-pane :label="`工时名单 (${members.length})`" name="members">
          <div class="member-toolbar">
            <el-input
              v-model="memberKeyword"
              placeholder="搜索 姓名/工号/PL组/角色/挂靠专项"
              clearable
              style="width: 280px"
            />
            <div class="spacer" />
            <el-button :icon="Download" @click="onDownloadTemplate">下载模板</el-button>
            <el-button v-if="isAdmin" :icon="Upload" @click="importDialogVisible = true">导入</el-button>
            <el-button :icon="Download" @click="onExportXlsx">导出</el-button>
            <el-button v-if="isAdmin" type="primary" :icon="Plus" @click="openMemberDialog()">新增</el-button>
          </div>

          <el-table :data="filteredMembers" v-loading="memberLoading" border stripe style="width: 100%" size="small">
            <el-table-column type="index" label="#" width="50" align="center" />
            <el-table-column prop="name" label="姓名" width="100" />
            <el-table-column prop="emp_no" label="工号" width="100" />
            <el-table-column prop="pl_group" label="PL组" width="100" />
            <el-table-column prop="role" label="角色" width="100" />
            <el-table-column prop="special_attach" label="挂靠专项" min-width="160" />
            <el-table-column prop="allocation" label="投入比例" width="100" />
            <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
            <el-table-column v-if="isAdmin" label="操作" width="160" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="openMemberDialog(row)">编辑</el-button>
                <el-popconfirm title="确认删除该成员？" @confirm="onDeleteMember(row.id)">
                  <template #reference>
                    <el-button size="small" type="danger">删除</el-button>
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>

          <div v-if="!memberLoading && members.length === 0" class="empty-hint">
            暂无人员{{ isAdmin ? '，点击「新增」添加或「导入」批量上传 Excel' : '' }}
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 项目阵型成员 Dialog -->
    <el-dialog
      v-model="memberDialogVisible"
      :title="memberForm.id ? '编辑成员' : '新增成员'"
      width="520px"
      @close="resetMemberForm"
    >
      <el-form :model="memberForm" label-width="90px">
        <el-form-item label="姓名" required>
          <el-input v-model="memberForm.name" />
        </el-form-item>
        <el-form-item label="工号">
          <el-input v-model="memberForm.emp_no" />
        </el-form-item>
        <el-form-item label="PL组">
          <el-input v-model="memberForm.pl_group" />
        </el-form-item>
        <el-form-item label="角色">
          <el-input v-model="memberForm.role" placeholder="如 开发 / 测试 / 产品" />
        </el-form-item>
        <el-form-item label="挂靠专项">
          <el-input v-model="memberForm.special_attach" placeholder="可填多个，逗号分隔" />
        </el-form-item>
        <el-form-item label="投入比例">
          <el-input v-model="memberForm.allocation" placeholder="0.5 / 30% / 全职" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="memberForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="memberDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="memberSaving" @click="saveMember">保存</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入 Dialog -->
    <el-dialog v-model="importDialogVisible" title="批量导入人员" width="500px">
      <p class="import-tip">
        1. 先下载模板，按格式填写人员清单；<br />
        2. 表头列名请勿改动；姓名必填，其它字段可留空；<br />
        3. 上传 .xlsx 文件批量入库。
      </p>
      <el-button :icon="Download" link type="primary" @click="onDownloadTemplate">下载导入模板</el-button>
      <el-divider />
      <el-checkbox v-model="importReplace">导入前先清空现有名单（覆盖模式）</el-checkbox>
      <el-upload
        ref="memberUploadRef"
        :auto-upload="false"
        :limit="1"
        :on-exceed="onMemberExceed"
        :on-change="onMemberFileChange"
        :show-file-list="true"
        accept=".xlsx"
        drag
        style="margin-top: 12px"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽 .xlsx 文件到此，或<em>点击选择</em></div>
      </el-upload>
      <div v-if="importResult" class="import-result">
        <div v-if="importResult.cleared">已清空旧数据 {{ importResult.cleared }} 条。</div>
        <div>成功导入 <b>{{ importResult.created }}</b> 条。</div>
        <div v-if="importResult.errors?.length" class="errors">
          错误 {{ importResult.errors.length }} 条：
          <ul>
            <li v-for="(e, i) in importResult.errors" :key="i">{{ e }}</li>
          </ul>
        </div>
      </div>
      <template #footer>
        <el-button @click="importDialogVisible = false">关闭</el-button>
        <el-button type="primary" :loading="importing" :disabled="!importFile" @click="onSubmitImport">开始导入</el-button>
      </template>
    </el-dialog>

    <!-- 项目组联系人 Dialog -->
    <el-dialog
      v-model="projectDialogVisible"
      :title="projectForm.id ? '编辑联系人' : '新增联系人'"
      width="480px"
      @close="resetProjectForm"
    >
      <el-form :model="projectForm" label-width="90px">
        <el-form-item label="角色">
          <el-input v-model="projectForm.col1" placeholder="请输入角色名称" />
        </el-form-item>
        <el-form-item label="姓名/工号">
          <el-input v-model="projectForm.col2" placeholder="请输入姓名或工号" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="projectDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="projectSaving" @click="saveProjectContact">保存</el-button>
      </template>
    </el-dialog>

    <!-- 战场沟通矩阵 Dialog -->
    <el-dialog
      v-model="battlefieldDialogVisible"
      :title="battlefieldForm.id ? '编辑战场条目' : '新增战场条目'"
      width="560px"
      @close="resetBattlefieldForm"
    >
      <el-form :model="battlefieldForm" label-width="90px">
        <el-form-item label="客户">
          <el-select
            v-model="battlefieldForm.battlefield"
            placeholder="从客户管理中选择"
            filterable
            style="width: 100%"
          >
            <el-option
              v-for="c in customerList"
              :key="c.id"
              :label="c.display_name ? `${c.code} · ${c.display_name}` : c.code"
              :value="c.code"
            />
          </el-select>
          <div class="form-hint">
            选项来自客户管理；没有想要的客户？请联系管理员先到「客户面状态 → 客户管理」新增
          </div>
        </el-form-item>
        <el-form-item label="地域">
          <el-input v-model="battlefieldForm.region" placeholder="地域" />
        </el-form-item>
        <el-form-item label="服务">
          <el-input v-model="battlefieldForm.service" placeholder="服务名称" />
        </el-form-item>
        <el-form-item label="联系方式">
          <el-input
            v-model="battlefieldForm.contact1"
            type="textarea"
            :rows="3"
            placeholder="服务联系方式（支持多行）"
          />
        </el-form-item>
        <el-form-item label="APPS">
          <el-input v-model="battlefieldForm.apps" placeholder="APPS 名称" />
        </el-form-item>
        <el-form-item label="联系方式">
          <el-input
            v-model="battlefieldForm.contact2"
            type="textarea"
            :rows="3"
            placeholder="APPS 联系方式（支持多行）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="battlefieldDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="battlefieldSaving" @click="saveBattlefield">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { DataAnalysis, Delete, Download, Edit as EditIcon, Grid, OfficeBuilding, Plus, Upload, UploadFilled, UserFilled } from '@element-plus/icons-vue'
import { auth } from '../store/auth'
import http, { customerApi, downloadBlob, formationApi, resourceGroupApi, stakeholderApi, userApi } from '../api'
import { checkStorageOrWarn } from '../store/storage'

const isAdmin = auth.isAdmin

// ── 项目组沟通地图 ─────────────────────────────────────────
const projectContacts     = ref([])
const loadingProject      = ref(false)
const projectDialogVisible = ref(false)
const projectSaving       = ref(false)
const projectForm         = reactive({ id: null, col1: '', col2: '' })

async function loadProjectContacts() {
  loadingProject.value = true
  try {
    const { data } = await stakeholderApi.listProjectContacts()
    projectContacts.value = data
  } catch {
    ElMessage.error('加载项目组沟通地图失败')
  } finally {
    loadingProject.value = false
  }
}

function openProjectDialog(row = null) {
  if (row) {
    Object.assign(projectForm, { id: row.id, col1: row.col1, col2: row.col2 })
  }
  projectDialogVisible.value = true
}

function resetProjectForm() {
  Object.assign(projectForm, { id: null, col1: '', col2: '' })
}

async function saveProjectContact() {
  projectSaving.value = true
  try {
    const payload = { col1: projectForm.col1, col2: projectForm.col2 }
    if (projectForm.id) {
      await stakeholderApi.updateProjectContact(projectForm.id, payload)
    } else {
      await stakeholderApi.createProjectContact(payload)
    }
    ElMessage.success('已保存')
    projectDialogVisible.value = false
    await loadProjectContacts()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    projectSaving.value = false
  }
}

async function deleteProjectContact(id) {
  try {
    await stakeholderApi.removeProjectContact(id)
    ElMessage.success('已删除')
    await loadProjectContacts()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

// ── 战场沟通矩阵 ──────────────────────────────────────────
const battlefields          = ref([])
const loadingBattlefield    = ref(false)
const battlefieldDialogVisible = ref(false)
const battlefieldSaving     = ref(false)
const battlefieldForm       = reactive({
  id: null, battlefield: '', region: '', service: '', contact1: '', apps: '', contact2: '',
})

// 客户下拉的可选项（从客户管理加载）
const customerList = ref([])
async function loadCustomerList() {
  try {
    const { data } = await customerApi.list(false)
    customerList.value = data || []
  } catch {
    // 静默：客户列表加载失败不阻塞页面
  }
}

async function loadBattlefields() {
  loadingBattlefield.value = true
  try {
    const { data } = await stakeholderApi.listBattlefields()
    battlefields.value = data
  } catch {
    ElMessage.error('加载战场沟通矩阵失败')
  } finally {
    loadingBattlefield.value = false
  }
}

function openBattlefieldDialog(row = null) {
  if (row) {
    Object.assign(battlefieldForm, {
      id: row.id,
      battlefield: row.battlefield,
      region: row.region,
      service: row.service,
      contact1: row.contact1,
      apps: row.apps,
      contact2: row.contact2,
    })
  }
  battlefieldDialogVisible.value = true
}

function resetBattlefieldForm() {
  Object.assign(battlefieldForm, {
    id: null, battlefield: '', region: '', service: '', contact1: '', apps: '', contact2: '',
  })
}

async function saveBattlefield() {
  battlefieldSaving.value = true
  try {
    const payload = {
      battlefield: battlefieldForm.battlefield,
      region:      battlefieldForm.region,
      service:     battlefieldForm.service,
      contact1:    battlefieldForm.contact1,
      apps:        battlefieldForm.apps,
      contact2:    battlefieldForm.contact2,
    }
    if (battlefieldForm.id) {
      await stakeholderApi.updateBattlefield(battlefieldForm.id, payload)
    } else {
      await stakeholderApi.createBattlefield(payload)
    }
    ElMessage.success('已保存')
    battlefieldDialogVisible.value = false
    await loadBattlefields()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    battlefieldSaving.value = false
  }
}

async function deleteBattlefield(id) {
  try {
    await stakeholderApi.removeBattlefield(id)
    ElMessage.success('已删除')
    await loadBattlefields()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

// ── 项目阵型 ──────────────────────────────────────────────
const formationTab = ref('image')

// 阵型图：自动组织树 vs 上传图片
const formationMode = ref('org')
const orgGroups = ref([])
const orgUsers = ref([])

const orgTree = computed(() => {
  const depts = orgGroups.value.filter((g) => g.kind === 'dept')
  const pls = orgGroups.value.filter((g) => g.kind === 'pl')
  const byGroup = {}
  for (const u of orgUsers.value) {
    if (u.group_id == null) continue
    ;(byGroup[u.group_id] || (byGroup[u.group_id] = [])).push(u)
  }
  return depts.map((d) => {
    const childPls = pls
      .filter((p) => p.parent_id === d.id)
      .map((p) => ({ ...p, members: byGroup[p.id] || [] }))
    const memberCount = childPls.reduce((sum, p) => sum + p.members.length, 0)
    return { ...d, pls: childPls, memberCount }
  })
})

async function loadOrg() {
  try {
    const [{ data: gs }, { data: us }] = await Promise.all([
      resourceGroupApi.list({}),
      userApi.options({ include_inactive: false }),
    ])
    orgGroups.value = gs
    orgUsers.value = us
  } catch {
    // 静默：组织树加载失败不阻塞页面（可回退到上传图片）
  }
}

// 阵型图（上传图片）
const formationImage = ref({ image_path: '', image_name: '', updated_at: null })
const formationImageSrc = ref('')

async function loadFormationImageInfo() {
  try {
    const { data } = await formationApi.imageInfo()
    formationImage.value = data
    if (data.image_path) await loadFormationImageBlob()
    else {
      if (formationImageSrc.value) URL.revokeObjectURL(formationImageSrc.value)
      formationImageSrc.value = ''
    }
  } catch { /* 静默 */ }
}

async function loadFormationImageBlob() {
  try {
    const resp = await http.get('/project-formation/image', { responseType: 'blob' })
    if (formationImageSrc.value) URL.revokeObjectURL(formationImageSrc.value)
    formationImageSrc.value = URL.createObjectURL(resp.data)
  } catch {
    formationImageSrc.value = ''
  }
}

async function onUploadFormationImage(uploadFile) {
  const file = uploadFile?.raw || uploadFile
  const ct = (file?.type || '').toLowerCase()
  const okType =
    ct.startsWith('image/') ||
    ct === 'image/svg+xml' ||
    (file?.name || '').toLowerCase().endsWith('.svg')
  if (!file || !okType) {
    ElMessage.warning('仅支持图片或 SVG 文件')
    return
  }
  await checkStorageOrWarn()
  try {
    const { data } = await formationApi.uploadImage(file)
    formationImage.value = data
    await loadFormationImageBlob()
    ElMessage.success('阵型图已更新')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '上传失败')
  }
}

// 人员名单
const members = ref([])
const memberLoading = ref(false)
const memberKeyword = ref('')
const memberDialogVisible = ref(false)
const memberSaving = ref(false)
const memberForm = reactive({
  id: null, name: '', emp_no: '', pl_group: '', role: '',
  special_attach: '', allocation: '', remark: '',
})

const filteredMembers = computed(() => {
  if (!memberKeyword.value.trim()) return members.value
  const k = memberKeyword.value.trim().toLowerCase()
  return members.value.filter(m =>
    (m.name || '').toLowerCase().includes(k) ||
    (m.emp_no || '').toLowerCase().includes(k) ||
    (m.pl_group || '').toLowerCase().includes(k) ||
    (m.role || '').toLowerCase().includes(k) ||
    (m.special_attach || '').toLowerCase().includes(k)
  )
})

async function loadMembers() {
  memberLoading.value = true
  try {
    const { data } = await formationApi.listMembers()
    members.value = data
  } catch {
    ElMessage.error('加载人员名单失败')
  } finally {
    memberLoading.value = false
  }
}

function openMemberDialog(row = null) {
  if (row) {
    Object.assign(memberForm, {
      id: row.id, name: row.name, emp_no: row.emp_no, pl_group: row.pl_group,
      role: row.role, special_attach: row.special_attach,
      allocation: row.allocation, remark: row.remark,
    })
  }
  memberDialogVisible.value = true
}

function resetMemberForm() {
  Object.assign(memberForm, {
    id: null, name: '', emp_no: '', pl_group: '', role: '',
    special_attach: '', allocation: '', remark: '',
  })
}

async function saveMember() {
  if (!memberForm.name.trim()) {
    ElMessage.warning('请输入姓名')
    return
  }
  memberSaving.value = true
  try {
    const payload = { ...memberForm }
    delete payload.id
    if (memberForm.id) {
      await formationApi.updateMember(memberForm.id, payload)
    } else {
      await formationApi.createMember(payload)
    }
    ElMessage.success('已保存')
    memberDialogVisible.value = false
    await loadMembers()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    memberSaving.value = false
  }
}

async function onDeleteMember(id) {
  try {
    await formationApi.removeMember(id)
    ElMessage.success('已删除')
    await loadMembers()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

// 导入 / 导出
const importDialogVisible = ref(false)
const importReplace = ref(false)
const importFile = ref(null)
const importing = ref(false)
const importResult = ref(null)
const memberUploadRef = ref(null)

async function onDownloadTemplate() {
  try {
    const { data } = await formationApi.importTemplate()
    downloadBlob(data, 'project-formation-template.xlsx')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '模板下载失败')
  }
}

async function onExportXlsx() {
  try {
    const { data } = await formationApi.exportXlsx()
    const ts = new Date().toISOString().slice(0, 10).replace(/-/g, '')
    downloadBlob(data, `项目阵型人员_${ts}.xlsx`)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导出失败')
  }
}

function onMemberFileChange(uploadFile) {
  importFile.value = uploadFile?.raw || uploadFile
}

function onMemberExceed() {
  ElMessage.warning('一次只能选一个文件，请先移除再选择')
}

async function onSubmitImport() {
  if (!importFile.value) return
  importing.value = true
  importResult.value = null
  try {
    const { data } = await formationApi.importMembers(importFile.value, importReplace.value)
    importResult.value = data
    ElMessage.success(`导入完成：成功 ${data.created} 条，错误 ${data.errors?.length || 0} 条`)
    await loadMembers()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  } finally {
    importing.value = false
  }
}

onMounted(() => {
  loadProjectContacts()
  loadBattlefields()
  loadFormationImageInfo()
  loadOrg()
  loadMembers()
  loadCustomerList()
})
</script>

<style scoped>
.stakeholder-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-card :deep(.el-card__header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.pre-text {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
}

.empty-hint {
  text-align: center;
  color: #909399;
  padding: 32px 0;
  font-size: 13px;
}

.form-hint {
  color: #909399;
  font-size: 12px;
  line-height: 1.5;
  margin-top: 4px;
}

.contact-table :deep(.el-table__cell),
.battlefield-table :deep(.el-table__cell) {
  vertical-align: top;
  padding: 10px 12px;
}

/* ── 项目阵型 ── */
.formation-tabs :deep(.el-tabs__nav) {
  font-weight: 500;
}
.formation-image-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.formation-image-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}
.formation-image-toolbar .img-name {
  color: #909399;
  font-size: 13px;
}
.formation-image-body {
  background: #fafafa;
  border: 1px solid #ebeef5;
  min-height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
.formation-img {
  max-width: 100%;
  max-height: 720px;
}
.formation-image-empty {
  color: #c0c4cc;
  padding: 60px 0;
}
/* ── 自动组织阵型树 ── */
.formation-mode-bar {
  margin-bottom: 14px;
}
.org-tree {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.org-dept {
  border: 1px solid #d9ecff;
  border-radius: 6px;
  background: #f5faff;
  padding: 12px 14px;
}
.org-dept-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #1f4e7a;
  margin-bottom: 12px;
}
.org-dept-name { font-size: 15px; }
.org-leader {
  font-size: 12px;
  font-weight: 400;
  color: #909399;
}
.org-dept-count {
  margin-left: auto;
  font-size: 12px;
  font-weight: 400;
  color: #409eff;
  background: #ecf5ff;
  border-radius: 10px;
  padding: 1px 10px;
}
.org-pl-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.org-pl {
  flex: 0 1 220px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fff;
  overflow: hidden;
}
.org-pl-head {
  background: #f0f5ff;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  border-bottom: 1px solid #ebeef5;
}
.org-pl-name { font-weight: 600; color: #303133; font-size: 13px; }
.org-pl-leader { font-size: 12px; color: #909399; }
.org-members {
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.org-member {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 13px;
}
.org-member .m-name { color: #303133; }
.org-member .m-title { color: #909399; font-size: 12px; }
.org-member.empty { color: #c0c4cc; font-size: 12px; }
.org-pl-empty {
  color: #c0c4cc;
  font-size: 12px;
  padding: 8px 4px;
}
.org-tree-tip {
  margin-top: 14px;
  color: #909399;
  font-size: 12px;
}

.member-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  align-items: center;
}
.member-toolbar .spacer { flex: 1; }
.import-tip {
  margin: 0;
  line-height: 1.8;
  color: #606266;
  font-size: 13px;
}
.import-result {
  margin-top: 12px;
  background: #f0f9ff;
  border-left: 3px solid #409EFF;
  padding: 8px 12px;
  font-size: 13px;
  line-height: 1.6;
}
.import-result .errors ul {
  margin: 4px 0 0 16px;
  padding: 0;
  color: #f56c6c;
}
</style>
