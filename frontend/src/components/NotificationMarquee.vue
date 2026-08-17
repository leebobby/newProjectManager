<template>
  <div v-if="visibleItems.length" class="marquee-bar">
    <el-icon class="marquee-icon"><Promotion /></el-icon>
    <div class="marquee-viewport" @mouseenter="paused = true" @mouseleave="paused = false">
      <div
        class="marquee-track"
        :class="{ paused, scroll: shouldScroll }"
        :style="{ animationDuration: duration + 's' }"
      >
        <!-- 条目多时复制一遍做无缝滚动；条目少时静止左对齐，避免只剩一小条看不清 -->
        <span
          v-for="(n, i) in displayItems"
          :key="i"
          class="marquee-item"
          :class="{ unread: !n.is_read }"
          @click="onClick(n)"
        >
          <el-tag size="small" :type="kindType(n.kind)" effect="plain" class="m-tag">{{ kindLabel(n.kind) }}</el-tag>
          {{ n.title }}
          <span class="dot">·</span>
        </span>
      </div>
    </div>
    <el-button class="marquee-close" link :icon="Close" title="关闭跑马灯" @click="dismiss" />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Close, Promotion } from '@element-plus/icons-vue'
import { notificationApi } from '../api'
import { auth } from '../store/auth'

const router = useRouter()
const items = ref([])
const paused = ref(false)
const dismissed = ref(sessionStorage.getItem('marqueeDismissed') === '1')
let pollHandle = null

const KIND_LABEL = {
  assignment: '指派', status_change: '状态变更', mention: '@提到',
  due_soon: '临期', overdue: '已逾期', version_plan: '版本计划',
  broadcast: '广播', system: '系统',
}
function kindLabel(k) { return KIND_LABEL[k] || k }
function kindType(k) {
  if (k === 'overdue') return 'danger'
  if (k === 'due_soon') return 'warning'
  if (k === 'broadcast') return 'success'
  if (k === 'assignment' || k === 'mention') return 'primary'
  return 'info'
}

const visibleItems = computed(() => (dismissed.value ? [] : items.value))
// 条目较多才滚动；少于 5 条静止展示，避免内容被压成一小条、看不清
const shouldScroll = computed(() => visibleItems.value.length >= 5)
const loopItems = computed(() => [...visibleItems.value, ...visibleItems.value])
const displayItems = computed(() => (shouldScroll.value ? loopItems.value : visibleItems.value))
// 放慢滚动：单条约 8s，最少 30s 跑完一圈
const duration = computed(() => Math.max(30, visibleItems.value.length * 8))

async function load() {
  if (!auth.isLoggedIn.value || dismissed.value) {
    items.value = []
    return
  }
  try {
    const { data } = await notificationApi.list({ only_unread: true, limit: 20 })
    items.value = data.items || []
  } catch {
    /* 静默：跑马灯不阻塞 */
  }
}

async function onClick(n) {
  if (!n.is_read) {
    try {
      await notificationApi.markRead(n.id)
      n.is_read = true
    } catch { /* ignore */ }
  }
  if (n.link) {
    try { router.push(n.link) } catch { /* invalid link */ }
  }
}

function dismiss() {
  dismissed.value = true
  sessionStorage.setItem('marqueeDismissed', '1')
}

onMounted(() => {
  load()
  pollHandle = setInterval(load, 60 * 1000)
})
onBeforeUnmount(() => {
  if (pollHandle) clearInterval(pollHandle)
})

defineExpose({ reload: load })
</script>

<style scoped>
.marquee-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 40px;
  /* 固定高度且不被兄弟（如很高的页面内容）挤压——否则整条会被压扁看不清字 */
  flex-shrink: 0;
  min-height: 40px;
  padding: 0 14px;
  background: #fff7e6;
  border-bottom: 1px solid #ffe7ba;
  overflow: hidden;
}
.marquee-icon { color: #e6a23c; flex-shrink: 0; font-size: 17px; }
.marquee-viewport {
  flex: 1;
  overflow: hidden;
  white-space: nowrap;
}
.marquee-track {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  will-change: transform;
}
/* 条目多时才滚动；少时静止左对齐 */
.marquee-track.scroll { animation: marquee linear infinite; }
.marquee-track.paused { animation-play-state: paused; }
@keyframes marquee {
  from { transform: translateX(0); }
  to { transform: translateX(-50%); }
}
.marquee-item {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 14px;
  color: #8c6d3f;
  cursor: pointer;
  padding: 0 6px;
}
.marquee-item.unread { color: #d48806; font-weight: 500; }
.marquee-item:hover { text-decoration: underline; }
.marquee-item .m-tag { flex-shrink: 0; }
.marquee-item .dot { color: #d9b48a; margin-left: 8px; }
.marquee-close {
  flex-shrink: 0;
  color: #c0a06a;
  padding: 0 4px;
}
.marquee-close:hover { color: #e6a23c; }
</style>
