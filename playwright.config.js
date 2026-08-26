const { defineConfig, devices } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './frontend/tests/browser',
  timeout: 30000,
  // The production service worker can activate and reload a page while a CI
  // assertion is running. PWA behaviour is tested separately; layout tests
  // must run against a stable document.
  use: { baseURL: 'http://127.0.0.1:4173', trace: 'retain-on-failure', screenshot: 'only-on-failure', serviceWorkers: 'block' },
  webServer: { command: 'python3 -m http.server 4173 --directory frontend', url: 'http://127.0.0.1:4173', reuseExistingServer: true },
  projects: [
    { name: 'mobile-safari', use: { ...devices['iPhone 13'] } },
    { name: 'desktop-chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1920, height: 1080 } } }
  ]
});
