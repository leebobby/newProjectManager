<template>
  <div v-if="!auth.isAdmin.value">
    <el-empty description="此页面仅管理员可见。请从左侧选择具体专项 / 攻关查看详情。" />
  </div>
  <div v-else>
    <!-- 专项本体与版式模板是同一件事的两面（有哪些专项 / 每个专项长什么样），
         收进同一页的两个 tab；模板原来是顶层独立菜单，找起来不顺手 -->
    <el-tabs v-model="pageTab" class="page-tabs">
      <el-tab-pane label="专项 / 攻关" name="list">
        <el-card shadow="never">
          <div class="toolbar">
            <el-button type="primary" :icon="Plus" @click="openDialog()">新增</el-button>
            <el-button :icon="Refresh" @click="load">刷新</el-button>
            <el-checkbox v-model="includeInactive" @change="load">显示停用</el-checkbox>
          </div>
          <el-table :data="list" v-loading="loading" border stripe style="width: 100%">
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column label="类型" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="row.kind === 'assault' ? 'danger' : 'info'" size="small">
                  {{ row.kind === 'assault' ? '攻关' : '专项' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="name" label="名称" min-width="160" />
            <el-table-column prop="owner" label="责任人" width="140" />
            <el-table-column label="周报收件人" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">{{ row.email_to || '-' }}</template>
            </el-table-column>
            <el-table-column label="排序" width="80" align="center">
              <template #default="{ row }">{{ row.sort_order }}</template>
            </el-table-column>
            <el-table-column label="状态" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                  {{ row.is_active ? '启用' : '停用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="240" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="onOpen(row)">打开页面</el-button>
                <el-button size="small" @click="openDialog(row)">编辑</el-button>
                <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="版式模板" name="templates">
        <!-- KeepAlive：首次懒加载，之后切回来秒显 -->
        <KeepAlive>
          <SpecialTemplates v-if="pageTab === 'templates'" />
        </KeepAlive>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="dialog.visible" :title="dialog.editing ? '编辑' : '新增'" width="560px">
      <el-form :model="dialog.form" label-width="120px">
        <el-form-item label="类型">
          <el-radio-group v-model="dialog.form.kind">
            <el-radio value="special">专项</el-radio>
            <el-radio value="assault">攻关</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="dialog.form.name" :placeholder="dialog.form.kind === 'assault' ? '攻关名称' : '专项名称'" />
        </el-form-item>
        <!-- 版式模板只在新建时选：建完再改版式走详情页的「套用模板」，那里能保证不删已填内容 -->
        <el-form-item v-if="!dialog.editing" label="版式模板">
          <el-select v-model="dialog.form.template_id" clearable placeholder="不套用（默认版式）" style="width: 100%">
            <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id">
              <span>{{ t.name }}</span>
              <span class="tpl-desc">{{ t.description }}</span>
            </el-option>
          </el-select>
          <div class="tpl-hint">
            决定详情页有哪些分段、各叫什么、什么顺序。模板在本页的
            <el-link type="primary" :underline="false" @click="gotoTemplates">版式模板</el-link> 标签页维护。
          </div>
        </el-form-item>
        <el-form-item label="责任人">
          <el-input v-model="dialog.form.owner" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="dialog.form.sort_order" :min="0" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="dialog.form.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
        <el-divider content-position="left">周报默认值（可留空）</el-divider>
        <el-form-item label="主送收件人">
          <el-input v-model="dialog.form.email_to" placeholder="多个邮箱用 , 分隔" />
        </el-form-item>
        <el-form-item label="抄送">
          <el-input v-model="dialog.form.email_cc" placeholder="多个邮箱用 , 分隔" />
        </el-form-item>
        <el-form-item label="主题模板">
          <el-input
            v-model="dialog.form.email_subject_tpl"
            :placeholder="`留空则用 【${dialog.form.kind === 'assault' ? '攻关' : '专项'}周报】{name} - {date}`"
          />
          <div class="tpl-hint">可用占位符：<code>{label}</code> <code>{name}</code> <code>{owner}</code> <code>{date}</code></div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { specialApi, specialTemplateApi } from '../api'
import { reloadSpecials } from '../store/specials'
import { auth } from '../store/auth'
import SpecialTemplates from './SpecialTemplates.vue'

const route = useRoute()
// 顶层 tab：list=专项/攻关 / templates=版式模板。支持 ?tab=templates 深链——
// /special-templates 那条老路由还在（已从菜单隐藏），会重定向到这里
const pageTab = ref(route.query.tab === 'templates' ? 'templates' : 'list')

const list = ref([])
const templates = ref([])
const loading = ref(false)
const includeInactive = ref(true)
const router = useRouter()
const dialog = reactive({
  visible: false,
  editing: null,
  form: defaultForm(),
})

function defaultForm() {
  return {
    name: '',
    kind: 'special',
    template_id: null,
    owner: '',
    sort_order: 0,
    is_active: true,
    email_to: '',
    email_cc: '',
    email_subject_tpl: '',
  }
}

async function loadTemplates() {
  try {
    const { data } = await specialTemplateApi.list()
    templates.value = data
  } catch { templates.value = [] }   // 模板拉不到不该挡住建专项，留空＝用默认版式
}

async function load() {
  loading.value = true
  try {
    const { data } = await specialApi.list(includeInactive.value)
    list.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

function openDialog(row) {
  dialog.editing = row || null
  if (row) {
    dialog.form = {
      name: row.name,
      kind: row.kind || 'special',
      owner: row.owner || '',
      sort_order: row.sort_order || 0,
      is_active: !!row.is_active,
      email_to: row.email_to || '',
      email_cc: row.email_cc || '',
      email_subject_tpl: row.email_subject_tpl || '',
    }
  } else {
    dialog.form = { ...defaultForm(), sort_order: list.value.length }
  }
  dialog.visible = true
}

async function onSubmit() {
  const f = dialog.form
  if (!f.name.trim()) {
    ElMessage.warning('请输入名称')
    return
  }
  try {
    if (dialog.editing) {
      await specialApi.update(dialog.editing.id, f)
      ElMessage.success('已更新')
    } else {
      await specialApi.create(f)
      ElMessage.success('已创建')
    }
    dialog.visible = false
    await load()
    await reloadSpecials()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function onDelete(row) {
  const label = row.kind === 'assault' ? '攻关' : '专项'
  await ElMessageBox.confirm(
    `确认删除${label}「${row.name}」？相关内容、事务、风险都会一并删除`,
    '提示', { type: 'warning' }
  )
  try {
    await specialApi.remove(row.id)
    ElMessage.success('已删除')
    await load()
    await reloadSpecials()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

function onOpen(row) {
  router.push(`/specials/${row.id}`)
}

function gotoTemplates() {
  dialog.visible = false
  pageTab.value = 'templates'
}

// 从模板页切回来时重新拉一遍：刚在那边加的模板要能出现在「新增专项」的下拉里
watch(pageTab, (v, old) => {
  if (v === 'list' && old === 'templates') loadTemplates()
})

onMounted(() => { load(); loadTemplates() })
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}
.tpl-hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
  margin-top: 4px;
}
.tpl-desc {
  float: right;
  margin-left: 16px;
  color: #909399;
  font-size: 12px;
}
.tpl-hint code {
  background: #f5f7fa;
  padding: 1px 5px;
  margin: 0 2px;
  border-radius: 3px;
  font-size: 12px;
}
</style>
