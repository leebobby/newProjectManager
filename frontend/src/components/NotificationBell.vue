<template>
  <div class="notif-wrap">
    <el-badge :value="unread" :max="99" :hidden="!unread" type="danger">
      <el-button :icon="Bell" circle text @click="open" />
    </el-badge>

    <el-drawer
      v-model="visible"
      title="通知中心"
      direction="rtl"
      size="420px"
      :before-close="onClose"
    >
      <template #header>
        <div class="drawer-header">
          <span>通知中心</span>
          <div>
            <el-button v-if="isAdmin" size="small" :icon="Promotion" @click="openBroadcast">广播</el-button>
            <el-button size="small" @click="onMarkAllRead" :disabled="!unread">全部已读</el-button>
            <el-button size="small" :icon="Refresh" @click="loadList" />
          </div>
        </div>
      </template>

      <el-radio-group v-model="filter" size="small" @change="loadList" style="margin-bottom: 8px">
        <el-radio-button :value="false">全部</el-radio-button>
        <el-radio-button :value="true">未读</el-radio-button>
      </el-radio-group>

      <el-empty v-if="!items.length && !loading" description="暂无通知" />

      <div v-loading="loading" class="notif-list">
        <div
          v-for="n in items"
          :key="n.id"
          class="notif-item"
          :class="{ unread: !n.is_read }"
          @click="onClickItem(n)"
        >
          <div class="row1">
            <el-tag size="small" :type="kindType(n.kind)" effect="plain">{{ kindLabel(n.kind) }}</el-tag>
            <span v-if="n.is_broadcast" class="broadcast">广播</span>
            <span class="time">{{ relTime(n.created_at) }}</span>
          </div>
          <div class="title">{{ n.title }}</div>
          <div v-if="n.body" class="body">{{ n.body }}</div>
          <div v-if="n.actor_name" class="actor">— {{ n.actor_name }}</div>
        </div>
      </div>
    </el-drawer>

    <!-- 广播弹窗 -->
    <el-dialog v-model="broadcast.visible" title="发布广播" width="500px">
      <el-form :model="broadcast.form" label-width="80px">
        <el-form-item label="标题">
          <el-input v-model="broadcast.form.title" placeholder="如：v2.4 版本计划变更" />
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="broadcast.form.body" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="跳转链接">
          <el-input v-model="broadcast.form.link" placeholder="可选；如 /roadmaps" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="broadcast.visible = false">取消</el-button>
        <el-button type="primary" @click="submitBroadcast">发送</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Bell, Promotion, Refresh } from '@element-plus/icons-vue'
import { notificationApi } from '../api'
import { auth } from '../store/auth'

const router = useRouter()
const isAdmin = computed(() => auth.isAdmin.value)

const visible = ref(false)
const loading = ref(false)
const filter = ref(false)
const items = ref([])
const unread = ref(0)
let pollHandle = null

const KIND_LABEL = {
  assignment: '指派',
  status_change: '状态变更',
  mention: '@提到',
  due_soon: '临期',
  overdue: '已逾期',
  version_plan: '版本计划',
  broadcast: '广播',
  system: '系统',
}
function kindLabel(k) { return KIND_LABEL[k] || k }
function kindType(k) {
  if (k === 'overdue') return 'danger'
  if (k === 'due_soon') return 'warning'
  if (k === 'broadcast') return 'success'
  if (k === 'assignment' || k === 'mention') return 'primary'
  return 'info'
}

function relTime(s) {
  if (!s) return ''
  const t = new Date(s)
  const diff = Math.floor((Date.now() - t.getTime()) / 1000)
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 7 * 86400) return `${Math.floor(diff / 86400)} 天前`
  return t.toLocaleString()
}

async function loadUnread() {
  if (!auth.isLoggedIn.value) {
    unread.value = 0
    return
  }
  try {
    const { data } = await notificationApi.unreadCount()
    unread.value = data.unread || 0
  } catch {
    /* ignore */
  }
}

async function loadList() {
  loading.value = true
  try {
    const { data } = await notificationApi.list({ only_unread: filter.value, limit: 50 })
    items.value = data.items
    unread.value = data.unread_count
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

function open() {
  visible.value = true
  loadList()
}

function onClose(done) {
  done()
}

async function onClickItem(n) {
  if (!n.is_read) {
    try {
      await notificationApi.markRead(n.id)
      n.is_read = true
      unread.value = Math.max(0, unread.value - 1)
    } catch {
      /* ignore */
    }
  }
  if (n.link) {
    visible.value = false
    try { router.push(n.link) } catch { /* invalid */ }
  }
}

async function onMarkAllRead() {
  try {
    await notificationApi.markAllRead()
    ElMessage.success('已全部标记为已读')
    await loadList()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

// ─── 广播 ────────────────────────────────────────
const broadcast = reactive({
  visible: false,
  form: { title: '', body: '', link: '' },
})
function openBroadcast() {
  broadcast.form = { title: '', body: '', link: '' }
  broadcast.visible = true
}
async function submitBroadcast() {
  if (!broadcast.form.title.trim()) {
    ElMessage.warning('标题必填')
    return
  }
  try {
    await notificationApi.broadcast(broadcast.form)
    ElMessage.success('已广播')
    broadcast.visible = false
    await loadList()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '发送失败')
  }
}

// ─── 轮询 ────────────────────────────────────────
onMounted(() => {
  loadUnread()
  // 30 秒轮询一次未读数
  pollHandle = setInterval(loadUnread, 30 * 1000)
})

onBeforeUnmount(() => {
  if (pollHandle) clearInterval(pollHandle)
})
</script>

<style scoped>
.notif-wrap { display: inline-flex; align-items: center; margin-right: 8px; }
.drawer-header { display: flex; justify-content: space-between; align-items: center; }
.notif-list { display: flex; flex-direction: column; gap: 6px; }
.notif-item {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 8px 10px;
  cursor: pointer;
  background: #fafafa;
  transition: all 0.15s;
}
.notif-item:hover { border-color: #409eff; }
.notif-item.unread { background: #ecf5ff; border-color: #b3d8ff; }
.row1 { display: flex; align-items: center; gap: 6px; }
.row1 .time { margin-left: auto; font-size: 12px; color: #909399; }
.row1 .broadcast { color: #67c23a; font-size: 12px; font-weight: 600; }
.notif-item .title { font-weight: 500; color: #303133; margin-top: 4px; }
.notif-item .body { color: #606266; font-size: 13px; margin-top: 2px; white-space: pre-wrap; }
.notif-item .actor { color: #909399; font-size: 12px; margin-top: 4px; }
</style>
