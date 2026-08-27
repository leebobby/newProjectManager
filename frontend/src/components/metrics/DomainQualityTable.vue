<template>
  <!-- 版本质量与领域质量共用这一张表：两边各写一份的话，同一批字段会长出两套列名，
       口径也会慢慢分叉。差别只有「采集问题单」两列——只有版本口径能按「版本信息」
       精确匹配，迭代口径下快照没有迭代维度（它是"当天还开着的单"）。 -->
  <el-table :data="rows" v-loading="loading" border stripe size="small" show-summary
    :summary-method="summary">
    <el-table-column label="领域" min-width="160" fixed>
      <template #default="{ row }">
        <span :class="{ muted: row.group_id === null }">{{ row.group_name }}</span>
        <el-tooltip v-if="row.group_id === null" placement="top"
          content="这些需求还没填 PL 组。它们不属于任何领域，最该被捞出来补录——藏起来就永远没人去补">
          <el-icon class="hdr-help"><QuestionFilled /></el-icon>
        </el-tooltip>
      </template>
    </el-table-column>
    <el-table-column label="需求数" width="90" align="right">
      <template #default="{ row }">{{ row.total }}</template>
    </el-table-column>
    <el-table-column label="已完成" width="90" align="right">
      <template #default="{ row }">{{ row.done }}</template>
    </el-table-column>
    <el-table-column label="平均完成度" width="150">
      <template #default="{ row }">
        <el-progress :percentage="Math.round(row.avg_completion * 100)" :stroke-width="12" />
      </template>
    </el-table-column>
    <el-table-column label="代码量(行)" width="115" align="right">
      <template #default="{ row }">{{ row.code_volume.toLocaleString() }}</template>
    </el-table-column>
    <el-table-column label="自验证用例" width="105" align="right">
      <template #default="{ row }">{{ row.self_test_cases }}</template>
    </el-table-column>
    <el-table-column label="用例密度" width="105" align="right">
      <template #header>
        用例密度
        <el-tooltip placement="top" content="个/kloc = 用例数 ÷ (代码量/1000)；代码量为空时不计算，显示 —">
          <el-icon class="hdr-help"><QuestionFilled /></el-icon>
        </el-tooltip>
      </template>
      <template #default="{ row }">
        <span :class="row.code_volume ? '' : 'muted'">
          {{ row.code_volume ? row.self_test_case_density : '—' }}
        </span>
      </template>
    </el-table-column>
    <el-table-column label="转测后问题单" width="120" align="right">
      <template #default="{ row }">{{ row.post_test_issues }}</template>
    </el-table-column>
    <el-table-column label="问题单密度" width="115" align="right">
      <template #default="{ row }">
        <span :class="row.code_volume ? '' : 'muted'">
          {{ row.code_volume ? row.post_test_issue_density : '—' }}
        </span>
      </template>
    </el-table-column>
    <template v-if="showSnapshot">
      <el-table-column label="采集问题单" width="110" align="right">
        <template #header>
          采集问题单
          <el-tooltip placement="top"
            content="问题单管理最新一次采集里、「版本信息」命中本版本且责任人属于该领域的条数。命中率见表上方的提示">
            <el-icon class="hdr-help"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <!-- 未指定领域那行没法按组切问题单：留空而不是记 0——
               0 会被读成"这个领域没问题单"，留空才是"这一格算不出来" -->
          <span v-if="row.snapshot_issues === null" class="muted">—</span>
          <span v-else>{{ row.snapshot_issues }}</span>
        </template>
      </el-table-column>
      <el-table-column label="加权分" width="95" align="right">
        <template #header>
          加权分
          <el-tooltip placement="top" content="致命 10 分 / 严重 3 分 / 一般 1 分 / 提示 0.1 分">
            <el-icon class="hdr-help"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span v-if="row.snapshot_score === null" class="muted">—</span>
          <span v-else class="danger">{{ row.snapshot_score }}</span>
        </template>
      </el-table-column>
    </template>
  </el-table>
</template>

<script setup>
import { QuestionFilled } from '@element-plus/icons-vue'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  // 采集问题单两列：只有版本口径填得出来
  showSnapshot: { type: Boolean, default: false },
})

// 合计行：能相加的列才加。密度是比值，**逐行相加没有意义**——
// 合计的密度必须用「合计用例数 ÷ 合计代码量」重算，直接把各行密度加起来
// 会得到一个大得离谱的数，而且看着还挺像个数。
function summary({ columns }) {
  const rows = props.rows
  const sum = (k) => rows.reduce((s, r) => s + (r[k] || 0), 0)
  const cv = sum('code_volume')
  const perKloc = (n) => (cv ? Math.round((n / (cv / 1000)) * 100) / 100 : '—')
  return columns.map((col, i) => {
    if (i === 0) return '合计'
    switch (col.label) {
      case '需求数': return sum('total')
      case '已完成': return sum('done')
      case '代码量(行)': return cv.toLocaleString()
      case '自验证用例': return sum('self_test_cases')
      case '用例密度': return perKloc(sum('self_test_cases'))
      case '转测后问题单': return sum('post_test_issues')
      case '问题单密度': return perKloc(sum('post_test_issues'))
      case '采集问题单': return sum('snapshot_issues')
      case '加权分': return Math.round(sum('snapshot_score') * 10) / 10
      default: return ''      // 平均完成度：进度条列不填合计，各行权重不同，简单平均会误导
    }
  })
}
</script>

<style scoped>
.muted { color: #c0c4cc; }
.danger { color: #f56c6c; }
.hdr-help { color: #909399; vertical-align: -2px; margin-left: 2px; }
</style>
