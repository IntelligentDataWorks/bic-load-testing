import { test, expect } from '@playwright/test';

const QUESTION_TEXT = 'How many articles do we have in Training KCC for SS27?';

test('user creates a session and receives a chat response', async ({ page }) => {
  test.setTimeout(120_000);

  await page.goto('/');
  await page.getByRole('button', { name: 'New Session' }).click();

  const questionInput = page.getByPlaceholder('Ask a question about your data...');
  await questionInput.click();
  await questionInput.fill(QUESTION_TEXT);

  const [chatResponse] = await Promise.all([
    // The Send Message button actually calls the streaming route (SSE body, not JSON) --
    // matching "/api/chat" would also match "/api/chat/stream", so target it explicitly.
    page.waitForResponse(
      (resp) => resp.url().includes('/api/chat/stream') && resp.request().method() === 'POST'
    ),
    page.getByRole('button', { name: 'Send Message' }).click(),
  ]);

  expect(chatResponse.ok(), 'expected POST /api/chat/stream to succeed').toBeTruthy();

  // Each SSE frame is a "data: {...}" line; the terminal one has type "result" and carries
  // the same ChatResult shape /api/chat returns -- see openapi.json's ChatResult schema.
  const streamBody = await chatResponse.text();
  const events = streamBody
    .split(/\r?\n\r?\n/)
    .map((frame) => frame.split(/\r?\n/).find((line) => line.startsWith('data:')))
    .filter((line): line is string => Boolean(line))
    .map((line) => JSON.parse(line.slice('data:'.length).trim()));

  const resultEvent = events.find((event) => event.type === 'result');
  expect(resultEvent, 'expected a terminal SSE "result" event in the chat stream').toBeTruthy();

  const chatResult = resultEvent.result;
  const assistantText: string = (chatResult.message?.trim() || chatResult.insighter?.insight?.trim() || '');
  expect(assistantText.length, 'expected a non-empty assistant response in the API payload').toBeGreaterThan(0);

  await expect(page).toHaveURL(/session=chat_[A-Za-z0-9]+/);
  await expect(page.getByText(QUESTION_TEXT, { exact: true }).first()).toBeVisible();
  // Match on a short leading snippet since markdown rendering may split the full text across nodes.
  await expect(page.getByText(assistantText.slice(0, 40)).first()).toBeVisible();
});