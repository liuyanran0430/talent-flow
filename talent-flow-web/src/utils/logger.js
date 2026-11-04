// 前端分级日志工具：控制台输出 + 内存环形缓冲（window.__TALENT_LOGS__ 可查）
// warn/error 自动上报后端 POST /logs/frontend 落盘；携带 session_id/request_id/页面/URL/UA，
// request_id 仅调用 LLM 的接口才有，用于和该次 LLM 请求的后端日志对齐。
import { API_BASE, apiFetch } from './api'
import { SESSION_ID, getActiveRequestId } from './requestContext'

const MAX_BUFFER = 200
const buffer = []

function safeStringify(value) {
  if (typeof value === 'string') return value
  if (value instanceof Error) return value.stack || `${value.name}: ${value.message}`
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

// 单页应用无路由，从全局状态取当前区块；不可用时不携带
function currentSection() {
  try {
    return window.__TALENT_SECTION__ || null
  } catch {
    return null
  }
}

function pickStack(args) {
  const err = args.find((a) => a instanceof Error)
  return err?.stack || null
}

function report(level, tag, message, stack, ctx = null) {
  const payload = {
    level,
    tag,
    message,
    page: currentSection(),
    stack,
    session_id: SESSION_ID,
    // 优先使用日志所属 LLM 请求的 request_id，保证与后端同一次请求的日志一致
    request_id: ctx?.request_id ?? getActiveRequestId(),
    url: typeof location !== 'undefined' ? location.href : null,
    user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : null,
  }
  apiFetch(`${API_BASE}/logs/frontend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    keepalive: true, // 页面卸载/跳转时也尽量保证日志发出
  }).catch(() => {}) // 上报失败静默，避免无限递归
}

function write(level, tag, args, ctx = null) {
  const message = args.map(safeStringify).join(' ')
  const stack = pickStack(args)
  const requestId = ctx?.request_id ?? getActiveRequestId()
  const entry = {
    time: new Date().toISOString(),
    level,
    tag,
    message,
    session_id: SESSION_ID,
    request_id: requestId,
  }
  buffer.push(entry)
  if (buffer.length > MAX_BUFFER) buffer.shift()
  if (typeof window !== 'undefined') window.__TALENT_LOGS__ = buffer

  const fn = { debug: console.debug, info: console.info, warn: console.warn, error: console.error }[level]
  fn(`[${entry.time.slice(11, 23)}][${requestId || '-'}][${tag}]`, ...args)

  if (level === 'warn' || level === 'error') report(level, tag, message, stack, ctx)
  return entry
}

export const logger = {
  debug: (tag, ...args) => write('debug', tag, args),
  info: (tag, ...args) => write('info', tag, args),
  warn: (tag, ...args) => write('warn', tag, args),
  error: (tag, ...args) => write('error', tag, args),
  history: () => [...buffer],
  sessionId: SESSION_ID,
}

// 接口失败自动记录：使用该请求的 request_id 上报，保证前后端日志 request_id 一一对应
export function initApiErrorCapture() {
  if (typeof window === 'undefined') return
  window.addEventListener('talent:api-error', (e) => {
    const d = e.detail || {}
    const message = d.error
      ? `${d.method} ${d.path} 请求失败 status=${d.status} error=${d.error}`
      : `${d.method} ${d.path} 请求失败 status=${d.status}`
    write('error', 'api', [message], { request_id: d.requestId })
  })
}

// 全局兜底：捕获未处理的 JS 异常与 Promise 拒绝，避免错误无声丢失
export function initGlobalErrorCapture() {
  if (typeof window === 'undefined') return
  window.addEventListener('error', (e) => {
    logger.error(
      'global',
      e.message,
      `${e.filename || ''}:${e.lineno || 0}:${e.colno || 0}`,
      e.error instanceof Error ? e.error : undefined,
    )
  })
  window.addEventListener('unhandledrejection', (e) => {
    logger.error('promise', e.reason instanceof Error ? e.reason : safeStringify(e.reason))
  })
}
