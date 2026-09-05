<template>
  <el-button :link="link" :type="link ? 'primary' : ''" size="small"
             :icon="link ? undefined : Clock" @click="open = true">
    {{ label || (link ? '历史' : '修订历史') }}
  </el-button>
  <el-button v-if="kind" :link="link" :type="link ? 'primary' : ''" size="small"
             :icon="link ? undefined : Camera" :loading="saving" @click="archiveNow">
    {{ link ? '存档' : '存一份档' }}
  </el-button>
  <HistoryDrawer v-model="open" :scope="scope" :entity="entity" :entity-id="entityId"
                 :title="title" />
</template>

<script setup>
/**
 * 「修订历史 + 存一份档」两个按钮打成一个件，各页面插一行就够。
 *
 * 两种回看是两回事，所以两个按钮都在：
 * 历史答「这一格之前写的是什么」，存档答「那一天整页长什么样」。
 * 只给其中一个的话，另一个问题就只能靠猜。
 *
 * 存档同一天覆盖，所以按钮可以随便点，不会越存越多。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Camera, Clock } from '@element-plus/icons-vue'
import { apiError, archiveApi } from '../api'
import HistoryDrawer from './HistoryDrawer.vue'

const props = defineProps({
  // 修订历史的归属，如 special:12（整页级）
  scope: { type: String, default: '' },
  // 或者只看某一行：给 entity + entityId（表格行里用这一档）
  entity: { type: String, default: '' },
  entityId: { type: [Number, null], default: null },
  // 存档的对象；不给 kind 就只显示「修订历史」——按行是没有"整页存档"这回事的
  kind: { type: String, default: '' },
  refId: { type: Number, default: 0 },
  title: { type: String, default: '' },
  // 表格行里用 link 档：两个实心按钮会把操作列挤爆
  link: { type: Boolean, default: false },
  label: { type: String, default: '' },
})

const open = ref(false)
const saving = ref(false)

async function archiveNow() {
  saving.value = true
  try {
    const { data } = await archiveApi.create(props.kind, props.refId)
    ElMessage.success(`已存档（${data.label}），在「历史存档」页可以翻回来看`)
  } catch (e) {
    ElMessage.error(apiError(e, '存档失败'))
  } finally {
    saving.value = false
  }
}
</script>
