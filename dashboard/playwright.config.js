// @ts-check
const { defineConfig, devices } = require("@playwright/test");

// ISOLATED, local-only Playwright harness for the dashboard SPA (ADR 0003).
// Boots the FastAPI app on a FIXED test port against a DETERMINISTIC fixture board
// (tests/e2e/fixture-board.json) so every assertion is stable. NOT wired into ci.yml /
// .pre-commit-config.yaml — the Python `dashboard` gate stays byte-unaffected.

const PORT = 8787;
const BASE_URL = `http://127.0.0.1:${PORT}`;

module.exports = defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    // dashboard/.venv is the 3.12 interpreter that carries fastapi/uvicorn/pydantic.
    // FENRIR_DASH_BOARD pins the deterministic fixture; FENRIR_DASH_PROJECT="" scopes
    // telemetry to "all" so the run never depends on the dev's live ~/.claude data.
    command: `.venv/bin/python -m uvicorn backend.app:app --port ${PORT}`,
    url: `${BASE_URL}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    env: {
      FENRIR_DASH_BOARD: "tests/e2e/fixture-board.json",
      FENRIR_DASH_PROJECT: "",
    },
  },
});
