import { test, expect } from '@playwright/test'

/**
 * 需求 5：接口失败提示与重试
 * 模拟 GET /jobs 返回 500 → Toast 错误 → 恢复接口后重新加载 → 列表正常渲染
 */
test.describe('接口失败提示与重试', () => {
  test('GET /jobs 返回 500 时 Toast 提示错误，重试后列表恢复', async ({ page }) => {
    // 首次加载让 /jobs 直接失败
    await page.route('**/jobs', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ code: 500, message: '后端模拟异常' }),
        })
        return
      }
      await route.continue()
    })

    await page.goto('/')
    const toast = page.locator('.fixed.bottom-6')
    await expect(toast).toBeVisible({ timeout: 10_000 })
    await expect(toast).toContainText('加载失败')

    // 解除拦截，模拟「重试」：重新加载页面触发一次正常请求
    await page.unroute('**/jobs')
    await page.reload()

    // 列表恢复：表格出现真实职位行
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('职位管理')
    await expect(page.locator('tbody tr').first()).toBeVisible()
  })
})
