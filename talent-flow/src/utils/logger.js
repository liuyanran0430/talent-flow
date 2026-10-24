// 前端分级日志工具：控制台输出 + 内存环形缓冲（window.__TALENT_LOGS__ 可查）
// warn/error 自动上报后端 POST /logs/frontend 落盘，便于事后追溯线上问题
const API_BASE = 'http://localhost:8000'
const MAX_BUFFER = 200
const buffer = []

function safeStringify(value) {
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function currentSection() {
  // 单页应用无路由，从全局状态取当前区块；不可用时不携带
  try {
    return window.__TALENT_SECTION__ || null
  } catch {
    return null
  }
}

function write(level, tag, args) {
  const message = args.map(safeStringify).join(' ')
  const entry = { time: new Date().toISOString(), level, tag, message }
  buffer.push(entry)
  if (buffer.length > MAX_BUFFER) buffer.shift()
  if (typeof window !== 'undefined') window.__TALENT_LOGS__ = buffer

  const fn = { debug: console.debug, info: console.info, warn: console.warn, error: console.error }[level]
  fn(`[${entry.time.slice(11, 23)}][${tag}]`, ...args)

  if (level === 'warn' || level === 'error') {
    fetch(`${API_BASE}/logs/frontend`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ level, tag, message, page: currentSection() }),
    }).catch(() => {}) // 上报失败静默，避免无限递归
  }
  return entry
}

export const logger = {
  debug: (tag, ...args) => write('debug', tag, args),
  info: (tag, ...args) => write('info', tag, args),
  warn: (tag, ...args) => write('warn', tag, args),
  error: (tag, ...args) => write('error', tag, args),
  history: () => [...buffer],
}

// 全局兜底：捕获未处理的 JS 异常与 Promise 拒绝，避免错误无声丢失
export function initGlobalErrorCapture() {
  if (typeof window === 'undefined') return
  window.addEventListener('error', (e) => {
    logger.error('global', e.message, `${e.filename || ''}:${e.lineno || 0}:${e.colno || 0}`)
  })
  window.addEventListener('unhandledrejection', (e) => {
    logger.error('promise', safeStringify(e.reason))
  })
}
