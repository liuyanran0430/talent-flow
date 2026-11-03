// 操作级 trace id：一次用户操作（点击/回车/表单提交）生成一个 trace id。
// 该 id 通过 X-Trace-ID 请求头传给后端，后端日志与前端日志用同一 id 串联。
const TRACE_KEY = '__TALENT_TRACE_ID__'
const LAST_TRACE_KEY = '__LAST_TRACE_ID__'
// 同一次点击可能连续触发 pointerdown → submit，用一个短窗口合并，避免拆成多个 trace
const COALESCE_MS = 400

let activeTraceId = null
let lastBeginAt = 0

export function newTraceId() {
  const raw = typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID().replace(/-/g, '')
    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`
  return raw.slice(0, 16)
}

// 开始一个新操作：生成新的 trace id（短时间内重复触发则复用，保证一次点击一个 trace）
export function beginTrace() {
  const now = Date.now()
  if (activeTraceId && now - lastBeginAt < COALESCE_MS) return activeTraceId
  lastBeginAt = now
  activeTraceId = newTraceId()
  if (typeof window !== 'undefined') window[TRACE_KEY] = activeTraceId
  return activeTraceId
}

// 当前操作的 trace id（页面初始化/无交互时懒生成）
export function getActiveTraceId() {
  if (!activeTraceId) {
    activeTraceId = newTraceId()
    if (typeof window !== 'undefined') window[TRACE_KEY] = activeTraceId
  }
  return activeTraceId
}

// 最近一次请求实际使用的 trace id（后端回传的优先，用于错误上报对齐）
export function getLastTraceId() {
  return typeof window !== 'undefined' ? window[LAST_TRACE_KEY] || null : null
}

export function setLastTraceId(traceId) {
  if (typeof window !== 'undefined' && traceId) window[LAST_TRACE_KEY] = traceId
}

// 全局捕获用户操作：一次点击 / 一次回车 / 一次表单提交 = 一个新的 trace
export function initTraceCapture() {
  if (typeof window === 'undefined') return
  window.addEventListener('pointerdown', () => beginTrace(), true)
  window.addEventListener(
    'keydown',
    (e) => {
      if (e.key === 'Enter' || e.key === ' ') beginTrace()
    },
    true,
  )
  window.addEventListener('submit', () => beginTrace(), true)
}
