# Copilot instructions for bic-load-testing

This repository load-tests the IRIS (DS Insights Companion) DEV app on Databricks:
Locust for API load, Playwright for the browser journey, and a local Streamlit
control centre (`streamlit_app.py`) that runs both.

## Where things are

- Setup and running: `docs/RUNBOOK.md` (Windows) and `docs/RUNBOOK-mac.md` (macOS)
  are the source of truth. Use only the one for the user's system. Follow its
  commands exactly; do not invent alternatives.
- Setup playbook for a new teammate: `.github/prompts/bic-playbook.prompt.md` (`/bic-playbook`).
- Profiles, environment variables, layout: `README.md`.
- Running without the app (Windows PowerShell only): `docs/cli-reference.md`.
- App internals: `docs/streamlit-control-centre.md`.

## Rules

- Run commands from the repository root. On Windows, use PowerShell and call tools
  through `.venv\Scripts\...`. On macOS, use zsh and call tools through
  `.venv/bin/...`. Never mix the two. No need to activate the virtual environment.
- Node.js, `npm ci` and the Chromium download are only needed for React UI and
  Combined tests. Don't install them for a user who only wants FastAPI BFF or Serving
  endpoint tests.
- Keep the known-good versions listed in section 1 of the runbook. Install missing
  tools only with the runbook's commands, which pin those versions. If an installed
  tool has a different version, tell the user both versions and ask whether to
  replace it; change nothing without a yes.
- Never upgrade a tool or package on your own, even when it suggests one (for
  example npm's `New major version of npm available`). Never run `npm install`,
  `npm update` or `uv pip install <package>`. Do not edit `requirements.txt`,
  `requirements.lock.txt`, `package.json` or `package-lock.json`.
- Ask before installing software, and ask before any run with more than 1 user.
- Never run the `prod-serving-*` profiles or point a test at a production host.
- Never open, print, copy or summarise: `playwright/.auth/*`, `~/.databrickscfg`,
  `.env` files, the contents of `results/`, `playwright-report/` or `test-results/`,
  or any environment variable holding a token (`BIC_AUTH_TOKEN`).
- Never ask the user to paste a token or PAT into the chat, and never write one to a
  file. Tokens go only into the app's **Authentication** page, which keeps them in
  memory.
- Sign-in steps need the user in a browser. Explain the step, then wait for the user
  to confirm it is done.
- Do not run `npm init playwright@latest` (it overwrites the config and tests). Do
  not edit tests or thresholds to make a failing check pass.
- Do not run `tests/bic-chat-recorded.spec.ts`; it is a raw recording. Always pass a
  spec path to `npx playwright test`.
- Do not commit or push unless the user asks.
- When something fails, look it up in section 12 (Troubleshooting) of the user's
  runbook first.
