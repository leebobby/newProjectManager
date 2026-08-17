<template>
  <div class="cl-cell">
    <!-- 无可见条目 -->
    <template v-if="!visible.length">
      <div class="cl-compact-line">
        <span class="cl-empty">—</span>
        <button v-if="editMode" class="cl-add-btn-mini" type="button" title="新增条目" @click.stop="startAdd">＋</button>
        <span v-if="doneCount" class="cl-done-badge" @click.stop="expandDone = !expandDone">
          已完成 {{ doneCount }}
        </span>
      </div>
    </template>

    <!-- 精简模式：只显第一条 -->
    <template v-else-if="compact">
      <div class="cl-compact-line">
        <label class="cl-item" :class="{ ro: !editMode }" @click.prevent="editMode && toggle(visible[0])">
          <span class="cl-box" :class="boxClass(visible[0])">
            <svg v-if="visible[0].status === 'CLOSED'" class="cl-check-svg" viewBox="0 0 10 8" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1,4 4,7 9,1"/></svg>
          </span>
          <span class="cl-text" :class="textClass(visible[0])" @click.stop="$emit('open', visible[0])">
            {{ visible[0].description }}
          </span>
        </label>
        <span v-if="visible.length > 1" class="cl-more">+{{ visible.length - 1 }}</span>
        <button v-if="editMode" class="cl-add-btn-mini" type="button" title="新增条目" @click.stop="startAdd">＋</button>
        <span v-if="doneCount && !showCompleted" class="cl-done-badge" @click.stop="expandDone = !expandDone">
          已完成 {{ doneCount }}
        </span>
      </div>
    </template>

    <!-- 详细模式：全部展开 -->
    <template v-else>
      <div v-for="item in visible" :key="item.id" class="cl-line">
        <label class="cl-item" :class="{ ro: !editMode }" @click.prevent="editMode && toggle(item)">
          <span class="cl-box" :class="boxClass(item)">
            <svg v-if="item.status === 'CLOSED'" class="cl-check-svg" viewBox="0 0 10 8" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1,4 4,7 9,1"/></svg>
          </span>
          <span class="cl-text" :class="textClass(item)" title="点击查看跟踪详情" @click.stop="$emit('open', item)">
            {{ item.description }}
          </span>
        </label>
        <!-- 元信息：问题看紧急度/责任人，事务只看预计时间 -->
        <div class="cl-meta">
          <span v-if="item.kind === 'demand'" class="cl-tag u-demand">需求</span>
          <span v-if="kind === 'issue' && item.urgency && item.urgency !== '一般'"
                class="cl-tag" :class="item.urgency === '重要紧急' ? 'u-crit' : 'u-urg'">{{ item.urgency }}</span>
          <span v-if="item.status === '挂起'" class="cl-tag u-hold">挂起</span>
          <span v-if="kind === 'issue' && item.owner_display" class="cl-mini">{{ item.owner_display }}</span>
          <span v-if="item.due_date" class="cl-mini" :class="{ 'is-overdue': item.overdue }">
            {{ item.overdue ? '逾期 ' : '' }}{{ item.due_date }}
          </span>
          <span v-if="kind === 'issue' && item.issue_ref" class="cl-mini ref">#{{ item.issue_ref }}</span>
          <button v-if="editMode && isAdmin" class="cl-del" type="button" @click.stop="remove(item)">×</button>
        </div>
      </div>

      <div class="cl-progress-wrap">
        <div class="cl-bar"><div class="cl-fill" :style="{ width: pct + '%' }" /></div>
        <span class="cl-pct-text">{{ doneCount }}/{{ items.length }}</span>
        <span v-if="doneCount && !showCompleted" class="cl-done-badge" @click.stop="expandDone = !expandDone">
          {{ expandDone ? '收起已完成' : `已完成 ${doneCount}` }}
        </span>
      </div>
      <button v-if="editMode" class="cl-add-btn" type="button" @click.stop="startAdd">＋ 新增</button>
    </template>

    <!-- 快速新增：只填一句话，其余字段走默认值，细节到跟踪表里补 -->
    <div v-if="adding" class="cl-add-row">
      <input ref="addInput" v-model="addText" class="cl-add-input"
             :placeholder="kind === 'issue' ? '输入内容…（「需求:」开头记为需求，其余记为问题）' : '输入任务内容…'"
             @keydown.enter.prevent="confirmAdd" @keydown.esc="cancelAdd" />
      <button class="cl-btn-ok" type="button" @click="confirmAdd">确认</button>
      <button class="cl-btn-no" type="button" @click="cancelAdd">取消</button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { customerIssueApi } from '../api'

