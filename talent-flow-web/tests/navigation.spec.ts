import { test, expect } from '@playwright/test'

/**
 * 需求 1：页面正常加载
 * 验证 5 个侧栏菜单都能打开对应页面，页面核心元素可见。
 */
const MENUS = [
  { label: '职位管理', h1: '职位管理' },
  { label: '职位要求配置', h1: '职位要求配置' },
  { label: '候选人管理', h1: '候选人管理' },
  { label: '职位匹配看板', h1: '职位匹配看板' },
  // 导入简历页没有 h1，用空状态下方的提示标题判断
  { label: '导入简历', h1: null },
]

test.describe('页面正常加载', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    // 等首屏加载完成：h1 出现
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('职位管理')
  })

  test('默认进入职位管理，标题与统计卡都可见', async ({ page }) => {
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('职位管理')
    // 3 张统计卡（招聘中 / 已暂停 / 已关闭）
    for (const label of ['招聘中', '已暂停', '已关闭']) {
      await expect(page.getByText(label, { exact: true }).first()).toBeVisible()
    }
  })

  for (const m of MENUS) {
    test(`点击「${m.label}」能正常打开`, async ({ page }) => {
      // 侧栏按钮唯一匹配（exact 避免「职位要求配置」误匹配其他按钮）
      const menuBtn = page.locator('aside').getByRole('button', { name: m.label, exact: true })
      await menuBtn.click()

      // 当前菜单高亮
      await expect(menuBtn).toHaveClass(/text-cyan-300/)

      if (m.h1) {
        await expect(page.getByRole('heading', { level: 1 })).toHaveText(m.h1)
      } else {
        // 导入简历页未选部门/职位时，展示引导提示
        await expect(page.getByRole('heading', { name: '请先选择部门与职位' })).toBeVisible()
      }
    })
  }

  test('网站标题正确', async ({ page }) => {
    await expect(page).toHaveTitle(/招聘配置中心|TalentFlow/i)
  })
})
