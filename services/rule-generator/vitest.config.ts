import { cloudflareTest } from '@cloudflare/vitest-plugin';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [cloudflareTest({
    wrangler: { configPath: './wrangler.jsonc' },
    miniflare: {
      bindings: {
        DEEPSEEK_API_KEY: 'test-provider-key-not-a-credential',
        RULE_GENERATOR_TOKEN: 'test-operator-token-not-a-credential-32chars',
      },
    },
  })],
  test: { fileParallelism: false, testTimeout: 10000 },
});
