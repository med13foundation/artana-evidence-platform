import { expect, test } from '@playwright/test'

test.describe('Data discovery workflows', () => {
  test('renders the current orchestrated source selection flow', async ({ page }) => {
    await page.goto('/data-discovery')

    await expect(page.getByRole('heading', { name: 'Data Discovery' })).toBeVisible()
    await expect(page.getByRole('button', { name: /PubMed Clinical/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /ClinVar Variants/i })).toBeVisible()
    await expect(page.getByText('Selected sources: 1')).toBeVisible()
    await expect(
      page.getByRole('button', { name: 'Run search (backend orchestrated)' }),
    ).toBeEnabled()

    await page.getByRole('button', { name: /ClinVar Variants/i }).click()
    await expect(page.getByText('Selected sources: 2')).toBeVisible()

    await page.getByRole('button', { name: /PubMed Clinical/i }).click()
    await expect(page.getByText('Selected sources: 1')).toBeVisible()
  })
})
