// 统一接口封装：所有请求带上会话 id（X-Session-ID），供后端结构化日志记录 session_id。
// 请求失败（非 2xx / 网络错误）派发 talent:api-error 事件，由 logger 用当前 request_id 上报；
// request_id 只有调用 LLM 的接口才有，其它请求该字段为空。
import { SESSION_ID, getActiveRequestId } from './requestContext'

export const API_BASE = 'http://localhost:8080'

function requestPath(url) {
  try {
    const u = new URL(url, typeof location !== 'undefined' ? location.origin : 'http://localhost')
    return u.pathname + u.search
  } catch {
    return String(url)
  }
}

// 把失败请求交给 logger；跳过日志上报接口自身，避免失败时递归
function notifyApiError({ requestId, status, method, url, error }) {
  if (typeof window === 'undefined') return
  const path = requestPath(url)
  if (path.includes('/logs/frontend')) return
  window.dispatchEvent(
    new CustomEvent('talent:api-error', {
      detail: { requestId, status, method, path, error },
    }),
  )
}

export async function apiFetch(input, init = {}) {
  // 先取当前 request_id：请求期间可能被其它操作覆盖
  const requestId = getActiveRequestId()
  const method = (init.method || 'GET').toUpperCase()
  const url = typeof input === 'string' ? input : input?.url || ''
  const headers = new Headers(init.headers || {})
  headers.set('X-Session-ID', SESSION_ID)

  let res
  try {
    res = await fetch(input, { ...init, headers })
  } catch (e) {
    notifyApiError({ requestId, status: 0, method, url, error: String(e) })
    throw e
  }
  if (!res.ok) notifyApiError({ requestId, status: res.status, method, url })
  return res
}

// LLM 接口采用异步任务：调用后拿到 request_id，轮询 GET /tasks/{request_id} 直到成功/失败。
// success 返回任务 data（result 为业务结果），failed 抛错，超时抛错，由调用方提示用户。
export async function pollTask(
  requestId,
  { interval = 1500, timeout = 180000, onTick } = {},
) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const res = await apiFetch(`${API_BASE}/tasks/${requestId}`)
    const json = await res.json()
    if (!res.ok || json.code !== 0) throw new Error(json.message || '任务状态查询失败')
    const data = json.data || {}
    if (onTick) onTick(data)
    if (data.status === 'success') return data
    if (data.status === 'failed') throw new Error(data.error || '处理失败')
    await new Promise((r) => setTimeout(r, interval))
  }
  throw new Error('处理超时，请稍后查看列表确认结果')
}
