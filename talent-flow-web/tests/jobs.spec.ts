import { test, expect } from '@playwright/test'

/**
 * 需求 2 + 3：核心业务流程 + 必填 / 格式校验
 * 职位管理 → 新建职位 → 必填校验 → 保存 → Toast 提示
 */
test.describe('职位管理', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('职位管理')
  })

  test('新建职位弹框：空名称保存触发必填校验', async ({ page }) => {
    await page.getByRole('button', { name: '新建职位' }).click()
    // 弹框标题可见
    await expect(page.getByRole('heading', { name: '新建职位' })).toBeVisible()

    // 什么都不填，直接保存
    await page.getByRole('button', { name: '保存职位' }).click()

    // Toast 提示：请先填写职位名称
    const toast = page.locator('.fixed.bottom-6')
    await expect(toast).toBeVisible()
    await expect(toast).toContainText('职位名称')
  })

  test('新建职位：填写完整后保存成功（mock 后端）', async ({ page }) => {
    // 拦截 POST /jobs 返回成功，避免污染真实数据
    await page.route('**/jobs', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ code: 0, message: 'ok', data: { id: 9999 } }),
        })
        return
      }
      await route.continue()
    })

    await page.getByRole('button', { name: '新建职位' }).click()
    await expect(page.getByRole('heading', { name: '新建职位' })).toBeVisible()

    // 职位名称
    await page.getByLabel('职位名称').fill('Playwright 测试工程师')

    // 所属部门：跳过占位项，选第一个真实部门
    const deptSelect = page.getByLabel('所属部门')
    const deptCount = await deptSelect.locator('option').count()
    if (deptCount > 1) await deptSelect.selectOption({ index: 1 })

    // 招聘人数
    await page.getByLabel('招聘人数').fill('5')

    // 保存
    await page.getByRole('button', { name: '保存职位' }).click()

    const toast = page.locator('.fixed.bottom-6')
    await expect(toast).toBeVisible()
    await expect(toast).toContainText('已保存')
  })
})
