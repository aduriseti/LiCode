import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    setupFiles: ["tests/vitest.setup.ts"],
    environment: "node",
    globals: true,
    exclude: [
      "**/node_modules/**",
      "**/dist/**",
      ".arenas/**"
    ]
  }
});
