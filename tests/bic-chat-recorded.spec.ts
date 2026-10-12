import { test, expect } from '@playwright/test';

test.use({
  storageState: 'C:\\Projects\\bic-load-testing\\playwright\\.auth\\bic-user.json'
});

test('test', async ({ page }) => {
  await page.goto('https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com/');
  await page.getByRole('button', { name: 'New Session' }).click();
  await page.getByPlaceholder('Ask a question about your').click();
  await page.getByPlaceholder('Ask a question about your').fill('hi');
  await page.goto('https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com/?session=chat_739267474ba44146');
});