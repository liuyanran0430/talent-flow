import { defineConfig, devices } from '@playwright/test'

/**
 * TalentFlow 前端 E2E 测试配置
 *
 * 前置条件（二选一）：
 *   A. 已执行 `start.bat start` 同时启动 后端(8080) + 前端(3000)
 *   B. 后端已在 8080 运行；Playwright 会自动用 `npm run dev:e2e` 起前端
 *
 * 后端接口使用真实数据库 + mock 混合策略：
 *   - 列表类接口（/jobs, /candidates）走真实后端，验证页面渲染
 *   - 写操作（POST / PUT / DELETE）按需 page.route 拦截，避免污染真实数据
 *   - 需要 LLM 的接口（/resumes/{id}/analyze, /requirements/{id}/generate）一律 mock
 */
export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : 1,
  reporter: [
    ['html', { open: 'never' }],
    ['list'],
  ],
  use: {
    baseURL: 'http://localhost:3000',
    // 失败即保留 trace / video，成功则丢弃（retries=0 时 on-first-retry 不会触发）
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev:e2e',
    url: 'http://localhost:3000',
    // 本地已有 dev server 时直接复用（dev 机上不做严格端口独占）
    reuseExistingServer: true,
    timeout: 45_000,
  },
})
