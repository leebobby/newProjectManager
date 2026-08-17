<template>
  <div>
    <el-card shadow="never">
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="搜索标题/说明/责任人" clearable style="width: 280px" />
        <template v-if="auth.isAdmin.value">
          <el-button type="primary" :icon="Plus" @click="openCategoryDialog()">新增分类</el-button>
          <el-button :icon="Refresh" @click="load">刷新</el-button>
        </template>
        <span v-else class="muted">仅管理员可编辑分类与条目</span>
      </div>

      <div v-if="!categories.length && !loading" class="empty">
        <el-empty description="还没有任何分类，先去新增一个吧" />
      </div>

      <div v-for="cat in filteredCategories" :key="cat.id" class="cat-block">
        <div class="cat-head">
          <span class="cat-title">{{ cat.name }}</span>
          <span class="cat-count">{{ cat.items.length }} 项</span>
          <div class="spacer" />
          <template v-if="auth.isAdmin.value">
            <el-button size="small" :icon="Plus" @click="openItemDialog(cat, null)">新增条目</el-button>
            <el-button size="small" @click="openCategoryDialog(cat)">编辑分类</el-button>
            <el-button size="small" type="danger" @click="onDeleteCategory(cat)">删除分类</el-button>
          </template>
        </div>

        <el-table :data="filterItems(cat.items)" border stripe size="small" style="width: 100%">
          <el-table-column prop="title" label="标题" min-width="220">
            <template #default="{ row }">
              <a v-if="row.kind === 'link' && row.url" :href="row.url" target="_blank" class="link">
                {{ row.title }}
              </a>
              <a v-else-if="row.kind === 'file' && row.file_path" href="javascript:void(0)" class="link" @click="onDownload(row)">
                {{ row.title }}
              </a>
              <span v-else>{{ row.title }}</span>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="90" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.kind === 'file' ? 'success' : 'info'">
                {{ row.kind === 'file' ? '文件' : '链接' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="文件 / URL" min-width="260">
            <template #default="{ row }">
              <span v-if="row.kind === 'file'">{{ row.file_name || '-' }}</span>
              <span v-else class="muted" :title="row.url">{{ row.url || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="说明" min-width="220" show-overflow-tooltip />
          <el-table-column prop="owner" label="责任人" width="120" />
          <el-table-column label="更新时间" width="170">
            <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
          </el-table-column>
          <el-table-column v-if="auth.isAdmin.value" label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openItemDialog(cat, row)">编辑</el-button>
              <el-button size="small" type="danger" @click="onDeleteItem(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-dialog v-model="catDialog.visible" :title="catDialog.editing ? '编辑分类' : '新增分类'" width="420px">
      <el-form :model="catDialog.form" label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="catDialog.form.name" maxlength="64" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="catDialog.form.sort_order" :min="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="catDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="onSubmitCategory">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="itemDialog.visible" :title="itemDialog.editing ? '编辑条目' : '新增条目'" width="560px">
      <el-form :model="itemDialog.form" label-width="80px">
        <el-form-item label="标题">
          <el-input v-model="itemDialog.form.title" maxlength="200" />
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="itemDialog.form.kind">
            <el-radio value="link">外链</el-radio>
            <el-radio value="file">文件</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="itemDialog.form.kind === 'link'" label="URL">
          <el-input v-model="itemDialog.form.url" placeholder="https://..." />
        </el-form-item>
        <el-form-item v-else label="文件">
          <el-upload
            :auto-upload="false"
            :on-change="handleSelectFile"
            :show-file-list="false"
          >
            <el-button>{{ itemDialog.form.file?.name || itemDialog.editing?.file_name || '选择文件...' }}</el-button>
            <template #tip>
              <div class="upload-tip">
                <span v-if="itemDialog.editing?.file_name && !itemDialog.form.file" class="muted">
                  当前文件：{{ itemDialog.editing.file_name }}（重新选择文件可替换）
                </span>
              </div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item label="责任人">
          <el-input v-model="itemDialog.form.owner" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="itemDialog.form.sort_order" :min="0" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="itemDialog.form.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="itemDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="itemDialog.loading" @click="onSubmitItem">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { handbookApi, downloadBlob } from '../api'
import { auth } from '../store/auth'
import { checkStorageOrWarn } from '../store/storage'

const categories = ref([])
const loading = ref(false)
const keyword = ref('')

const catDialog = reactive({ visible: false, editing: null, form: { name: '', sort_order: 0 } })
const itemDialog = reactive({
  visible: false,
  editing: null,
  category: null,
  loading: false,
  form: defaultItem(),
})

function defaultItem() {
  return {
    title: '',
    kind: 'link',
    url: '',
    description: '',
    owner: '',
    sort_order: 0,
    file: null,
  }
}

const filteredCategories = computed(() => {
  if (!keyword.value) return categories.value
  const k = keyword.value.toLowerCase()
  return categories.value
    .map(c => ({ ...c, items: c.items.filter(it => matchItem(it, k)) }))
    .filter(c => c.items.length > 0)
})

function filterItems(items) {
  if (!keyword.value) return items
  const k = keyword.value.toLowerCase()
  return items.filter(it => matchItem(it, k))
}

function matchItem(it, k) {
  return (it.title || '').toLowerCase().includes(k) ||
         (it.description || '').toLowerCase().includes(k) ||
         (it.owner || '').toLowerCase().includes(k) ||
         (it.url || '').toLowerCase().includes(k) ||
         (it.file_name || '').toLowerCase().includes(k)
}

async function load() {
  loading.value = true
  try {
    const { data } = await handbookApi.listCategories()
    categories.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

function openCategoryDialog(cat) {
  catDialog.editing = cat || null
  catDialog.form = cat
    ? { name: cat.name, sort_order: cat.sort_order || 0 }
    : { name: '', sort_order: categories.value.length }
  catDialog.visible = true
}

async function onSubmitCategory() {
  if (!catDialog.form.name.trim()) {
    ElMessage.warning('请输入分类名称')
    return
  }
  try {
    if (catDialog.editing) {
      await handbookApi.updateCategory(catDialog.editing.id, catDialog.form)
      ElMessage.success('已更新')
    } else {
      await handbookApi.createCategory(catDialog.form)
      ElMessage.success('已创建')
    }
    catDialog.visible = false
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function onDeleteCategory(cat) {
  await ElMessageBox.confirm(
    `删除分类「${cat.name}」会一并删除其下 ${cat.items.length} 个条目，确定？`,
    '提示', { type: 'warning' }
  )
  try {
    await handbookApi.removeCategory(cat.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

function openItemDialog(cat, item) {
  itemDialog.category = cat
  itemDialog.editing = item || null
  itemDialog.form = item
    ? {
        title: item.title,
        kind: item.kind,
        url: item.url || '',
        description: item.description || '',
        owner: item.owner || '',
        sort_order: item.sort_order || 0,
        file: null,
      }
    : { ...defaultItem(), sort_order: cat.items.length }
  itemDialog.visible = true
  // 打开时检查一次磁盘空间，低于 10GB 自动弹 warning
  checkStorageOrWarn()
}

// el-upload 在 auto-upload=false 时通过 on-change 派发；
// uploadFile.raw 才是原始的 File 对象（FormData 需要这个）。
function handleSelectFile(uploadFile) {
  itemDialog.form.file = uploadFile?.raw || uploadFile
}

async function onSubmitItem() {
  const f = itemDialog.form
  if (!f.title.trim()) {
    ElMessage.warning('请输入标题')
    return
  }
  if (f.kind === 'link' && !f.url.trim()) {
    ElMessage.warning('外链类型需要填写 URL')
    return
  }
  if (f.kind === 'file' && !itemDialog.editing && !f.file) {
    ElMessage.warning('请选择要上传的文件')
    return
  }
  const fd = new FormData()
  if (!itemDialog.editing) fd.append('category_id', itemDialog.category.id)
  fd.append('title', f.title)
  fd.append('kind', f.kind)
  fd.append('url', f.url || '')
  fd.append('description', f.description || '')
  fd.append('owner', f.owner || '')
  fd.append('sort_order', String(f.sort_order || 0))
  if (f.file) fd.append('file', f.file)

  itemDialog.loading = true
  try {
    if (itemDialog.editing) {
      await handbookApi.updateItem(itemDialog.editing.id, fd)
      ElMessage.success('已更新')
    } else {
      await handbookApi.createItem(fd)
      ElMessage.success('已创建')
    }
    itemDialog.visible = false
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    itemDialog.loading = false
  }
}

async function onDeleteItem(row) {
  await ElMessageBox.confirm(`确认删除条目「${row.title}」？`, '提示', { type: 'warning' })
  try {
    await handbookApi.removeItem(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

async function onDownload(row) {
  try {
    const { data } = await handbookApi.download(row.id)
    downloadBlob(data, row.file_name || row.title)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '下载失败')
  }
}

function formatTime(d) {
  if (!d) return ''
  return new Date(d).toLocaleString()
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar .muted {
  color: #909399;
  font-size: 13px;
}
.cat-block {
  margin-bottom: 24px;
}
.cat-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 0 10px 0;
  border-bottom: 1px solid #ebeef5;
  margin-bottom: 10px;
}
.cat-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
.cat-count {
  color: #909399;
  font-size: 13px;
}
.cat-head .spacer { flex: 1; }
.link {
  color: #409EFF;
  text-decoration: none;
}
.link:hover {
  text-decoration: underline;
}
.muted {
  color: #909399;
}
.empty {
  padding: 24px 0;
}
.upload-tip {
  font-size: 12px;
}
</style>
