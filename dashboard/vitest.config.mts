import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: { "@": import.meta.dirname },
  },
  test: {
    environment: "node",
    include: ["**/*.test.ts"],
    // Set before any test file's top-level imports run (ESM hoists imports
    // above ordinary statements, so setting process.env inline in a test
    // file is too late for a module-load-time `const X = process.env.X!`).
    env: { NEXT_PUBLIC_API_BASE_URL: "https://api.example.com" },
  },
});
