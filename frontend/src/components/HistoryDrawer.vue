<template>
  <el-drawer v-model="visible" :title="title || '修订历史'" size="46%" append-to-body>
    <div class="hist-bar">
      <el-select v-model="entityFilter" size="small" clearable placeholder="全部内容"
                 style="width: 170px" @change="reload">
        <el-option v-for="e in entityOptions" :key="e.entity" :label="e.label" :value="e.entity" />
      </el-select>
      <el-select v-model="fieldFilter" size="small" clearable placeholder="全部字段"
                 style="width: 170px" :disabled="!entityFilter" @change="reload">
        <el-option v-for="f in fieldOptions" :key="f.field" :label="f.label" :value="f.field" />
      </el-select>
      <span class="hist-total">共 {{ total }} 条</span>
      <el-button size="small" text :icon="Refresh" @click="reload">刷新</el-button>
    </div>

    <el-alert v-if="!loading && !items.length" type="info" :closable="false"
              title="这里还没有修订记录"
              description="从这个版本起，每次保存都会把改之前的内容留下来；在此之前的改动没有留痕。"
              style="margin-bottom: 10px" />

    <div v-loading="loading" class="hist-list">
      <div v-for="it in items" :key="it.id" class="hist-item">
        <div class="hist-head">
          <el-tag size="small" :type="it.action === 'delete' ? 'danger' : 'info'" disable-transitions>
            {{ it.action === 'delete' ? '删除' : it.entity_label }}
          </el-tag>
          <span class="hist-field">{{ it.field_label }}</span>
          <span v-if="it.entity_title" class="hist-title" :title="it.entity_title">
            {{ it.entity_title }}
          </span>
          <span class="hist-meta">{{ it.username || '—' }} · {{ fmtDateTime(it.created_at) }}</span>
        </div>

        <template v-if="it.action === 'delete'">
          <div class="hist-side hist-old">
            <div class="hist-label">删除前的内容</div>
            <div class="hist-val"><pre>{{ prettyRow(it) }}</pre></div>
          </div>
        </template>
        <div v-else class="hist-diff">
          <div class="hist-side hist-old">
            <div class="hist-label">改之前</div>
            <div class="hist-val" v-html="it.old_html || '<span class=&quot;hist-empty&quot;>（空）</span>'" />
          </div>
          <div class="hist-side hist-new">
            <div class="hist-label">改之后</div>
            <div class="hist-val" v-html="it.new_html || '<span class=&quot;hist-empty&quot;>（空）</span>'" />
          </div>
        </div>
      </div>
    </div>

    <div v-if="items.length < total" class="hist-more">
      <el-button size="small" :loading="loading" @click="loadMore">加载更早的（还有 {{ total - items.length }} 条）</el-button>
    </div>
  </el-drawer>
</template>

<script setup>
/**
 * 修订历史抽屉：一个入口看完某个对象（或某一行）被改过什么。
 *
 * 给 scope（如 special:12）＝这个对象名下所有表的历史，按时间排在一起；
 * 给 entity + entityId ＝只看某一行。两者都不给的话服务端会 400——
 * 不设范围就是全库拉，没有使用场景。
 *
 * 富文本一律渲染服务端给的 *_html：那是过了同一份清洗函数的，
 * 直接 v-html 原始值等于把老数据里没洗过的标记也照单执行。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { apiError, historyApi } from '../api'
import { fmtDateTime } from '../utils/format'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // 归属对象，如 special:12 / domain:3 / customer:7 / hardware:0
  scope: { type: String, default: '' },
  entity: { type: String, default: '' },
  entityId: { type: [Number, null], default: null },
  title: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const PAGE = 20

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const items = ref([])
const total = ref(0)
const loading = ref(false)
const registry = ref([])
const entityFilter = ref('')
const fieldFilter = ref('')

// 按行看时不给筛选：那一行就一个实体，筛了也只有它
const entityOptions = computed(() => (props.entity ? [] : registry.value))
const fieldOptions = computed(
  () => registry.value.find((e) => e.entity === entityFilter.value)?.fields || []
)

function prettyRow(it) {
  // 删除记录存的是整行 JSON，摊成「列名：值」比一坨 JSON 好读。
  // 列名对照按**这一条自己的** entity 取，不能跟着筛选走——不筛的时候就没有对照了。
  try {
    const obj = JSON.parse(it.old_value || '{}')
    const ent = registry.value.find((e) => e.entity === it.entity)
    const labels = Object.fromEntries((ent?.fields || []).map((f) => [f.field, f.label]))
    return Object.entries(obj)
      .filter(([, v]) => String(v ?? '').trim() !== '')
      .map(([k, v]) => `${labels[k] || k}：${v}`)
      .join('\n')
  } catch {
    return it.old_value || ''
  }
}

async function fetchPage(offset) {
  const params = { limit: PAGE, offset }
  if (props.entity) {
    params.entity = props.entity
    if (props.entityId != null) params.entity_id = props.entityId
  } else {
    params.scope = props.scope
    if (entityFilter.value) params.entity = entityFilter.value
    if (fieldFilter.value) params.field = [fieldFilter.value]
  }
  const { data } = await historyApi.list(params)
  return data
}

async function reload() {
  if (!props.scope && !props.entity) return
  loading.value = true
  try {
    if (!registry.value.length) {
      const { data } = await historyApi.entities()
      registry.value = data.entities || []
    }
    const data = await fetchPage(0)
    items.value = data.items || []
    total.value = data.total || 0
  } catch (e) {
    ElMessage.error(apiError(e, '加载修订历史失败'))
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  loading.value = true
  try {
    const data = await fetchPage(items.value.length)
    items.value = items.value.concat(data.items || [])
    total.value = data.total || 0
  } catch (e) {
    ElMessage.error(apiError(e, '加载修订历史失败'))
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.modelValue, props.scope, props.entity, props.entityId],
  ([open]) => {
    if (open) {
      fieldFilter.value = ''
      reload()
    }
  }
)
</script>

<style scoped>
.hist-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.hist-total {
  margin-left: auto;
  color: #909399;
  font-size: 12px;
}
.hist-list {
  min-height: 60px;
}
.hist-item {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 8px 10px;
  margin-bottom: 10px;
}
.hist-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  margin-bottom: 6px;
}
.hist-field {
  font-weight: 600;
  color: #303133;
}
.hist-title {
  color: #606266;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.hist-meta {
  margin-left: auto;
  color: #909399;
}
.hist-diff {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.hist-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 2px;
}
.hist-val {
  border: 1px solid #ebeef5;
  border-radius: 3px;
  padding: 6px 8px;
  font-size: 13px;
  line-height: 1.6;
  max-height: 220px;
  overflow: auto;
  word-break: break-word;
}
.hist-old .hist-val {
  background: #fef6f6;
}
.hist-new .hist-val {
  background: #f4faf4;
}
.hist-val :deep(.hist-empty) {
  color: #c0c4cc;
}
.hist-val pre {
  margin: 0;
  white-space: pre-wrap;
  font-family: inherit;
}
.hist-more {
  text-align: center;
  padding: 4px 0 12px;
}
</style>
