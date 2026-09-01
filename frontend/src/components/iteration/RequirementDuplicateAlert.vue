<template>
  <!-- 一条都没重复时整条不渲染：常态是没有重复，天天挂一条绿色的"没问题"
       只会让人学会无视这块地方，真出问题那天也不会去看 -->
  <el-alert
    v-if="data && (data.same_iteration || data.cross_iteration)"
    class="dup-alert"
    type="warning"
    show-icon
    :closable="false"
  >
    <template #title>
      <span class="dup-title">{{ summary }}</span>
      <el-button link type="primary" size="small" @click="expanded = !expanded">
        {{ expanded ? '收起' : '看看是哪些' }}
      </el-button>
    </template>
    <div v-if="expanded" class="dup-list">
      <div v-for="(g, i) in data.groups" :key="i" class="dup-row">
        <el-tag size="small" :type="g.rows.length > 1 ? 'danger' : 'warning'">
          {{ g.rows.length > 1 ? '本迭代内重复' : '别的迭代也有' }}
        </el-tag>
        <span class="dup-what">
          <span v-if="g.kind === 'no'" class="dup-no">{{ g.rows[0].req_no }}</span>
          {{ g.rows[0].title || '（无标题）' }}
        </span>
        <span class="dup-where">
          本迭代序号 {{ g.rows.map((r) => r.seq || '-').join('、') }}
          <template v-if="g.others.length">
            ；另见
            <template v-for="(o, j) in g.others" :key="o.id">
              {{ j ? '、' : '' }}{{ o.iteration_label }}（序号 {{ o.seq || '-' }}）
            </template>
          </template>
        </span>
      </div>
    </div>
  </el-alert>
</template>

<script setup>
/**
 * 需求重复提示条。
 *
 * 两类重复分开说，因为处理方式完全不同：
 * - **本迭代内重复**＝真的录重了，该合并掉一条（新录入已经拦住，这里剩下的是存量）；
 * - **别的迭代也有**＝不一定是错，本轮没做完下个月接着排是正常的，但也可能是
 *   上个月录过这个月又录了一条。数据上分不出来，只有人分得出——所以摆出来，
 *   而不是替人决定。
 */
import { computed, ref } from 'vue'

const props = defineProps({
  data: { type: Object, default: null },
})

const expanded = ref(false)

const summary = computed(() => {
  const d = props.data
  if (!d) return ''
  const parts = []
  if (d.same_iteration) parts.push(`本迭代里有 ${d.same_iteration} 条需求录重了`)
  if (d.cross_iteration) parts.push(`${d.cross_iteration} 条在别的迭代里也录过`)
  return parts.join('，')
})
</script>

<style scoped>
.dup-alert {
  margin-bottom: 8px;
}
.dup-title {
  margin-right: 8px;
}
.dup-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
  max-height: 220px;
  overflow-y: auto;
}
.dup-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
  line-height: 1.6;
}
.dup-what {
  font-weight: 500;
}
.dup-no {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  margin-right: 4px;
  opacity: 0.75;
}
.dup-where {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
