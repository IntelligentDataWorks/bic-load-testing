import { defineConfig, devices } from '@playwright/test';

/**
 * Read environment variables from file.
 * https://github.com/motdotla/dotenv
 */
// import dotenv from 'dotenv';
// import path from 'path';
// dotenv.config({ path: path.resolve(__dirname, '.env') });

/**
 * Defaults below are unchanged; each is now overridable by an environment
 * variable so the Streamlit control centre can point a run at a different host,
 * a different saved session, or different artefact capture without editing this
 * file. Running the documented `npx playwright test ...` commands by hand with
 * no BIC_* variables set behaves exactly as before.
 */
const DEFAULT_BASE_URL = 'https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com';
const DEFAULT_STORAGE_STATE = 'playwright/.auth/bic-user.json';

type TraceMode = NonNullable<Parameters<typeof defineConfig>[0]['use']>['trace'];
type ScreenshotMode = NonNullable<Parameters<typeof defineConfig>[0]['use']>['screenshot'];
type VideoMode = NonNullable<Parameters<typeof defineConfig>[0]['use']>['video'];

/**
 * See https://playwright.dev/docs/test-configuration.
 */
export default defineConfig({
  testDir: './tests',
  /* Run tests in files in parallel */
  fullyParallel: true,
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,
  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,
  /* One worker initially -- raise once the deployed app's tolerance for concurrent sessions is known. */
  workers: 1,
  /* Reporter to use. See https://playwright.dev/docs/test-reporters */
  reporter: 'html',
  /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
  use: {
    /* Base URL to use in actions like `await page.goto('')`. */
    baseURL: process.env.BIC_BASE_URL || DEFAULT_BASE_URL,

    /* Reuse the signed-in session captured by the auth setup project. */
    storageState: process.env.BIC_STORAGE_STATE || DEFAULT_STORAGE_STATE,

    /* Only capture screenshots and traces for failing tests. */
    screenshot: (process.env.BIC_SCREENSHOT as ScreenshotMode) || 'only-on-failure',
    trace: (process.env.BIC_TRACE as TraceMode) || 'retain-on-failure',
    video: (process.env.BIC_VIDEO as VideoMode) || 'off',

    /* The deployed app can be slow to respond; give navigations more room than the default. */
    navigationTimeout: 60_000,
  },

  /* Configure projects for major browsers */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },

    /* Enable additional browsers once the Chromium-only baseline is stable. */
    // {
    //   name: 'firefox',
    //   use: { ...devices['Desktop Firefox'] },
    // },

    // {
    //   name: 'webkit',
    //   use: { ...devices['Desktop Safari'] },
    // },

    /* Test against mobile viewports. */
    // {
    //   name: 'Mobile Chrome',
    //   use: { ...devices['Pixel 5'] },
    // },
    // {
    //   name: 'Mobile Safari',
    //   use: { ...devices['iPhone 12'] },
    // },

    /* Test against branded browsers. */
    // {
    //   name: 'Microsoft Edge',
    //   use: { ...devices['Desktop Edge'], channel: 'msedge' },
    // },
    // {
    //   name: 'Google Chrome',
    //   use: { ...devices['Desktop Chrome'], channel: 'chrome' },
    // },
  ],

  /* Run your local dev server before starting the tests */
  // webServer: {
  //   command: 'npm run start',
  //   url: 'http://localhost:3000',
  //   reuseExistingServer: !process.env.CI,
  // },
});
