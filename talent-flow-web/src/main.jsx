import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { initGlobalErrorCapture } from './utils/logger'
import { initTraceCapture } from './utils/trace'
import './index.css'

// 全局兜底：未捕获的 JS 异常与 Promise 拒绝都会进入日志并上报后端
initGlobalErrorCapture()
// 一次用户操作（点击/回车/提交）生成一个 trace_id，请求与日志共用
initTraceCapture()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
