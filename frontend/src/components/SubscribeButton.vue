<template>
  <el-button
    size="small"
    :type="subscribed ? 'primary' : 'default'"
    :icon="subscribed ? BellFilled : Bell"
    :loading="loading"
    @click="onToggle"
  >
    {{ subscribed ? '已订阅' : '订阅' }}
  </el-button>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Bell, BellFilled } from '@element-plus/icons-vue'
import { notificationApi } from '../api'

const props = defineProps({
  sourceType: { type: String, required: true },
  sourceId: { type: [Number, null], required: true },
})

const subs = ref([])
const loading = ref(false)

const subscribed = computed(() =>
  subs.value.some((s) => s.source_type === props.sourceType && s.source_id === props.sourceId)
)

async function load() {
  try {
    const { data } = await notificationApi.listSubs()
    subs.value = data
  } catch {
    /* ignore */
  }
}

async function onToggle() {
  if (props.sourceId == null) {
    ElMessage.warning('目标未就绪')
    return
  }
  loading.value = true
  try {
    if (subscribed.value) {
      await notificationApi.removeSub({ source_type: props.sourceType, source_id: props.sourceId })
      ElMessage.success('已取消订阅')
    } else {
      await notificationApi.addSub({ source_type: props.sourceType, source_id: props.sourceId, events: '*' })
      ElMessage.success('已订阅')
    }
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => [props.sourceType, props.sourceId], load)
</script>
