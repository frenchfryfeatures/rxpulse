import { defineConfig, devices } from "@playwright/test";

const API_PORT = 8100;
const WEB_PORT = 3100;
const DB = process.env.E2E_DATABASE_URL ?? "postgresql+asyncpg://rxpulse:rxpulse@localhost:5432/rxpulse_e2e";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    viewport: { width: 1600, height: 1000 },
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1600, height: 1000 },
        launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
      },
    },
  ],
  webServer: [
    {
      // Fresh schema + seeded eye-hospital data on every run.
      command: `uv run alembic upgrade head && uv run python -m app.seed --reset && uv run uvicorn app.main:app --port ${API_PORT}`,
      cwd: "../backend",
      url: `http://localhost:${API_PORT}/health`,
      env: { AUTH_MODE: "dev", ENV: "local", DATABASE_URL: DB, CORS_ORIGINS: `["http://localhost:${WEB_PORT}"]` },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `npx next dev -p ${WEB_PORT}`,
      url: `http://localhost:${WEB_PORT}/login`,
      env: {
        NEXT_PUBLIC_API_BASE_URL: `http://localhost:${API_PORT}/api/v1`,
        NEXT_PUBLIC_AUTH_MODE: "dev",
        NEXT_PUBLIC_IDLE_TIMEOUT_MINUTES: "0",
      },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
