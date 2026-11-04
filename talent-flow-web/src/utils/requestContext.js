// 请求上下文：会话 id 与当前 LLM 请求 id。
// - session_id 随所有请求通过 X-Session-ID 传给后端，写入后端结构化日志，用于定位「哪段对话」；
// - request_id 只由调用 LLM 的异步接口产生（接口返回），其它请求没有该字段，因此默认 null。
const SESSION_KEY = 'talent-flow-session-id'

function generateSessionId() {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID().replace(/-/g, '').slice(0, 16)
    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function loadSessionId() {
  try {
    let sid = sessionStorage.getItem(SESSION_KEY)
    if (!sid) {
      sid = generateSessionId()
      sessionStorage.setItem(SESSION_KEY, sid)
    }
    if (typeof window !== 'undefined') window.__TALENT_SESSION_ID__ = sid
    return sid
  } catch {
    return '-'
  }
}

// 会话 id：同一个标签页会话内稳定，刷新页面后保留（sessionStorage）
export const SESSION_ID = loadSessionId()

let activeRequestId = null

// 调用 LLM 的异步接口返回 request_id 后设置，本次操作期间的前端日志都带上它
export function setActiveRequestId(requestId) {
  activeRequestId = requestId || null
  if (typeof window !== 'undefined') window.__TALENT_REQUEST_ID__ = activeRequestId
}

export function getActiveRequestId() {
  return activeRequestId
}

// 仅清除自己设置的那一个，避免并发请求互相覆盖
export function clearActiveRequestId(requestId) {
  if (requestId && activeRequestId === requestId) setActiveRequestId(null)
}
