import { expect, test } from '@playwright/test'

test.describe('Storage dashboard', () => {
  test('creates, tests, toggles, and disables configurations', async ({ page }) => {
    await page.goto('/system-settings')
    await page.getByRole('tab', { name: 'Storage' }).click()

    await expect(page.getByRole('heading', { name: 'Storage Platform Overview' })).toBeVisible()
    await expect(page.getByTestId('storage-card-config-local')).toBeVisible()

    await page.getByRole('button', { name: 'Add Configuration' }).click()
    await page.getByLabel('Name').fill('Cloud Archive')
    await page.getByLabel('Provider').selectOption('google_cloud_storage')
    await page.getByLabel('Bucket Name').fill('artana-e2e')
    await page.getByLabel('Path Prefix').fill('/archives')
    await page.getByLabel('Credentials Secret').fill('projects/playwright/secrets/storage')
    await page.getByRole('button', { name: 'Create Configuration' }).click()
    await page.getByRole('button', { name: 'Continue without maintenance' }).click()

    const cloudCard = page.locator('[data-testid^="storage-card-"]').filter({ hasText: 'Cloud Archive' })
    await expect(cloudCard).toBeVisible()

    await cloudCard.getByRole('button', { name: 'Test Connection' }).click()
    await expect(cloudCard.getByRole('button', { name: 'Testing...' })).toBeVisible()
    await expect(cloudCard.getByRole('button', { name: 'Test Connection' })).toBeVisible()

    const switchControl = cloudCard.getByRole('switch')
    await expect(switchControl).toHaveAttribute('aria-checked', 'true')
    await switchControl.click()
    await expect(switchControl).toHaveAttribute('aria-checked', 'false')
    await switchControl.click()
    await expect(switchControl).toHaveAttribute('aria-checked', 'true')

    await cloudCard.getByRole('button', { name: 'Delete' }).click()
    await expect(switchControl).toHaveAttribute('aria-checked', 'false')
    await expect(cloudCard.getByText('Disabled')).toBeVisible()
  })
})
