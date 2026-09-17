<template>
  <div v-if="count" class="bulk-bar">
    <span class="bulk-count">已选 <b>{{ count }}</b> 条</span>

    <!-- 版本按**两级**选：先挑大版本，再挑它底下的构建。需求行上存的是构建号
         （C10SPC101B003），而人脑子里记的是大版本——把上百个构建铺在一个下拉里，
         挑对的那个全靠肉眼扫版本号前缀 -->
    <el-select
      v-model="majorPick"
      placeholder="① 选大版本"
      size="small"
      filterable
      clearable
      style="width: 200px"
      @change="buildPick = null"
    >
      <el-option v-for="g in groups" :key="g.label" :label="g.label" :value="g.label" />
    </el-select>
    <el-select
      v-model="buildPick"
      :placeholder="majorPick ? '② 选构建号' : '先选大版本'"
      size="small"
      filterable
      clearable
      :disabled="!majorPick"
      style="width: 200px"
    >
      <el-option
        v-for="v in buildOptions"
        :key="v.id"
        :label="v.version_no"
        :value="v.version_no"
      >
        <span>{{ v.version_no }}</span>
        <span v-if="v.title" class="opt-sub">{{ v.title }}</span>
      </el-option>
    </el-select>
    <el-button
      size="small"
      type="primary"
      :disabled="!buildPick"
      :loading="busy === 'version'"
      @click="applyVersion"
    >改计划交付版本</el-button>

    <el-divider direction="vertical" />

    <el-button size="small" :loading="busy === 'move'" @click="applyMove">挪到下个月</el-button>
    <el-button size="small" text @click="emit('clear')">取消选择</el-button>

    <span class="bulk-tip">批量也走乐观锁：被别人改过的那几条会单独列出来，其余照常生效</span>
  </div>
</template>

<script setup>
/**
 * 需求列表的批量操作条，领域需求与产品需求两个 Tab 共用一份。
 *
 * 两处各写一份的表现是「在一个 Tab 挪走会重排序号、在另一个 Tab 不重排」，
 * 而两边单独看都正常（同 RequirementLinkDialog / SpecialItemDialog 的理由）。
 *
 * 结果处理也在这儿收口：后端**不整批回滚**——能改的改掉，改不动的逐条回在
 * `conflicts` 里。所以成功与失败要同时说清楚，只弹一句「保存成功」的话，
 * 人以为 12 条全改了，其实只改了 9 条。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { apiError } from '../../api'

const props = defineProps({
  /** 选中的行（要用它们的 id + version） */
  rows: { type: Array, default: () => [] },
  /** 「项目 · 大版本 · 版本」分组的迭代版本选项，由 IterationDetail 统一加载 */
  groups: { type: Array, default: () => [] },
  /** iterationRequirementApi 或 productRequirementApi */
  api: { type: Object, required: true },
  label: { type: String, default: '需求' },
})
const emit = defineEmits(['done', 'clear'])

const majorPick = ref(null)
const buildPick = ref(null)
const busy = ref('')

const count = computed(() => props.rows.length)
const buildOptions = computed(() => {
  const g = props.groups.find((x) => x.label === majorPick.value)
  return g ? g.options : []
})

// 选择被清空时把两级下拉也复位，免得下次选中几行时框里还挂着上次的版本
watch(count, (n) => { if (!n) { majorPick.value = null; buildPick.value = null } })

function payloadItems() {
  return props.rows.map((r) => ({ id: r.id, version: r.version }))
}

/** 成功与失败一起说：后端不整批回滚，只报一头都是在骗人 */
function report(data, okWord) {
  const conflicts = data.conflicts || []
  if (data.updated) {
    const moved = (data.moved_to || []).join('、')
    ElMessage.success(`${data.updated} 条已${okWord}${moved ? `（${moved}）` : ''}`)
  }
  if (conflicts.length) {
    ElMessageBox.alert(
      conflicts
        .map((c) => `序号 ${c.seq ?? '-'}、${c.title || '无标题'}：${c.reason}`)
        .join('\n'),
      `${conflicts.length} 条没改成`,
      { type: 'warning', customClass: 'bulk-conflict-box' },
    )
  }
  if (!data.updated && !conflicts.length) ElMessage.info('没有需要改的行')
}

async function applyVersion() {
  busy.value = 'version'
  try {
    const { data } = await props.api.bulk({
      items: payloadItems(), planned_version: buildPick.value,
    })
    report(data, `改到 ${buildPick.value}`)
    emit('done')
  } catch (e) {
    ElMessage.error(apiError(e, '批量改版本失败'))
  } finally {
    busy.value = ''
  }
}

async function applyMove() {
  try {
    await ElMessageBox.confirm(
      `把选中的 ${count.value} 条${props.label}挪到下个月的迭代？挪过去之后本迭代就不再统计它们。`,
      '挪到下个月', { type: 'warning' },
    )
  } catch { return }
  busy.value = 'move'
  try {
    const { data } = await props.api.bulk({ items: payloadItems(), shift_months: 1 })
    report(data, '挪走')
    emit('done')
  } catch (e) {
    ElMessage.error(apiError(e, '批量挪迭代失败'))
  } finally {
    busy.value = ''
  }
}
</script>

<style scoped>
.bulk-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
  padding: 8px 12px;
  background: #ecf5ff;
  border: 1px solid #d9ecff;
  border-radius: 4px;
}
.bulk-count { font-size: 13px; color: #409eff; }
.bulk-count b { font-size: 15px; }
.bulk-tip { margin-left: auto; font-size: 12px; color: #909399; }
.opt-sub { color: #909399; margin-left: 6px; font-size: 12px; }
</style>
