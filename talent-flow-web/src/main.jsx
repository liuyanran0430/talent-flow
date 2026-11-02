import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { initGlobalErrorCapture } from './utils/logger'
import './index.css'

// 全局兜底：未捕获的 JS 异常与 Promise 拒绝都会进入日志并上报后端
initGlobalErrorCapture()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
