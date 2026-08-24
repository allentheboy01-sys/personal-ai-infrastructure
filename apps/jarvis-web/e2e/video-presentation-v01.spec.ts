import { expect, test } from '@playwright/test'

test('desktop presents a video card and ResourceRef-owned native player', async ({ page, isMobile }) => {
  test.skip(isMobile, 'desktop-only behavior')
  await page.route('**/api/v1/resources/**/video', async (route) => {
    await route.fulfill({
      status: 206,
      headers: {
        'Content-Type': 'video/mp4',
        'Content-Range': 'bytes 0-0/1',
        'Accept-Ranges': 'bytes',
        'Content-Length': '1',
      },
      body: '0',
    })
  })
  await page.goto('/?page=resources&detail=video&scene=review')
  const card = page.getByRole('article').filter({ hasText: 'Garden clip' })
  await expect(card.getByRole('img', { name: 'Garden clip' })).toBeVisible()
  await expect(card.locator('.video-play-indicator')).toBeVisible()
  const detail = page.locator('.desktop-panel-slot .work-panel')
  const video = detail.locator('video')
  await expect(video).toBeVisible()
  await expect(video.locator('source')).toHaveAttribute('src', /^\/api\/v1\/resources\/.+\/video$/)
  await expect(page.getByRole('article').filter({ hasText: 'Morning lake' }).getByRole('img')).toBeVisible()
})

test('mobile video card and player fit without horizontal overflow', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'mobile-only behavior')
  await page.route('**/api/v1/resources/**/video', async (route) => {
    await route.fulfill({ status: 200, contentType: 'video/mp4', body: '0' })
  })
  await page.goto('/?page=resources&detail=video&scene=review')
  await expect(page.locator('.resource-card').filter({ hasText: 'Garden clip' }).locator('.video-play-indicator')).toBeAttached()
  const detail = page.getByRole('dialog', { name: 'Resource detail' })
  await expect(detail.locator('video')).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
  expect(overflow).toBe(false)
})