const props = defineProps({
  items: { type: Array, default: () => [] },   // 该机台该 kind 的全部条目
  kind: { type: String, default: 'issue' },    // issue | task
  machineStatusId: { type: Number, required: true },
  editMode: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
  showCompleted: { type: Boolean, default: false },  // 顶部全局开关
  isAdmin: { type: Boolean, default: false },
})
const emit = defineEmits(['refresh', 'open'])

// 已完成默认藏起来；全局开关或本格展开都能让它现身
const expandDone = ref(false)
const visible = computed(() => {
  if (props.showCompleted || expandDone.value) return props.items
  return props.items.filter((i) => i.status !== 'CLOSED')
})
const doneCount = computed(() => props.items.filter((i) => i.status === 'CLOSED').length)
const pct = computed(() => (props.items.length ? Math.round((doneCount.value / props.items.length) * 100) : 0))

function boxClass(item) {
  return { checked: item.status === 'CLOSED', hold: item.status === '挂起' }
}
function textClass(item) {
  return { done: item.status === 'CLOSED', hold: item.status === '挂起' }
}

// 勾选＝在 OPEN / CLOSED 之间切；挂起的勾一下直接置为已闭环
async function toggle(item) {
  const next = item.status === 'CLOSED' ? 'OPEN' : 'CLOSED'
  try {
    await customerIssueApi.update(item.id, { version: item.version, status: next })
    emit('refresh')
  } catch (e) {
    if (e.response?.status !== 409) ElMessage.error(e.response?.data?.detail || '保存失败')
    else emit('refresh')
  }
}

