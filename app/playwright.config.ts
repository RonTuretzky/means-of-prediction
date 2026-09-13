import { defineConfig } from "@playwright/test";

// E2E runs against its own anvil (port 8548, spawned in global-setup) and its own
// vite dev server (port 5198), so it never interferes with the dev environment.
export default defineConfig({
  testDir: "./e2e",
  testIgnore: /record\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  use: {
    baseURL: "http://localhost:5198",
    trace: "retain-on-failure",
  },
  webServer: {
    // global-setup syncs again after its fresh deployment, before tests open the app.
    command: "node scripts/sync-contracts.mjs && VITE_RPC_URL=http://localhost:8548 npx vite --port 5198 --strictPort",
    port: 5198,
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
