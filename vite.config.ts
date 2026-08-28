import { defineConfig } from "vite-plus";

export default defineConfig({
  staged: {
    "*": "vp check --fix",
    "*.py": ["uv run ruff format", "uv run ruff check --fix"],
  },
  fmt: {
    ignorePatterns: ["**/src/generated/**", "**/openapi.json", "**/.agents/**", "**/.claude/**"],
  },
  lint: {
    plugins: ["typescript"],
    options: {
      typeAware: true,
      typeCheck: true,
    },
    ignorePatterns: [
      "**/dist/**",
      "**/coverage/**",
      "**/.next/**",
      "**/src/generated/**",
      "**/.agents/**",
      "**/.claude/**",
    ],
    overrides: [
      {
        // `plugins` in an override replaces the base list, so repeat it.
        files: ["**/*.test.ts", "**/*.spec.ts"],
        plugins: ["typescript", "vitest"],
      },
    ],
  },
  test: {
    passWithNoTests: true,
  },
  pack: {
    dts: true,
    sourcemap: true,
  },
  run: {
    cache: true,
  },
});
