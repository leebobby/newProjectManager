<template>
  <div>
    <el-card shadow="never">
      <div class="toolbar">
        <el-button :icon="Refresh" @click="load">刷新</el-button>
        <el-button :icon="Download" :loading="exporting" @click="onExport">导出 PPT</el-button>
        <el-checkbox v-model="includeInactive" @change="load">显示停用</el-checkbox>
        <el-checkbox v-model="expandAll">展开全部文字</el-checkbox>
        <span class="flex-1" />
        <!-- 灯的分布摆在表头上方：一屏看不完时，先知道有没有红的 -->
        <span class="light-sum">
          <span v-for="k in LIGHT_ORDER" :key="k" class="sum-item">
            <i class="dot" :class="'dot-' + k" />{{ LIGHT_LABELS[k] }} {{ lightCount[k] }}
          </span>
        </span>
      </div>

      <el-alert
        v-if="grayCount > 0"
        type="info"
        show-icon
        :closable="false"
        class="tip"
        :title="`有 ${grayCount} 个专项一条风险都没登记，点灯显示「未评估」`"
        description="一条都没登记不等于没风险，所以不记成绿灯。到对应专项的「风险和问题」分段登一行，这里就会自动跟着变。"
      />

      <el-table
        :data="rows"
        v-loading="loading"
        border
        stripe
        row-key="id"
        style="width: 100%"
      >
        <el-table-column prop="seq" label="序号" width="64" align="center" />

        <el-table-column label="关键专题" min-width="180">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="row.kind === 'assault' ? 'danger' : 'info'">
              {{ row.kind_label }}
            </el-tag>
            <el-link type="primary" :underline="false" class="name-link" @click="openSpecial(row)">
              {{ row.name }}
            </el-link>
          </template>
        </el-table-column>

        <el-table-column label="目标" min-width="220">
          <template #default="{ row }">
            <div class="cell-text" :class="{ clamp: !expandAll }" :title="row.goal">
              {{ row.goal || '—' }}
            </div>
          </template>
        </el-table-column>

        <el-table-column label="风险" width="112" align="center">
          <template #default="{ row }">
            <!-- 灯是这张表里唯一「只属于总览」的一格（其余几列改的都是专项自己的字段）。
                 改走统一弹窗，不在行内挂下拉——一屏几十行，每行一个 popper 没必要 -->
            <button type="button" class="light-btn" :title="lightTitle(row)" @click="openLight(row)">
              <i class="dot" :class="'dot-' + row.light" />
              <span>{{ LIGHT_LABELS[row.light] }}</span>
              <i v-if="row.light_manual" class="manual-mark" title="人工指定">✎</i>
            </button>
          </template>
        </el-table-column>

        <el-table-column label="关键进展" min-width="240">
          <template #default="{ row }">
            <div class="cell-text" :class="{ clamp: !expandAll }" :title="row.progress">
              {{ row.progress || '—' }}
            </div>
            <!-- 改的是专项详情页的「整体进展」那一段本身，不是总览自己存的一列 -->
            <el-link type="primary" :underline="false" class="edit-link" @click="openProgress(row)">
              {{ row.progress ? '编辑' : '填写' }}
            </el-link>
          </template>
        </el-table-column>

        <el-table-column label="关键风险和措施" min-width="300">
          <template #default="{ row }">
            <div v-if="row.risks.length" class="risk-list">
              <div v-for="r in shownRisks(row)" :key="r.id" class="risk-item">
                <div class="risk-head">
                  <el-tag v-if="r.overdue" type="danger" size="small" effect="dark">已超期</el-tag>
                  <span class="risk-text" :class="{ clamp: !expandAll }" :title="r.content">{{ r.content || '（未填写）' }}</span>
                </div>
                <div v-if="r.progress" class="risk-act" :class="{ clamp: !expandAll }" :title="r.progress">
                  措施：{{ r.progress }}
                </div>
                <div class="risk-meta">
                  <span v-if="r.owner">{{ r.owner }}</span>
                  <span v-if="r.planned_close_date">计划闭环 {{ r.planned_close_date }}</span>
                  <!-- 改的是该专项风险分段里的那一行本身；标成 closed 之后它就不再出现在这儿了 -->
                  <el-link type="primary" :underline="false" class="edit-link" @click="openRisk(row, r)">编辑</el-link>
                </div>
              </div>
              <!-- 截断要写明另有几条，别悄悄少几行 -->
              <el-link
                v-if="row.risks.length > RISK_LIMIT && !expandAll"
                type="primary"
                :underline="false"
                class="more"
                @click="openSpecial(row)"
              >另 {{ row.risks.length - RISK_LIMIT }} 条，点开专项查看</el-link>
            </div>
            <span v-else class="muted">{{ emptyRiskText(row) }}</span>
            <div class="risk-add">
              <el-link type="primary" :underline="false" class="edit-link" @click="openRisk(row, null)">+ 新增风险</el-link>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="owner" label="责任人" width="110">
          <template #default="{ row }">{{ row.owner || '—' }}</template>
        </el-table-column>

        <template #empty>
          <el-empty description="还没有专项。建专项在「专项管理 · 专项配置」里。" />
        </template>
      </el-table>

      <div class="foot-note">
        表里七列全部从各专项自己的字段自动取：目标＝专项目标分段，关键进展＝整体进展分段，
        关键风险和措施＝风险和问题分段里<b>还没闭环</b>的行，责任人＝专项责任人。
        「关键进展」「关键风险和措施」可以直接在这儿改，但<b>改的是专项详情页里的那一段本身</b>
        ——总览没有自己的一份，所以两边永远是同一个值；改完详情页、周报、导出都跟着变。
        「风险」这一盏灯可以在本页人工指定；目标与责任人到专项里改。
      </div>
    </el-card>

    <el-dialog v-model="dialog.visible" title="风险点灯" width="460px">
      <div v-if="dialog.row" class="dlg">
        <div class="dlg-name">{{ dialog.row.kind_label }}：{{ dialog.row.name }}</div>
        <el-alert type="info" :closable="false" class="dlg-auto">
          <template #title>
            自动判定：<b>{{ LIGHT_LABELS[dialog.row.light_auto] }}</b> —— {{ dialog.row.light_reason }}
          </template>
        </el-alert>
        <el-radio-group v-model="dialog.light" class="dlg-radio">
          <el-radio value="">跟着风险行自动判（推荐）</el-radio>
          <el-radio v-for="k in LIGHT_ORDER.filter(x => x !== 'gray')" :key="k" :value="k">
            <i class="dot" :class="'dot-' + k" />人工指定为「{{ LIGHT_LABELS[k] }}」
          </el-radio>
        </el-radio-group>
        <div class="dlg-hint">
          人工指定之后这盏灯就不再跟着风险行走了——风险闭环了它也不会自己变绿。
          用完记得改回「自动判」。
        </div>
      </div>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="dialog.saving" @click="saveLight">保存</el-button>
      </template>
    </el-dialog>

    <!-- 关键进展：改的是该专项 content.progress_summary 本身（详情页的「整体进展」分段） -->
    <el-dialog v-model="progressDlg.visible" title="关键进展" width="720px" top="8vh">
      <div v-if="progressDlg.row" class="dlg-name">
        {{ progressDlg.row.kind_label }}：{{ progressDlg.row.name }}
      </div>
      <el-alert type="info" :closable="false" class="dlg-auto" show-icon
        title="这里改的就是专项详情页的「整体进展」分段"
        description="总览没有自己的一份进展文案，所以改完详情页、周报、导出看到的都是这一段。" />
      <div v-loading="progressDlg.loading">
        <RichTextEditor v-model="progressDlg.html" min-height="220px" placeholder="本周期该专项的关键进展…" />
      </div>
      <template #footer>
        <el-button @click="progressDlg.visible = false">取消</el-button>
        <el-button type="primary" :loading="progressDlg.saving" :disabled="progressDlg.loading" @click="saveProgress">
          保存
        </el-button>
      </template>
    </el-dialog>

    <!-- 风险行：表单与专项详情页共用一份（SpecialItemDialog） -->
    <SpecialItemDialog
      v-model="riskDlg.visible"
      kind="risk"
      :special-id="riskDlg.specialId"
      :item="riskDlg.item"
      @saved="load"
    />
  </div>
