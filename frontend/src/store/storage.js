/**
 * 上传目录磁盘空间查询 + 阈值告警。
 *
 * 用法：
 *   import { checkStorageOrWarn } from '../store/storage'
 *   await checkStorageOrWarn()   // 内部已弹 ElMessage.warning
 */
import { ElMessage } from 'element-plus'
import { systemApi } from '../api'

const WARN_THRESHOLD = 10 * 1024 * 1024 * 1024 // 10 GB

function formatGB(bytes) {
  return (bytes / 1024 / 1024 / 1024).toFixed(2)
}

/**
 * 拉取存储信息并在低于阈值时弹 warning。
 * 返回 storage info 对象，调用方可用来再做判断；
 * 接口失败时静默返回 null（不应该阻塞上传流程）。
 */
export async function checkStorageOrWarn() {
  try {
    const { data } = await systemApi.storage()
    if (data.free < WARN_THRESHOLD) {
      ElMessage.warning({
        message:
          `服务器上传目录所在分区剩余空间仅 ${formatGB(data.free)} GB ` +
          `(总 ${formatGB(data.total)} GB)，已低于 10 GB 阈值，请尽快清理或扩容。`,
        duration: 6000,
      })
    }
    return data
  } catch {
    return null
  }
}

export { WARN_THRESHOLD }
