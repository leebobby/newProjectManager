/**
 * 客户面问题跟踪的全局缓存。
 *
 * 问题条目是一张全量小表，原来「客户面状态」总览与「问题跟踪」tab 各自
 * 每次进入都全量拉一遍（外加一次 /summary），切 tab / 回访都要重等。
 * 这里缓存一份全量结果，两处共用：进入即用缓存秒显，后台再静默刷新；
 * 增删改就地更新缓存，避免整表重拉。统计卡也从缓存现算，不再单独请求 /summary。
 */
import { reactive } from 'vue'
import { customerIssueApi } from '../api'

const state = reactive({
  rows: [],
  loaded: false,
  loading: false,
})

export const customerIssues = state

// 首次进入：已加载则直接用缓存，不重复请求
export async function ensureIssues() {
  if (state.loaded || state.loading) return
  await reloadIssues()
}

// 强制全量重拉（含已闭环，无筛选——筛选一律在前端做）
export async function reloadIssues() {
  state.loading = true
  try {
    const { data } = await customerIssueApi.list()
    state.rows = data
    state.loaded = true
  } finally {
    state.loading = false
  }
}

// 后台静默刷新：保留旧数据，拿到新数据再替换（回访时先显示后刷新）
export async function refreshIssues() {
  try {
    const { data } = await customerIssueApi.list()
    state.rows = data
    state.loaded = true
  } catch {
    /* 静默：不打断已在展示的缓存 */
  }
}

export function upsertIssue(row) {
  const i = state.rows.findIndex((r) => r.id === row.id)
  if (i >= 0) state.rows[i] = row
  else state.rows.push(row)
}

export function removeIssue(id) {
  const i = state.rows.findIndex((r) => r.id === id)
  if (i >= 0) state.rows.splice(i, 1)
}

export function clearIssues() {
  state.rows = []
  state.loaded = false
}
