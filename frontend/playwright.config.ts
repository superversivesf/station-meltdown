import { defineConfig, devices } from '@playwright/test';

const BACKEND_PORT = process.env.E2E_BACKEND_PORT || '8090';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: 'list',
  timeout: 120000,
  use: {
    baseURL: `http://localhost:${BACKEND_PORT}`,
    trace: 'on-first-retry',
    actionTimeout: 10000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: `npm run build && cp -r build ../backend/static && cd ../backend && DEBUG_MODE=1 ACTION_PHASE_SECONDS=5 ${process.env.E2E_PYTHON || 'python'} -m uvicorn main:app --host 0.0.0.0 --port ${BACKEND_PORT}`,
    url: `http://localhost:${BACKEND_PORT}/api/health`,
    timeout: 60000,
    // Never reuse a stale server: a leftover dev backend on the port would
    // silently serve old JS and produce green runs against stale code.
    reuseExistingServer: false,
    cwd: '.',
  },
});