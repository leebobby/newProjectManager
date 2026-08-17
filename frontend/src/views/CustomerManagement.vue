<template>
  <div>
    <el-card shadow="never">
      <div class="toolbar">
        <el-button v-if="isAdmin" type="primary" :icon="Plus" @click="openDialog()">新增客户</el-button>
        <el-button v-if="isAdmin" :icon="Setting" @click="sowDialog.visible = true">SOW 字段配置</el-button>
        <el-button v-if="isAdmin" :icon="Setting" @click="extraDialog.visible = true">信息块配置</el-button>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
        <el-checkbox v-model="includeInactive" @change="load">显示停用</el-checkbox>
        <el-input
          v-model="filter"
          placeholder="搜索 code / 别名 / 名称"
          clearable
          style="margin-left: auto; width: 280px"
        />
      </div>

      <el-table :data="filtered" v-loading="loading" border stripe style="width: 100%">
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column label="客户编码 (Code)" width="180">
          <template #default="{ row }">
            <a class="code-link" @click="openDetail(row)">{{ row.code }}</a>
          </template>
        </el-table-column>
        <el-table-column prop="display_name" label="完整名称" min-width="160">
          <template #default="{ row }">{{ row.display_name || '—' }}</template>
        </el-table-column>
        <el-table-column prop="region" label="区域" width="110">
          <template #default="{ row }">{{ row.region || '—' }}</template>
        </el-table-column>
        <el-table-column prop="industry" label="行业" width="140">
          <template #default="{ row }">{{ row.industry || '—' }}</template>
        </el-table-column>
        <el-table-column label="别名" min-width="240">
          <template #default="{ row }">
            <el-tag
              v-for="a in row.aliases"
              :key="a.id"
              size="small"
              effect="plain"
              style="margin-right: 4px; margin-bottom: 2px"
            >
              {{ a.alias }}
            </el-tag>
            <span v-if="!row.aliases?.length" class="muted">—</span>
          </template>
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
            <el-button size="small" @click="openDetail(row)">查看详情</el-button>
            <el-button v-if="isAdmin" size="small" type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- SOW 字段配置（全局共享一份）-->
    <el-dialog
      v-model="sowDialog.visible"
      title="SOW 字段配置"
      width="820px"
      @open="loadSowFields"
    >
      <div style="margin-bottom: 8px;">
        <el-button size="small" :icon="Plus" @click="addSowField">新增列</el-button>
        <span class="muted-hint" style="margin-left: 8px;">
          所有客户、所有机台的 SOW 表格共用这一套列；停用的列不会出现在客户详情页
        </span>
      </div>
      <el-table :data="sowDialog.fields" v-loading="sowDialog.loading" border size="small">
        <el-table-column label="Key（内部）" width="140">
          <template #default="{ row }">
            <el-input v-model="row.key" size="small" :disabled="!!row.id" placeholder="如 item_name" />
          </template>
        </el-table-column>
        <el-table-column label="表头显示" min-width="160">
          <template #default="{ row }">
            <el-input v-model="row.label" size="small" placeholder="如 事项名称" />
          </template>
        </el-table-column>
        <el-table-column label="类型" width="120">
          <template #default="{ row }">
            <el-select v-model="row.field_type" size="small">
              <el-option label="文本" value="text" />
              <el-option label="日期" value="date" />
              <el-option label="下拉" value="select" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="下拉选项（逗号分隔）" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="row.field_type === 'select'"
              v-model="row.optionsText"
              size="small"
              placeholder="如 未开始,进行中,已完成"
            />
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="排序" width="80">
          <template #default="{ row }">
            <el-input-number v-model="row.sort_order" :min="0" size="small" controls-position="right" />
          </template>
        </el-table-column>
        <el-table-column label="启用" width="70" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.is_active" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row, $index }">
            <el-button size="small" type="primary" @click="saveSowField(row, $index)">保存</el-button>
            <el-button size="small" type="danger" @click="removeSowField(row, $index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="sowDialog.visible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 自定义信息块配置（全局共享一份）-->
    <el-dialog
      v-model="extraDialog.visible"
      title="自定义信息块配置"
      width="720px"
      @open="loadExtraFields"
    >
      <div style="margin-bottom: 8px;">
        <el-button size="small" :icon="Plus" @click="addExtraField">新增信息块</el-button>
        <span class="muted-hint" style="margin-left: 8px;">
          每个信息块在客户详情的每台机台下渲染为「一段文本 + 一个附件/图片」（如 MPH状态）；停用的不显示
        </span>
      </div>
      <el-table :data="extraDialog.fields" v-loading="extraDialog.loading" border size="small">
        <el-table-column label="Key（内部）" width="160">
          <template #default="{ row }">
            <el-input v-model="row.key" size="small" :disabled="!!row.id" placeholder="如 mph_status" />
          </template>
        </el-table-column>
        <el-table-column label="标题显示" min-width="180">
          <template #default="{ row }">
            <el-input v-model="row.label" size="small" placeholder="如 MPH状态" />
          </template>
        </el-table-column>
        <el-table-column label="排序" width="90">
          <template #default="{ row }">
            <el-input-number v-model="row.sort_order" :min="0" size="small" controls-position="right" />
          </template>
        </el-table-column>
        <el-table-column label="启用" width="70" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.is_active" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row, $index }">
            <el-button size="small" type="primary" @click="saveExtraField(row, $index)">保存</el-button>
            <el-button size="small" type="danger" @click="removeExtraField(row, $index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="extraDialog.visible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dialog.visible" title="新增客户" width="560px">
      <el-form :model="dialog.form" label-width="120px">
        <el-form-item label="客户编码">
          <el-input v-model="dialog.form.code" placeholder="缩写英文名，如 HW / CMCC" />
        </el-form-item>
        <el-form-item label="完整名称">
          <el-input v-model="dialog.form.display_name" placeholder="可选；不填则展示 code" />
        </el-form-item>
        <el-form-item label="区域">
          <el-input v-model="dialog.form.region" placeholder="如 华东 / 华南 / 海外" />
        </el-form-item>
        <el-form-item label="行业">
          <el-input v-model="dialog.form.industry" placeholder="可选" />
        </el-form-item>
        <el-form-item label="别名">
          <el-select
            v-model="dialog.form.aliases"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="输入回车添加多个别名"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="dialog.form.sort_order" :min="0" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="dialog.form.is_active" />
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
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Setting } from '@element-plus/icons-vue'
import { customerApi, customerExtraApi, sowApi } from '../api'
import { auth } from '../store/auth'