</template>

<script setup>
import { computed, reactive, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Download, Refresh } from '@element-plus/icons-vue'
import { specialApi, apiError, downloadBlob } from '../api'
import RichTextEditor from '../components/RichTextEditor.vue'
import SpecialItemDialog from '../components/SpecialItemDialog.vue'

// 四档灯。**与后端 enums.SPECIAL_OVERVIEW_LIGHT_LABELS 必须同步**：
// 分叉的表现是页面上多出/少掉一档，而那一档的行会显示成空白。
// gray（未评估）只可能由服务端自动推出来，所以不进人工指定的选项。
const LIGHT_ORDER = ['red', 'yellow', 'green', 'gray']
const LIGHT_LABELS = { red: '红', yellow: '黄', green: '绿', gray: '未评估' }
// 一格里最多铺几条风险。铺满会让一行有半屏高，横着扫的时候整张表就没法看了
const RISK_LIMIT = 3

const router = useRouter()
const rows = ref([])
const loading = ref(false)
const includeInactive = ref(false)
const expandAll = ref(false)

const lightCount = computed(() => {
  const c = { red: 0, yellow: 0, green: 0, gray: 0 }
  rows.value.forEach((r) => { if (c[r.light] !== undefined) c[r.light] += 1 })
  return c
})
const grayCount = computed(() => lightCount.value.gray)

