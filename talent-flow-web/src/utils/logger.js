// 前端分级日志工具：控制台输出 + 内存环形缓冲（window.__TALENT_LOGS__ 可查）
// warn/error 自动上报后端 POST /logs/frontend 落盘；携带 session_id/页面/URL/UA，
// 与后端日志中的 rid 一起用于全流程追溯（同一会话的操作可在日志中串联）。
const API_BASE = 'http://localhost:8000'
const MAX_BUFFER = 200
const SESSION_KEY = 'talent-flow-session-id'
const buffer = []

// 会话 id：同一个标签页会话内稳定，刷新页面后保留（sessionStorage）
function getSessionId() {
  try {
    let sid = sessionStorage.getItem(SESSION_KEY)
    if (!sid) {
      sid = typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID().replace(/-/g, '').slice(0, 16)
        : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
      sessionStorage.setItem(SESSION_KEY, sid)
    }
    window.__TALENT_SESSION_ID__ = sid
    return sid
  } catch {
    return '-'
  }
}

const SESSION_ID = getSessionId()

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

function report(level, tag, message, stack) {
  const payload = {
    level,
    tag,
    message,
    page: currentSection(),
    stack,
    session_id: SESSION_ID,
    url: typeof location !== 'undefined' ? location.href : null,
    user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : null,
  }
  fetch(`${API_BASE}/logs/frontend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    keepalive: true, // 页面卸载/跳转时也尽量保证日志发出
  }).catch(() => {}) // 上报失败静默，避免无限递归
}

function write(level, tag, args) {
  const message = args.map(safeStringify).join(' ')
  const stack = pickStack(args)
  const entry = { time: new Date().toISOString(), level, tag, message, session_id: SESSION_ID }
  buffer.push(entry)
  if (buffer.length > MAX_BUFFER) buffer.shift()
  if (typeof window !== 'undefined') window.__TALENT_LOGS__ = buffer

  const fn = { debug: console.debug, info: console.info, warn: console.warn, error: console.error }[level]
  fn(`[${entry.time.slice(11, 23)}][${tag}]`, ...args)

  if (level === 'warn' || level === 'error') report(level, tag, message, stack)
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
