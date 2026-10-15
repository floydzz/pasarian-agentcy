import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  expect: { timeout: 15000 },
  retries: 0,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:8123', trace: 'retain-on-failure', screenshot: 'only-on-failure', headless: true },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 1000 } } },
    { name: 'tablet', use: { viewport: { width: 768, height: 1024 } } },
    { name: 'mobile', use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
    { name: 'reduced-motion', use: { viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' } },
  ],
  webServer: { command: '../.venv/bin/python ../backend/scripts/browser_fixture.py', url: 'http://127.0.0.1:8123/api/health', timeout: 120000, reuseExistingServer: false },
})