function shownRisks(row) {
  return expandAll.value ? row.risks : row.risks.slice(0, RISK_LIMIT)
}

function emptyRiskText(row) {
  if (!row.risk_total) return '未登记风险'
  return `${row.risk_total} 条风险已全部闭环`
}

function lightTitle(row) {
  const base = row.light_manual
    ? `人工指定为「${LIGHT_LABELS[row.light_manual]}」（自动判定是「${LIGHT_LABELS[row.light_auto]}」）`
    : `自动判定：${row.light_reason}`
  return `${base}\n点击可修改`
}

function openSpecial(row) {
  router.push(`/specials/${row.id}`)
}

const dialog = reactive({ visible: false, row: null, light: '', saving: false })

function openLight(row) {
  dialog.row = row
  dialog.light = row.light_manual || ''
  dialog.visible = true
}

async function saveLight() {
  dialog.saving = true
  try {
    const { data } = await specialApi.setOverviewLight(dialog.row.id, dialog.light, dialog.row.version)
    // 服务端回的是这一行的最新形态（seq 除外——序号是表内位置，由本页决定）
    const i = rows.value.findIndex((r) => r.id === data.id)
    if (i >= 0) rows.value[i] = { ...data, seq: rows.value[i].seq }
    dialog.visible = false
    ElMessage.success('已保存')
  } catch (e) {
    // 409/423 由 api/index.js 的拦截器统一弹提示，这里只兜住别的错
    if (![409, 423].includes(e?.response?.status)) ElMessage.error(apiError(e, '保存失败'))
  } finally {
    dialog.saving = false
  }
}

// ── 就地编辑「关键进展」与「关键风险和措施」 ────────────────────────────
// **总览不存自己的一份**：这两处改的都是专项详情页里的那个字段本身
// （content.progress_summary / special_risks 的行），走的也是详情页那两个接口。
// 反过来做成「总览上单独填一列」的话，它就会和详情页对不上，而两边看着都对。
//
// 表里的文字是服务端剥过 HTML 的（横着扫的表留着标签每行高矮不一），
// 所以编辑时要回源拿**原始富文本**——拿页面上这份剥过的存回去，
// 等于把别人排的版一次抹平，而保存时一点提示都没有。
const progressDlg = reactive({ visible: false, row: null, html: '', version: 0, loading: false, saving: false })

async function openProgress(row) {
  progressDlg.row = row
  progressDlg.html = ''
  progressDlg.version = row.version
  progressDlg.visible = true
  progressDlg.loading = true
  try {
    const { data } = await specialApi.detail(row.id)
    progressDlg.html = data.content?.progress_summary || ''
    progressDlg.version = data.content?.version ?? row.version
  } catch (e) {
    progressDlg.visible = false
    ElMessage.error(apiError(e, '加载专项内容失败'))
  } finally {
    progressDlg.loading = false
  }
}

