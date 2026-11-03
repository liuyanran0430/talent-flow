import { test, expect } from '@playwright/test'

/**
 * 需求 4：返回上一步后数据保留
 * 导入简历页选择的部门 + 职位，切到其他页面再切回仍然保持。
 */
test.describe('返回上一步数据保留', () => {
  test('导入简历页：选部门和职位 → 切候选人管理 → 切回 → 选择保持', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('职位管理')

    // 1. 进入导入简历
    await page.locator('aside').getByRole('button', { name: '导入简历', exact: true }).click()
    await expect(page.getByRole('heading', { name: '请先选择部门与职位' })).toBeVisible()

    // 2. 选择部门（index 0 是「选择部门」占位）
    const deptSelect = page.locator('select').first()
    await expect(deptSelect.locator('option')).not.toHaveCount(1)
    await deptSelect.selectOption({ index: 1 })
    const deptValue = await deptSelect.inputValue()
    expect(deptValue).not.toBe('')

    // 3. 选择职位（部门联动后异步加载，等出现真实选项）
    const jobSelect = page.locator('select').nth(1)
    await expect.poll(async () => jobSelect.locator('option').count(), { timeout: 10_000 }).toBeGreaterThan(1)
    await jobSelect.selectOption({ index: 1 })
    const jobValue = await jobSelect.inputValue()
    expect(jobValue).not.toBe('')

    // 4. 切到候选人管理
    await page.locator('aside').getByRole('button', { name: '候选人管理', exact: true }).click()
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('候选人管理')

    // 5. 切回导入简历，验证选择仍然保留
    await page.locator('aside').getByRole('button', { name: '导入简历', exact: true }).click()
    await expect(page.locator('select').first()).toHaveValue(deptValue)
    await expect(page.locator('select').nth(1)).toHaveValue(jobValue)
  })
})
