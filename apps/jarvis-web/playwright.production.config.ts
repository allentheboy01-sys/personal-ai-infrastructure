import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e-production',
  fullyParallel: false,
  retries: 0,
  reporter: 'line',
  use: { baseURL: 'http://127.0.0.1:4174', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: '../../.venv/bin/uvicorn --app-dir ../.. tests.fixtures.jarvis_production_static_app:app --host 127.0.0.1 --port 4174 --no-access-log --no-proxy-headers',
    url: 'http://127.0.0.1:4174',
    reuseExistingServer: false,
  },
})
