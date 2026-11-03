// 统一接口封装：所有请求带上当前操作的 X-Trace-ID，并回读后端回传的 trace id。
import { getActiveTraceId, setLastTraceId } from './trace'

export const API_BASE = 'http://localhost:8080'

export async function apiFetch(input, init = {}) {
  const traceId = getActiveTraceId()
  const headers = new Headers(init.headers || {})
  headers.set('X-Trace-ID', traceId)
  // 请求失败（含跨域/断网）时也保留该 trace，便于错误上报与后端日志对齐
  setLastTraceId(traceId)
  const res = await fetch(input, { ...init, headers })
  const echoed = res.headers.get('X-Trace-ID')
  if (echoed) setLastTraceId(echoed)
  return res
}