async function remove(item) {
  try {
    await customerIssueApi.remove(item.id)
    emit('refresh')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

const adding = ref(false)
const addText = ref('')
const addInput = ref(null)

async function startAdd() {
  adding.value = true
  addText.value = ''
  await nextTick()
  addInput.value?.focus()
}
function cancelAdd() {
  adding.value = false
  addText.value = ''
}
async function confirmAdd() {
  const text = addText.value.trim()
  if (!text) { cancelAdd(); return }
  // 问题栏支持前缀分流：「需求:」开头记为需求，「问题:」开头或无前缀记为问题（前缀本身不入库）
  let kind = props.kind
  let description = text
  if (props.kind === 'issue') {
    if (/^需求[:：]/.test(text)) {
      kind = 'demand'
      description = text.replace(/^需求[:：]\s*/, '')
    } else if (/^问题[:：]/.test(text)) {
      description = text.replace(/^问题[:：]\s*/, '')
    }
    if (!description) { ElMessage.warning('前缀后面要有内容'); return }
  }
  try {
    await customerIssueApi.create({
      machine_status_id: props.machineStatusId,
      kind,
      description,
    })
    cancelAdd()
    emit('refresh')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '新增失败')
  }
}
</script>

<style scoped>
.cl-cell { display: flex; flex-direction: column; gap: 2px; }
.cl-compact-line { display: flex; align-items: center; gap: 6px; min-height: 22px; }
.cl-line { display: flex; align-items: flex-start; gap: 6px; flex-wrap: wrap; }
.cl-empty { color: #c0c4cc; }

.cl-item { display: flex; align-items: flex-start; gap: 6px; cursor: pointer; flex: 1 1 auto; min-width: 0; }
.cl-item.ro { cursor: default; }

.cl-box {
  flex: 0 0 14px; width: 14px; height: 14px; margin-top: 3px;
  border: 1.5px solid #c0c4cc; border-radius: 3px; background: #fff;
  display: inline-flex; align-items: center; justify-content: center; transition: all .15s;
}
.cl-box.checked { background: #67c23a; border-color: #67c23a; }
.cl-box.hold { border-color: #e6a23c; background: #fdf6ec; }
.cl-check-svg { width: 9px; height: 7px; }

.cl-text { font-size: 13px; color: #1f2329; line-height: 1.5; word-break: break-word; }
.cl-text:hover { color: #409eff; text-decoration: underline; }
.cl-text.done { color: #a8abb2; text-decoration: line-through; }
.cl-text.hold { color: #b88230; }

.cl-more { color: #909399; font-size: 12px; flex: 0 0 auto; }

/* 已完成折叠角标 */
.cl-done-badge {
  flex: 0 0 auto; font-size: 11px; color: #909399; cursor: pointer;
  background: #f4f4f5; border-radius: 9px; padding: 1px 7px; user-select: none;
}
.cl-done-badge:hover { background: #e9e9eb; color: #606266; }

/* 条目元信息 */
.cl-meta { display: flex; align-items: center; gap: 5px; flex: 0 0 auto; padding-left: 20px; }
.cl-tag { font-size: 11px; border-radius: 3px; padding: 0 5px; line-height: 16px; }
.u-crit { background: #fef0f0; color: #f56c6c; }
.u-urg { background: #fdf6ec; color: #e6a23c; }
.u-hold { background: #f4f4f5; color: #909399; }
.u-demand { background: #ecf5ff; color: #409eff; }
.cl-mini { font-size: 11px; color: #909399; }
.cl-mini.ref { color: #409eff; }
.cl-mini.is-overdue { color: #f56c6c; font-weight: 600; }

.cl-del {
  border: none; background: transparent; color: #c0c4cc; cursor: pointer;
  font-size: 15px; line-height: 1; padding: 0 2px;
}
.cl-del:hover { color: #f56c6c; }

.cl-progress-wrap { display: flex; align-items: center; gap: 6px; margin-top: 4px; }
.cl-bar { flex: 1 1 auto; height: 4px; background: #ebeef5; border-radius: 2px; overflow: hidden; }
.cl-fill { height: 100%; background: #67c23a; transition: width .3s; }
.cl-pct-text { font-size: 11px; color: #909399; flex: 0 0 auto; }

.cl-add-btn, .cl-add-btn-mini {
  border: 1px dashed #c0c4cc; background: transparent; color: #909399;
  border-radius: 4px; cursor: pointer; font-size: 12px;
}
.cl-add-btn { margin-top: 4px; padding: 2px 8px; align-self: flex-start; }
.cl-add-btn-mini { flex: 0 0 auto; width: 18px; height: 18px; line-height: 1; padding: 0; }
.cl-add-btn:hover, .cl-add-btn-mini:hover { border-color: #409eff; color: #409eff; }

.cl-add-row { display: flex; align-items: center; gap: 4px; margin-top: 4px; }
.cl-add-input {
  flex: 1 1 auto; min-width: 0; border: 1px solid #dcdfe6; border-radius: 4px;
  padding: 3px 6px; font-size: 12px; outline: none;
}
.cl-add-input:focus { border-color: #409eff; }
.cl-btn-ok, .cl-btn-no {
  border: none; border-radius: 4px; padding: 3px 8px; font-size: 12px; cursor: pointer;
}
.cl-btn-ok { background: #409eff; color: #fff; }
.cl-btn-no { background: #f4f4f5; color: #606266; }
</style>
