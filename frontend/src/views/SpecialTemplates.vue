<template>
  <div v-if="!auth.isAdmin.value">
    <el-empty description="专项模板仅管理员可维护。" />
  </div>
  <div v-else>
    <el-card shadow="never">
      <div class="toolbar">
        <el-button type="primary" :icon="Plus" @click="openDialog()">新增模板</el-button>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
        <el-checkbox v-model="includeInactive" @change="load">显示停用</el-checkbox>
        <span class="toolbar-hint">
          模板决定专项详情页有哪些分段、各叫什么、什么顺序。
          <b>套用后与模板脱钩</b>——改模板不会动已建的专项。
        </span>
      </div>
      <el-table :data="list" v-loading="loading" border stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="模板名" min-width="150" />
        <el-table-column label="适用" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.kind === 'assault' ? 'danger' : (row.kind === 'special' ? 'info' : 'success')">
              {{ row.kind === 'assault' ? '攻关' : (row.kind === 'special' ? '专项' : '通用') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="分段" min-width="280">
          <template #default="{ row }">
            <span class="sec-chips">
              <el-tag
                v-for="s in summarize(row)"
                :key="s.key"
                size="small"
                :type="s.custom ? 'warning' : 'info'"
                effect="plain"
                class="sec-chip"
              >{{ s.title }}</el-tag>
              <span v-if="!summarize(row).length" class="muted">（未配置分段）</span>
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openDialog(row)">编辑</el-button>
            <el-button size="small" @click="onCopy(row)">复制</el-button>
            <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialog.visible"
      :title="dialog.editing ? `编辑模板：${dialog.editing.name}` : '新增模板'"
      width="900px"
      top="5vh"
    >
      <el-form :model="dialog.form" label-width="90px">
        <el-form-item label="模板名">
          <el-input v-model="dialog.form.name" placeholder="如：解决方案专项" />
        </el-form-item>
        <el-form-item label="适用类型">
          <el-radio-group v-model="dialog.form.kind">
            <el-radio value="">通用</el-radio>
            <el-radio value="special">仅专项</el-radio>
            <el-radio value="assault">仅攻关</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="dialog.form.description" placeholder="建专项时给选择者看的一句话" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="dialog.form.is_active" active-text="启用" inactive-text="停用" />
          <el-input-number v-model="dialog.form.sort_order" :min="0" size="small" style="margin-left: 16px" />
          <span class="muted" style="margin-left: 6px">排序</span>
        </el-form-item>
      </el-form>

      <el-divider content-position="left">分段与顺序</el-divider>
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 10px">
        <template #title>
          内置分段各有专属交互（里程碑时间轴、事务/风险表、阵型网格），只能改标题或整段停用；
          需要新内容就加自定义分段，四种形态：<b>表格</b> / <b>文本框</b> / <b>里程碑</b> / <b>图片</b>。
          表格的列格式选<b>点灯</b>可按取值显示红黄绿；表格与文本框都能逐格改字体、字号、颜色。
        </template>
      </el-alert>

      <div class="sec-editor">
        <div v-for="(row, i) in dialog.rows" :key="row.uid" class="sec-row" :class="{ off: !row.enabled }">
          <span class="sec-idx">{{ i + 1 }}</span>
          <el-tag size="small" :type="row.custom ? 'warning' : 'info'" class="sec-kind">
            {{ row.custom ? `自定义·${BLOCK_KIND_LABEL[row.kind] || '分段'}` : '内置' }}
          </el-tag>
          <el-input
            v-model="row.title"
            size="small"
            class="sec-title"
            :placeholder="row.defaultTitle || '分段标题'"
          />
          <el-switch v-model="row.enabled" size="small" inline-prompt active-text="显示" inactive-text="停用" />
          <el-button size="small" text :disabled="i === 0" @click="move(i, -1)">上移</el-button>
          <el-button size="small" text :disabled="i === dialog.rows.length - 1" @click="move(i, 1)">下移</el-button>
          <el-button v-if="row.custom && row.kind === 'grid'" size="small" text @click="row.expanded = !row.expanded">
            {{ row.expanded ? '收起列' : `列（${row.cols.length}）` }}
          </el-button>
          <el-button v-if="row.custom" size="small" text type="danger" @click="removeCustom(i)">删除</el-button>

          <!-- 自定义表格的列定义 -->
          <div v-if="row.custom && row.kind === 'grid' && row.expanded" class="col-editor">
            <div v-for="(c, ci) in row.cols" :key="ci" class="col-row">
              <el-input v-model="c.text" size="small" class="col-name" placeholder="列名" />
              <el-select v-model="c.type" size="small" class="col-type" @change="onColTypeChange(c)">
                <el-option v-for="t in COL_TYPE_OPTIONS" :key="t.value" :label="t.label" :value="t.value" />
              </el-select>
              <el-input
                v-if="c.type === 'select' || c.type === 'light'"
                v-model="c.options"
                size="small"
                class="col-opts"
                :placeholder="c.type === 'light' ? '点灯取值，逗号分隔' : '下拉选项，逗号分隔'"
              />
              <el-input-number v-model="c.width" :min="60" :max="600" :step="10" size="small" controls-position="right" />
              <el-button size="small" text type="danger" :disabled="row.cols.length <= 1" @click="row.cols.splice(ci, 1)">
                删列
              </el-button>
            </div>
            <div class="col-add">
              <el-button size="small" :icon="Plus" @click="addCol(row)">加一列</el-button>
              <span class="muted">预留空行</span>
              <el-input-number v-model="row.rowCount" :min="0" :max="20" size="small" controls-position="right" />
            </div>
          </div>
        </div>
      </div>

      <div class="add-bar">
        <el-dropdown trigger="click" @command="addCustom">
          <el-button :icon="Plus" type="primary" plain>新增自定义分段</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="grid">表格（可设点灯列）</el-dropdown-item>
              <el-dropdown-item command="text">文本框</el-dropdown-item>
              <el-dropdown-item command="images">图片</el-dropdown-item>
              <el-dropdown-item command="milestones">里程碑（时间轴）</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>

      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="dialog.saving" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * 专项模板（版式预设）管理页。
 *
 * 页面把后端的 layout_json（{order, config, blocks}）摊平成一个可排序的分段列表：
 * 内置分段 8 条固定存在（只能改标题 / 停用），自定义分段可增删并定义列。
 * 保存时再折回 layout_json —— order 里的自定义分段写成 tpl:<tkey>，
 * tkey 是模板内的稳定标识，套用时靠它认领已挂上的分段，重复套用才是幂等的。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { specialTemplateApi } from '../api'
import { auth } from '../store/auth'
import { LIGHT_DEFAULT_OPTIONS } from '../utils/gridLight'

const COL_TYPE_OPTIONS = [
  { value: 'text', label: '文本' },
  { value: 'select', label: '下拉' },
  { value: 'date', label: '日期' },
  { value: 'light', label: '点灯' },
]
const BLOCK_KIND_LABEL = { grid: '表格', text: '文本框', images: '图片', milestones: '里程碑' }

const list = ref([])
const builtins = ref([])       // [{key, kind, default_title}]，来自后端，避免两边分段清单漂移
const loading = ref(false)
const includeInactive = ref(true)
let _uid = 0

const dialog = reactive({
  visible: false, editing: null, saving: false,
  form: { name: '', kind: '', description: '', is_active: true, sort_order: 0 },
  rows: [],
})

async function load() {
  loading.value = true
  try {
    const { data } = await specialTemplateApi.list({ include_inactive: includeInactive.value })
    list.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

async function loadBuiltins() {
  try {
    const { data } = await specialTemplateApi.sections()
    builtins.value = data.sections || []
  } catch { builtins.value = [] }
}

function parseLayout(row) {
  try {
    const obj = JSON.parse(row?.layout_json || '{}')
    return {
      order: Array.isArray(obj.order) ? obj.order : [],
      config: obj.config && typeof obj.config === 'object' ? obj.config : {},
      blocks: Array.isArray(obj.blocks) ? obj.blocks : [],
    }
  } catch { return { order: [], config: {}, blocks: [] } }
}

/** 表格里的分段摘要：只列启用的，自定义分段标黄 */
function summarize(row) {
  const { order, config, blocks } = parseLayout(row)
  const byTkey = Object.fromEntries(blocks.map(b => [b.tkey, b]))
  const out = []
  for (const key of order) {
    if (key.startsWith('tpl:')) {
      const b = byTkey[key.slice(4)]
      if (b) out.push({ key, title: b.title || BLOCK_KIND_LABEL[b.kind] || '分段', custom: true })
    } else if (config[key]?.enabled !== false) {
      out.push({ key, title: config[key]?.title || defaultTitleOf(key), custom: false })
    }
  }
  return out
}

function defaultTitleOf(key) {
  return builtins.value.find(b => b.key === key)?.default_title || key
}

function newTkey() {
  return `t${Date.now().toString(36)}${(_uid++).toString(36)}`
}

function makeCol(text = '', type = 'text') {
  return { text, type, options: '', width: 130 }
}

function onColTypeChange(c) {
  // 切成点灯列就给一份默认红黄绿，省得建完还要手填
  if (c.type === 'light' && !c.options.trim()) c.options = LIGHT_DEFAULT_OPTIONS.join('，')
}

/** layout_json → 可编辑的行列表（内置 8 条必然在列，缺的按默认序补末尾） */
function toRows(row) {
  const { order, config, blocks } = parseLayout(row)
  const byTkey = Object.fromEntries(blocks.map(b => [b.tkey, b]))
  const rows = []
  const seen = new Set()

  const pushBuiltin = (key) => {
    seen.add(key)
    const c = config[key] || {}
    rows.push({
      uid: `u${_uid++}`, custom: false, key,
      title: String(c.title || ''), defaultTitle: defaultTitleOf(key),
      enabled: c.enabled !== false,
    })
  }
  const pushCustom = (b) => {
    const cols = (b.headers || []).map((h, i) => {
      const opts = (b.colOptions || [])[i]
      return {
        text: typeof h === 'object' ? String(h.text || '') : String(h || ''),
        type: (b.colTypes || [])[i] || 'text',
        options: Array.isArray(opts) ? opts.join('，') : '',
        width: Number((b.colWidths || [])[i]) || 130,
      }
    })
    rows.push({
      uid: `u${_uid++}`, custom: true, tkey: b.tkey || newTkey(), kind: b.kind || 'grid',
      title: String(b.title || ''), defaultTitle: BLOCK_KIND_LABEL[b.kind] || '分段',
      enabled: true, expanded: false,
      cols: cols.length ? cols : [makeCol('列1'), makeCol('列2')],
      rowCount: Number(b.row_count ?? 2),
    })
  }

  for (const key of order) {
    if (key.startsWith('tpl:')) {
      const b = byTkey[key.slice(4)]
      if (b) pushCustom(b)
    } else if (!seen.has(key)) {
      pushBuiltin(key)
    }
  }
  // order 里没提到的内置分段补在末尾（新版本新增的分段也走这条路）
  for (const b of builtins.value) if (!seen.has(b.key)) pushBuiltin(b.key)
  return rows
}

/** 可编辑的行列表 → layout_json */
function toLayout() {
  const order = []
  const config = {}
  const blocks = []
  for (const r of dialog.rows) {
    if (r.custom) {
      order.push(`tpl:${r.tkey}`)
      const block = { tkey: r.tkey, kind: r.kind, title: r.title.trim() }
      if (r.kind === 'grid') {
        block.headers = r.cols.map(c => ({ text: c.text, colspan: 1, align: 'center' }))
        block.colTypes = r.cols.map(c => c.type)
        block.colOptions = r.cols.map(c =>
          String(c.options || '').split(/[，,]/).map(s => s.trim()).filter(Boolean))
        block.colWidths = r.cols.map(c => Number(c.width) || 130)
        block.row_count = Number(r.rowCount) || 0
      }
      blocks.push(block)
    } else {
      // 停用的内置分段也写进 order：套用时它仍在顺序里，只是不显示，随时能开回来
      order.push(r.key)
      config[r.key] = { title: r.title.trim(), enabled: !!r.enabled }
    }
  }
  return JSON.stringify({ order, config, blocks })
}

function openDialog(row) {
  dialog.editing = row || null
  dialog.form = row
    ? { name: row.name, kind: row.kind || '', description: row.description || '',
        is_active: !!row.is_active, sort_order: row.sort_order || 0 }
    : { name: '', kind: '', description: '', is_active: true, sort_order: list.value.length }
  dialog.rows = toRows(row)
  dialog.visible = true
}

function onCopy(row) {
  openDialog(row)
  dialog.editing = null                       // 走新增路径
  dialog.form.name = `${row.name} 副本`
  // tkey 要换一批：否则两个模板共用 tkey，先后套到同一专项时会互相认领对方的分段
  for (const r of dialog.rows) if (r.custom) r.tkey = newTkey()
}

function move(i, dir) {
  const j = i + dir
  if (j < 0 || j >= dialog.rows.length) return
  const rows = dialog.rows
  ;[rows[i], rows[j]] = [rows[j], rows[i]]
}

function addCustom(kind) {
  dialog.rows.push({
    uid: `u${_uid++}`, custom: true, tkey: newTkey(), kind,
    title: BLOCK_KIND_LABEL[kind] || '分段', defaultTitle: BLOCK_KIND_LABEL[kind] || '分段',
    enabled: true, expanded: kind === 'grid',
    cols: [makeCol('列1'), makeCol('列2')], rowCount: 2,
  })
}

function addCol(row) {
  row.cols.push(makeCol(`列${row.cols.length + 1}`))
}

function removeCustom(i) {
  dialog.rows.splice(i, 1)
}

async function onSubmit() {
  if (!dialog.form.name.trim()) {
    ElMessage.warning('请输入模板名')
    return
  }
  const payload = { ...dialog.form, layout_json: toLayout() }
  dialog.saving = true
  try {
    if (dialog.editing) await specialTemplateApi.update(dialog.editing.id, payload)
    else await specialTemplateApi.create(payload)
    ElMessage.success('已保存')
    dialog.visible = false
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    dialog.saving = false
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除模板「${row.name}」？已套用它的专项不受影响（版式在套用时已落到各专项自己身上）。`,
      '提示', { type: 'warning' },
    )
  } catch { return }
  try {
    await specialTemplateApi.remove(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

onMounted(async () => {
  await loadBuiltins()   // 内置分段清单要先到位，toRows 才能补齐默认标题
  await load()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.toolbar-hint { font-size: 12px; color: #909399; }
.muted { font-size: 12px; color: #909399; }
.sec-chips { display: flex; flex-wrap: wrap; gap: 4px; }
.sec-chip { max-width: 160px; overflow: hidden; text-overflow: ellipsis; }

.sec-editor { display: flex; flex-direction: column; gap: 6px; }
.sec-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 6px 10px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: #fafbfc;
}
.sec-row.off { opacity: 0.55; background: #f5f6f7; }
.sec-idx {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #ecf2fb;
  color: #4073ba;
  font-size: 12px;
}
.sec-kind { flex: none; }
.sec-title { width: 200px; }

.col-editor {
  flex-basis: 100%;
  margin-top: 6px;
  padding: 8px 10px;
  background: #fff;
  border: 1px dashed #dcdfe6;
  border-radius: 4px;
}
.col-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.col-name { width: 160px; }
.col-type { width: 90px; }
.col-opts { width: 200px; }
.col-add { display: flex; align-items: center; gap: 8px; }
.add-bar { margin-top: 10px; }
</style>
