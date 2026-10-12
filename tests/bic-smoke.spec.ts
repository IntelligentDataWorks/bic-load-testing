import { test, expect } from '@playwright/test';

const APP_HEADING_PATTERN = /WELCOME TO IRIS/i;
const QUESTION_INPUT_PLACEHOLDER = 'Ask a question about your data...';
const AUTH_REDIRECT_PATTERN = /login|signin|sign-in|authorize|oauth|sso/i;

test('authenticated user lands on the BIC app, not a login page', async ({ page, baseURL }) => {
  const response = await page.goto('/');

  expect(response?.ok(), 'expected the root page to load successfully').toBeTruthy();

  // A login/SSO redirect would send the saved session to a different URL than the app itself.
  await expect(page).not.toHaveURL(AUTH_REDIRECT_PATTERN);
  expect(new URL(page.url()).origin).toBe(new URL(baseURL!).origin);

  // Stable, user-visible elements that only render once the app (not a login page) has loaded.
  await expect(page.getByRole('heading', { name: APP_HEADING_PATTERN })).toBeVisible();
  await expect(page.getByPlaceholder(QUESTION_INPUT_PLACEHOLDER)).toBeVisible();
  await expect(page.getByRole('button', { name: 'VIEW DATA SOURCES' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'NEW SESSION' })).toBeVisible();
});
