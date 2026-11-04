import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { initApiErrorCapture, initGlobalErrorCapture } from './utils/logger'
import './index.css'

// 全局兜底：未捕获的 JS 异常与 Promise 拒绝都会进入日志并上报后端
initGlobalErrorCapture()
// 接口失败自动记录：携带该请求的 request_id（仅 LLM 接口有），与后端日志对齐
initApiErrorCapture()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
