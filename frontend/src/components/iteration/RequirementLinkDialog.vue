<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    width="760px"
    top="6vh"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <div class="link-head">
      <span class="link-self">
        <span v-if="row?.req_no" class="link-no">{{ row.req_no }}</span>
        {{ row?.title || '（无标题）' }}
      </span>
    </div>

    <el-table :data="links" size="small" empty-text="还没挂任何需求" max-height="260">
      <el-table-column label="需求编号" width="150">
        <template #default="{ row: r }">
          <a v-if="other(r).req_url" :href="other(r).req_url" target="_blank" rel="noopener">
            {{ other(r).req_no || '查看' }}
          </a>
          <span v-else>{{ other(r).req_no || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="需求标题" min-width="200">
        <template #default="{ row: r }">
          <div>{{ other(r).title || '（无标题）' }}</div>
          <div class="link-sub">
            <!-- 跨迭代不是错（本轮没做完下个月接着排），但要看得见：
                 不标的话，产品需求页上这一条看着就像是本月排的 -->
            <el-tag v-if="r.cross_iteration" size="small" type="warning">
              {{ other(r).iteration_label }} 迭代
            </el-tag>
            <!-- 只断言"不一致"，从不断言"一致"：两边有一边推不出版本时不标 -->
            <el-tag v-if="r.version_mismatch" size="small" type="danger">计划版本不一致</el-tag>
            <span v-if="other(r).owner_group">{{ other(r).owner_group }}</span>
            <span v-if="other(r).owner">{{ other(r).owner }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="进展" width="110" align="center">
        <template #default="{ row: r }">
          <el-tag v-if="other(r).changed" size="small" type="info">已变更</el-tag>
          <el-tag v-else-if="other(r).done" size="small" type="success">已完成</el-tag>
          <span v-else>{{ Math.round((other(r).completion || 0) * 100) }}%</span>
        </template>
      </el-table-column>
      <el-table-column label="拆解说明" min-width="150">
        <template #default="{ row: r }">
          <el-input
            :model-value="r.remark"
            size="small"
            placeholder="承接的是哪一部分"
            @change="(v) => saveRemark(r, v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center">
        <template #default="{ row: r }">
          <el-button link type="danger" size="small" @click="unlink(r)">解挂</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-divider content-position="left">挂上{{ otherLabel }}</el-divider>
    <div class="link-search">
      <el-input
        v-model="keyword"
        size="small"
        clearable
        placeholder="按需求编号或标题找"
        @keyup.enter="search"
        @clear="search"
      />
      <el-checkbox v-model="allIterations" size="small" @change="search">含其它迭代</el-checkbox>
      <el-button size="small" type="primary" :loading="searching" @click="search">查找</el-button>
    </div>
    <el-table :data="candidates" size="small" max-height="220"
              :empty-text="searched ? '没找到，换个关键词或勾上「含其它迭代」' : '输入关键词后点查找'">
      <el-table-column label="需求编号" width="150">
        <template #default="{ row: c }">{{ c.req_no || '—' }}</template>
      </el-table-column>
      <el-table-column label="需求标题" min-width="220">
        <template #default="{ row: c }">
          {{ c.title || '（无标题）' }}
          <el-tag v-if="c.iteration_id !== iterationId" size="small" type="warning">
            {{ c.iteration_label }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="90" align="center">
        <template #default="{ row: c }">
          <span v-if="linkedIds.has(c.id)" class="link-sub">已挂</span>
          <el-button v-else link type="primary" size="small" @click="add(c)">挂上</el-button>
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
/**
 * 一条需求的**拆解关联**管理，产品需求 Tab 与领域需求 Tab 共用一份。
 *
 * 两处各写一份表单的表现是：加一个字段（比如「拆解说明」）只加在其中一页上，
 * 另一页一保存就把它抹掉了。所以这里按 `side` 决定"当前这条在哪一侧"，
 * 表格里始终显示**对面**那一条（`other()`），两个方向共用同一套渲染。
 *
 * 关联行由父组件按迭代一次拉全后切片传进来（props.links），本组件不自己拉列表——
 * 各拉一遍的话，解挂之后父页面上的汇总数字还停在旧值。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { apiError, reqLinkApi } from '../../api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  /** 当前这条需求在哪一侧：product＝产品需求，domain＝领域需求 */
  side: { type: String, default: 'product' },
  row: { type: Object, default: null },
  iterationId: { type: Number, default: null },
  /** 这一行已有的关联（父组件从整份列表里切出来的） */
  links: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue', 'changed'])

const otherSide = computed(() => (props.side === 'product' ? 'domain' : 'product'))
const otherLabel = computed(() => (otherSide.value === 'domain' ? '领域需求' : '产品需求'))
const title = computed(() =>
  props.side === 'product' ? '领域拆解（这条产品需求由哪些领域需求承接）'
    : '关联产品需求（这条领域需求是为哪些产品需求做的）')

/** 关联行里"对面"那一条需求 */
function other(link) {
  return (otherSide.value === 'domain' ? link.domain : link.product) || {}
}

const linkedIds = computed(() => new Set(props.links.map((l) => other(l).id)))

const keyword = ref('')
const allIterations = ref(false)
const candidates = ref([])
const searching = ref(false)
const searched = ref(false)

watch(() => props.modelValue, (v) => {
  if (!v) return
  keyword.value = ''
  candidates.value = []
  searched.value = false
})

async function search() {
  if (!props.iterationId) return
  searching.value = true
  try {
    const { data } = await reqLinkApi.candidates({
      side: otherSide.value,
      iteration_id: props.iterationId,
      q: keyword.value || undefined,
      all_iterations: allIterations.value,
    })
    candidates.value = data
    searched.value = true
  } catch (e) {
    ElMessage.error(apiError(e, '查找需求失败'))
  } finally {
    searching.value = false
  }
}

async function add(c) {
  const body = props.side === 'product'
    ? { product_req_id: props.row.id, domain_req_id: c.id }
    : { product_req_id: c.id, domain_req_id: props.row.id }
  try {
    await reqLinkApi.create(body)
    ElMessage.success('已挂上')
    emit('changed')
  } catch (e) {
    ElMessage.error(apiError(e, '挂接失败'))
  }
}

async function unlink(link) {
  try {
    await reqLinkApi.remove(link.id)
    ElMessage.success('已解挂')
    emit('changed')
  } catch (e) {
    ElMessage.error(apiError(e, '解挂失败'))
  }
}

async function saveRemark(link, value) {
  try {
    await reqLinkApi.update(link.id, { remark: value ?? '' })
    emit('changed')
  } catch (e) {
    ElMessage.error(apiError(e, '保存拆解说明失败'))
  }
}
</script>

<style scoped>
.link-head {
  margin-bottom: 8px;
}
.link-self {
  font-weight: 500;
}
.link-no {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  opacity: 0.75;
  margin-right: 6px;
}
.link-sub {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.link-search {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
</style>
