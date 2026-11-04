import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3001,
    strictPort: true, // 端口被占用时直接失败，避免自动漂移到其他端口导致后端 CORS 不匹配
    open: true
  }
})