async function saveProgress() {
  progressDlg.saving = true
  try {
    await specialApi.updateContent(progressDlg.row.id, {
      progress_summary: progressDlg.html,
      version: progressDlg.version,
    })
    progressDlg.visible = false
    ElMessage.success('已保存')
    await load()
  } catch (e) {
    if (![409, 423].includes(e?.response?.status)) ElMessage.error(apiError(e, '保存失败'))
  } finally {
    progressDlg.saving = false
  }
}

const riskDlg = reactive({ visible: false, specialId: null, item: null })

async function openRisk(row, cell) {
  riskDlg.specialId = row.id
  if (!cell) {                 // 新增
    riskDlg.item = null
    riskDlg.visible = true
    return
  }
  // 同上：编辑已有行要回源拿原始富文本，表里那份是剥过 HTML 的
  try {
    const { data } = await specialApi.detail(row.id)
    const raw = (data.risks || []).find((x) => x.id === cell.id)
    if (!raw) { ElMessage.warning('这条风险已被他人删除，刷新后重试'); await load(); return }
    riskDlg.item = raw
    riskDlg.visible = true
  } catch (e) {
    ElMessage.error(apiError(e, '加载风险行失败'))
  }
}

const exporting = ref(false)

async function onExport() {
  exporting.value = true
  try {
    // 导出的口径跟着页面走：勾了「显示停用」，PPT 里也带上停用的那些，
    // 否则会出现"页面 6 行、导出 5 行"，而两边看着都对
    const resp = await specialApi.exportOverviewPptx(includeInactive.value)
    const ts = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19)
    downloadBlob(resp.data, `special-overview-${ts}.pptx`)
    ElMessage.success('已导出')
  } catch (e) {
    ElMessage.error(apiError(e, '导出失败'))
  } finally {
    exporting.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const { data } = await specialApi.overview(includeInactive.value)
    rows.value = data
  } catch (e) {
    ElMessage.error(apiError(e, '加载专项总览失败'))
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.flex-1 { flex: 1; }
.tip { margin-bottom: 12px; }
.light-sum { display: flex; gap: 14px; font-size: 13px; color: #606266; }
.sum-item { display: inline-flex; align-items: center; gap: 4px; }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; flex: none; }
.dot-red { background: #f56c6c; }
.dot-yellow { background: #e6a23c; }
.dot-green { background: #67c23a; }
.dot-gray { background: #c0c4cc; }
.name-link { margin-left: 6px; font-weight: 600; }
.cell-text { white-space: pre-wrap; word-break: break-word; line-height: 1.5; }
.clamp { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.light-btn {
  display: inline-flex; align-items: center; gap: 5px; cursor: pointer;
  border: 1px solid #dcdfe6; border-radius: 4px; background: #fff;
  padding: 2px 8px; font-size: 13px; color: #303133;
}
.light-btn:hover { border-color: #409eff; }
.manual-mark { font-style: normal; color: #909399; font-size: 12px; }
.risk-list { display: flex; flex-direction: column; gap: 8px; }
.risk-item { border-left: 3px solid #ebeef5; padding-left: 8px; }
.risk-head { display: flex; align-items: flex-start; gap: 6px; }
.risk-text { flex: 1; word-break: break-word; line-height: 1.5; }
.risk-act { color: #606266; font-size: 13px; margin-top: 2px; word-break: break-word; line-height: 1.5; }
.risk-meta { color: #909399; font-size: 12px; margin-top: 2px; display: flex; gap: 10px; }
.more { font-size: 12px; }
.edit-link { font-size: 12px; }
.risk-add { margin-top: 6px; }
.muted { color: #909399; }
.foot-note { margin-top: 12px; color: #909399; font-size: 12px; line-height: 1.7; }
.dlg-name { font-weight: 600; margin-bottom: 10px; }
.dlg-auto { margin-bottom: 12px; }
.dlg-radio { display: flex; flex-direction: column; gap: 10px; align-items: flex-start; }
.dlg-radio .dot { margin-right: 5px; vertical-align: middle; }
.dlg-hint { margin-top: 12px; color: #909399; font-size: 12px; line-height: 1.6; }
</style>
