# Mecha

A Python + TypeScript template: FastAPI backend, Next.js frontend, and a
generated, fully typed API client bonding the two. [Vite+](https://viteplus.dev)
(`vp`) and pnpm run the TypeScript side; [uv](https://docs.astral.sh/uv) and
ruff/ty run the Python side. One command vocabulary covers both.

## Requirements

- Node ≥ 24 (pinned in `.node-version`, enforced at install)
- uv (fetches the Python pinned in `.python-version` automatically)

## Layout

```text
├── apps/
│   ├── api/            # FastAPI
│   └── web/            # Next.js
├── packages/
│   └── api-client/     # TS client generated from the FastAPI OpenAPI schema
├── tools/
├── tsconfig/           # shared TypeScript presets (base/node/browser/library)
├── pnpm-workspace.yaml # TS workspace + supply-chain policy
└── pyproject.toml      # uv workspace + ruff/pytest config
```

## Commands

```sh
pnpm install        # TS dependencies
uv sync             # Python venv + dependencies
vp config           # once after cloning: activates the pre-commit hook

pnpm dev            # FastAPI on :8000 + Next.js on :3000, together
pnpm check          # format + lint + typecheck, both languages
pnpm check:fix
pnpm test           # Vitest + pytest
pnpm build          # export schema → generate client → next build, in order
pnpm run ci         # everything CI runs (bare `pnpm ci` is pnpm's clean-install)
```

Root scripts fan out: `vp check`/`vp test` cover TypeScript, then
`vp run -r <script>` runs each project's own `check`/`test`/`build` — which is
how the Python tools (ruff, ty, pytest) join the same commands. `apps/api` has
a thin `package.json` whose scripts call `uv run …`; that shim is what lets
`vp run` cache and order Python tasks alongside TS ones.

## The typed API boundary

`apps/api`'s `build` dumps the FastAPI OpenAPI schema to `openapi.json`;
`packages/api-client`'s `build` regenerates a typed fetch client from it
([@hey-api/openapi-ts](https://heyapi.dev)). The client depends on `api` in its
`package.json`, so `pnpm build` always runs them in order. Both the schema and
the generated client are committed — a fresh clone typechecks without running
Python, and CI's `contract` job regenerates both and fails on any diff, so they
can never drift from the backend.

After changing an endpoint:

```sh
pnpm build          # or: pnpm --filter api build && pnpm --filter @mecha/api-client build
```

In dev, the browser only ever talks to Next.js — `next.config.ts` rewrites
`/api/*` to `http://localhost:8000` (override with `API_URL`), so there is no
CORS setup. Give new FastAPI routes an `operation_id`; it becomes the generated
function name.

## Adding projects

TypeScript projects drop into `apps/*`, `packages/*`, or `tools/*` — the
workspace globs already cover them; extend a preset from `tsconfig/` as in
carbon-fiber. Python projects also get listed in `[tool.uv.workspace] members`
in the root `pyproject.toml`, plus a package.json shim with `check`/`test`
scripts if they should participate in the root commands.

Two TypeScript-version caveats, both from the TS 7 (tsgo) catalog default:

- `packages/api-client` pins TypeScript 5 locally — `@hey-api/openapi-ts`
  needs the old in-process compiler API.
- `apps/web` sets `experimental.useTypeScriptCli` so `next build` typechecks
  through the TS 7 CLI.

## Supply-chain policy

`pnpm-workspace.yaml` carries the full carbon-fiber policy: `minimumReleaseAge`
(4 days), `strictDepBuilds` + explicit `allowBuilds` (only `sharp`),
`blockExoticSubdeps`, `trustPolicy: no-downgrade`, `verifyDepsBeforeRun`, and
`engineStrict`. The Python side mirrors it: `uv.lock` is hash-pinned and CI
installs with `uv sync --locked`; Dependabot covers npm, uv, and GitHub Actions
weekly with a 4-day cooldown.

CI (`.github/workflows/ci.yml`) runs three least-privilege, SHA-pinned jobs:
`web` (vp check/test + builds), `api` (ruff, ty, pytest), and `contract`
(regenerate schema + client, fail on drift).

A pre-commit hook (`.vite-hooks/`) runs `vp check --fix` on staged files and
ruff on staged `*.py`. Only the hook itself is tracked — run `vp config` once
after cloning to activate it.

## License

[MIT](LICENSE) © builtbystef
