<template>
  <div class="milestone-timeline">
    <div v-if="!milestones.length" class="empty">还没有里程碑，点上方"新增里程碑"开始添加</div>
    <div v-else class="track">
      <div class="line" />
      <div
        v-for="(m, i) in milestones"
        :key="i"
        class="node"
        :style="{ left: leftPercent(i) }"
        :class="['status-' + (m.status || 'planning')]"
      >
        <div class="dot" />
        <div class="label">
          <div class="name">{{ m.name }}</div>
          <div class="date">{{ m.date || '未定' }}</div>
          <div v-if="editable" class="ops">
            <el-button size="small" link @click="$emit('edit', i)">编辑</el-button>
            <el-button size="small" link type="danger" @click="$emit('remove', i)">删除</el-button>
          </div>
        </div>
      </div>
    </div>
    <div class="legend">
      <span class="lg lg-planning">未开始</span>
      <span class="lg lg-in_progress">进行中</span>
      <span class="lg lg-done">已完成</span>
      <span class="lg lg-delayed">已延期</span>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  milestones: { type: Array, default: () => [] },
  editable: { type: Boolean, default: false },
})
defineEmits(['edit', 'remove'])

function leftPercent(i) {
  const n = props.milestones.length
  if (n === 1) return '50%'
  return `${(i / (n - 1)) * 100}%`
}
</script>

<style scoped>
.milestone-timeline {
  padding: 16px 8px 8px 8px;
}
.empty {
  color: #909399;
  padding: 12px;
  text-align: center;
}
.track {
  position: relative;
  min-height: 180px;
  margin: 0 40px 8px;
}
.line {
  position: absolute;
  left: 0; right: 0; top: 30px;
  height: 2px;
  background: #dcdfe6;
}
.node {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  text-align: center;
  width: 160px;
}
.dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  margin: 24px auto 0 auto;
  border: 2px solid #fff;
  box-shadow: 0 0 0 2px #c0c4cc;
}
.status-planning .dot { background: #c0c4cc; box-shadow: 0 0 0 2px #c0c4cc; }
.status-in_progress .dot { background: #409EFF; box-shadow: 0 0 0 2px #409EFF; }
.status-done .dot { background: #67C23A; box-shadow: 0 0 0 2px #67C23A; }
.status-delayed .dot { background: #F56C6C; box-shadow: 0 0 0 2px #F56C6C; }
.label {
  margin-top: 6px;
}
.name {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.4;
}
.date {
  font-size: 12px;
  color: #909399;
}
.ops {
  margin-top: 4px;
}
.legend {
  margin-top: 12px;
  display: flex;
  gap: 16px;
  justify-content: center;
  font-size: 12px;
  color: #606266;
}
.lg::before {
  content: '';
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 4px;
  vertical-align: middle;
}
.lg-planning::before { background: #c0c4cc; }
.lg-in_progress::before { background: #409EFF; }
.lg-done::before { background: #67C23A; }
.lg-delayed::before { background: #F56C6C; }
</style>