const isAdmin = computed(() => auth.isAdmin.value)
const router = useRouter()

const list = ref([])
const loading = ref(false)
const includeInactive = ref(true)
const filter = ref('')

const dialog = reactive({ visible: false, form: defaultForm() })

function defaultForm() {
  return {
    code: '',
    display_name: '',
    region: '',
    industry: '',
    aliases: [],
    sort_order: 0,
    is_active: true,
  }
}

const filtered = computed(() => {
  const kw = filter.value.trim().toLowerCase()
  if (!kw) return list.value
  return list.value.filter((c) => {
    if (c.code?.toLowerCase().includes(kw)) return true
    if (c.display_name?.toLowerCase().includes(kw)) return true
    if (c.region?.toLowerCase().includes(kw)) return true
    return (c.aliases || []).some((a) => a.alias.toLowerCase().includes(kw))
  })
})

async function load() {
  loading.value = true
  try {
    const { data } = await customerApi.list(includeInactive.value)
    list.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

function openDialog() {
  dialog.form = { ...defaultForm(), sort_order: list.value.length }
  dialog.visible = true
}

async function onSubmit() {
  const f = dialog.form
  if (!f.code.trim()) {
    ElMessage.warning('请输入客户编码')
    return
  }
  try {
    await customerApi.create(f)
    ElMessage.success('已创建')
    dialog.visible = false
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

function openDetail(row) {
  router.push(`/customers/${row.id}`)
}

async function onDelete(row) {
  await ElMessageBox.confirm(
    `确认删除客户「${row.code}」？所有别名将一并删除（已挂在该客户下的业务记录不会自动清理）`,
    '提示',
    { type: 'warning' }
  )
  try {
    await customerApi.remove(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

// ─── SOW 字段配置 ────────────────────────────────────────────
const sowDialog = reactive({
  visible: false,
  loading: false,
  fields: [],
})

async function loadSowFields() {
  sowDialog.loading = true
  try {
    const { data } = await sowApi.listFields(true)
    sowDialog.fields = data.map((f) => ({
      ...f,
      optionsText: (f.options || []).join(','),
    }))
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    sowDialog.loading = false
  }
}

function addSowField() {
  sowDialog.fields.push({
    id: null,
    key: '',
    label: '',
    field_type: 'text',
    options: [],
    optionsText: '',
    required: false,
    sort_order: sowDialog.fields.length,
    is_active: true,
  })
}

function parseOptions(text) {
  return (text || '')
    .split(/[,，]/)
    .map((s) => s.trim())
    .filter(Boolean)
}

async function saveSowField(row, _idx) {
  const payload = {
    key: row.key.trim(),
    label: row.label.trim() || row.key.trim(),
    field_type: row.field_type,
    options: parseOptions(row.optionsText),
    required: !!row.required,
    sort_order: row.sort_order || 0,
    is_active: !!row.is_active,
  }
  if (!payload.key) {
    ElMessage.warning('请填写 key')
    return
  }
  try {
    if (row.id) {
      // 已存在：用 update（key 不可改）
      const { data } = await sowApi.updateField(row.id, {
        label: payload.label,
        field_type: payload.field_type,
        options: payload.options,
        required: payload.required,
        sort_order: payload.sort_order,
        is_active: payload.is_active,
      })
      Object.assign(row, data, { optionsText: (data.options || []).join(',') })
    } else {
      const { data } = await sowApi.createField(payload)
      Object.assign(row, data, { optionsText: (data.options || []).join(',') })
    }
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function removeSowField(row, idx) {
  if (!row.id) {
    sowDialog.fields.splice(idx, 1)
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认删除列「${row.label || row.key}」？删除后历史 SOW 行里该列的数据会成为游离值（不报错但不再显示）。建议改用"停用"。`,
      '提示',
      { type: 'warning' }
    )
  } catch { return }
  try {
    await sowApi.removeField(row.id)
    sowDialog.fields.splice(idx, 1)
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

// ─── 自定义信息块配置 ────────────────────────────────────────
const extraDialog = reactive({
  visible: false,
  loading: false,
  fields: [],
})

async function loadExtraFields() {
  extraDialog.loading = true
  try {
    const { data } = await customerExtraApi.listFields(true)
    extraDialog.fields = data.map((f) => ({ ...f }))
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    extraDialog.loading = false
  }
}

function addExtraField() {
  extraDialog.fields.push({
    id: null,
    key: '',
    label: '',
    sort_order: extraDialog.fields.length,
    is_active: true,
  })
}

async function saveExtraField(row, _idx) {
  const key = (row.key || '').trim()
  const label = (row.label || '').trim() || key
  if (!key) {
    ElMessage.warning('请填写 key')
    return
  }
  try {
    if (row.id) {
      const { data } = await customerExtraApi.updateField(row.id, {
        label,
        sort_order: row.sort_order || 0,
        is_active: !!row.is_active,
      })
      Object.assign(row, data)
    } else {
      const { data } = await customerExtraApi.createField({
        key,
        label,
        sort_order: row.sort_order || 0,
        is_active: !!row.is_active,
      })
      Object.assign(row, data)
    }
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function removeExtraField(row, idx) {
  if (!row.id) {
    extraDialog.fields.splice(idx, 1)
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认删除信息块「${row.label || row.key}」？所有机台下该块的文本和附件都会被删除。建议改用"停用"。`,
      '提示',
      { type: 'warning' }
    )
  } catch { return }
  try {
    await customerExtraApi.removeField(row.id)
    extraDialog.fields.splice(idx, 1)
    ElMessage.success('已删除')
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
}
.code-link {
  color: #409eff;
  font-weight: 600;
  cursor: pointer;
}
.code-link:hover {
  text-decoration: underline;
}
.muted {
  color: #c0c4cc;
}
.muted-hint {
  color: #909399;
  font-size: 12px;
}
</style>
