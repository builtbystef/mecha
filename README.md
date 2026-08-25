# Mecha

An AI-agent application template: a [Pydantic AI](https://pydantic.dev/docs/ai)
agent served by FastAPI, streamed over SSE into a Next.js chat UI built with
[shadcn/ui](https://ui.shadcn.com) (Base UI) and Tailwind CSS. Derived from
[alloy](https://github.com/builtbystef/alloy): [Vite+](https://viteplus.dev)
(`vp`) and pnpm run the TypeScript side; [uv](https://docs.astral.sh/uv) and
ruff/ty run the Python side, with a generated, fully typed API client
connecting the two.

The demo agent answers weather questions with live
[Open-Meteo](https://open-meteo.com) data (free, no API key, CC-BY 4.0) via
three tools: `search_locations` (geocoding), `get_weather_forecast`, and
`current_datetime`.

## Requirements

- Node ≥ 24 (pinned in `.node-version`, enforced at install)
- uv (fetches the Python pinned in `.python-version` automatically)
- An LLM provider API key (Anthropic, OpenAI, …)

## Setup

```sh
pnpm install        # TS dependencies
uv sync             # Python venv + dependencies
vp config           # once after cloning: activates the pre-commit hook

cp apps/api/.env.example apps/api/.env   # then set MECHA_MODEL + provider key
pnpm dev            # FastAPI on :8000 + Next.js on :3000, together
```

The agent is provider-agnostic: `MECHA_MODEL` is a Pydantic AI model string
like `anthropic:claude-sonnet-4-6` or `openai:gpt-5.2`, and the matching
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` must be set. `MECHA_MODEL=test` runs
Pydantic AI's `TestModel` — no key needed, useful for trying the app without
a provider.

## Layout

```text
├── apps/
│   ├── api/            # FastAPI + the Pydantic AI agent
│   │   ├── src/mecha_api/
│   │   │   ├── agent.py    # Agent, deps dataclass, tools
│   │   │   ├── weather.py  # typed Open-Meteo client
│   │   │   ├── chat.py     # conversation CRUD + SSE streaming endpoint
│   │   │   ├── tables.py   # SQLAlchemy tables (what Alembic diffs against)
│   │   │   ├── store.py    # conversation + message-history persistence
│   │   │   ├── migrate.py  # runs Alembic from the app at startup
│   │   │   ├── observability.py # OpenTelemetry tracing
│   │   │   └── config.py   # MECHA_* settings
│   │   ├── migrations/ # Alembic revisions
│   │   └── alembic.ini
│   └── web/            # Next.js chat UI (shadcn/ui Base UI + Tailwind v4)
├── packages/
│   └── api-client/     # TS client generated from the FastAPI OpenAPI schema
├── tsconfig/           # shared TypeScript presets (base/node/browser/library)
├── pnpm-workspace.yaml # TS workspace + supply-chain policy
└── pyproject.toml      # uv workspace + ruff/pytest config
```

## Commands

```sh
pnpm dev            # both servers
pnpm check          # format + lint + typecheck, both languages
pnpm check:fix
pnpm test           # Vitest + pytest (agent tests run against fake models)
pnpm build          # export schema → generate client → next build, in order
pnpm run ci         # everything CI runs (bare `pnpm ci` is pnpm's clean-install)

pnpm --filter api migrate              # alembic upgrade head
pnpm --filter api migrate:new "add x"  # autogenerate a revision from tables.py
```

## The agent

`apps/api/src/mecha_api/agent.py` defines a module-level `Agent` with:

- **No fixed model** — the settings string is passed per run, so tests swap in
  `TestModel`/`FunctionModel` via `agent.override()` and never hit a provider
  (`ALLOW_MODEL_REQUESTS = False` in `tests/conftest.py`).
- **Typed dependencies** — tools receive an `httpx.AsyncClient` through
  `RunContext[AgentDeps]`; tests inject a `MockTransport` client.
- **Validated tool args** — pydantic `Field` constraints on coordinates and
  forecast days; violations are fed back to the model as retries, and tools
  raise `ModelRetry` with actionable hints (e.g. location not found).
- **Usage limits** — each run is capped (`UsageLimits`) to stop tool-call
  loops.

### Streaming and persistence

`POST /api/conversations/{id}/messages` runs the agent with
`agent.run_stream_events()` and translates Pydantic AI events into a small SSE
vocabulary (`text-delta`, `tool-call`, `tool-result`, `done`, `error`) that
`apps/web/hooks/use-chat.ts` reads with `fetch` and a small SSE parser (the
endpoint streams over POST, which `EventSource` can't do).

Completed runs are appended to the database (`store.py`) as
`ModelMessagesTypeAdapter` JSON; the accumulated history is passed back as
`message_history=` on the next turn. The UI's message list is built from that
same history, so a refresh restores the chat exactly.

On the client, [TanStack Query](https://tanstack.com/query/latest) owns the
server state: the conversation list and message history are queries (shared
`queryOptions` in `lib/queries.ts`, provider in `app/providers.tsx`), and the
SSE stream writes into the message cache with `setQueryData`, so fetched and
streamed data render through one path. Mutations invalidate the conversation
list — titles are assigned server-side from the first message. The messages
query is disabled while a stream is in flight so a background refetch can't
overwrite the not-yet-persisted messages.

## Database and migrations

`tables.py` declares the schema with SQLAlchemy's async ORM; `store.py` is
the only thing that touches it. `MECHA_DATABASE_URL` picks the backend, so
production means a URL change rather than a rewrite:

```sh
MECHA_DATABASE_URL=postgresql+asyncpg://user:pass@host/mecha  # + uv add asyncpg
```

Alembic owns the schema. `migrations/env.py` reads that same setting, so the
CLI and the app can't end up on different databases:

```sh
pnpm --filter api migrate:new "add users"   # diff tables.py → new revision
pnpm --filter api migrate                   # apply
```

The app also migrates itself at startup, which keeps `pnpm dev` a single
command. Set `MECHA_MIGRATE_ON_STARTUP=false` and migrate from a release
step once more than one replica starts at a time.

Two details worth keeping if you fork this: a `connect` hook sets SQLite's
`foreign_keys`, `journal_mode=WAL`, and `busy_timeout` — without the first,
deleting a conversation silently leaves its runs behind — and `UtcDateTime`
normalizes timestamps in both directions, since SQLite drops the offset and
hands back a naive datetime. `test_store.py` fails the build if `tables.py`
and `migrations/` ever disagree, the same way CI's `contract` job guards the
OpenAPI client.

## Tracing

`observability.py` sets up OpenTelemetry at import, using
[Logfire](https://pydantic.dev/logfire) as the SDK. One run produces a full
trace:

```text
POST /api/conversations/{id}/messages   ← FastAPI
└── chat turn                           ← conversation id, tokens, tool calls
    └── invoke_agent agent               ← pydantic-ai
        ├── chat anthropic:claude-…      ← prompt, reply, usage per request
        └── execute_tool search_locations ← args and result
```

Nothing is exported until a sink is set: `LOGFIRE_TOKEN` sends to Logfire,
`OTEL_EXPORTER_OTLP_ENDPOINT` to any OTLP collector (Jaeger, Grafana,
Honeycomb, …). With neither, the app runs exactly as it did untraced — no
network calls, no startup failure.

Prompts and replies are span attributes by default; set
`MECHA_TRACE_CONTENT=false` where conversations carry data that must not
leave the process. Stdlib log records are bridged onto the active span, so
`logger.exception` lands on the trace that failed. `/api/health` is excluded,
since load balancers poll it.

## The typed API boundary

`apps/api`'s `build` dumps the FastAPI OpenAPI schema to `openapi.json`;
`packages/api-client`'s `build` regenerates a typed fetch client from it
([@hey-api/openapi-ts](https://heyapi.dev)). Both are committed, and CI's
`contract` job fails on any drift. Conversation CRUD in the web app goes
through this client; only the SSE stream is read with raw `fetch`. After
changing an endpoint:

```sh
pnpm build          # or: pnpm --filter api build && pnpm --filter @mecha/api-client build
```

In dev the browser only talks to Next.js — `next.config.ts` rewrites `/api/*`
to `http://localhost:8000` (override with `API_URL`), so there is no CORS
setup. Give new FastAPI routes an `operation_id`; it becomes the generated
function name.

## UI components

shadcn/ui with the Base UI (`@base-ui/react`) primitives, `base-nova` style:
components are vendored source under `apps/web/components/ui`, added via
`npx shadcn@latest add <component>`. The `shadcn` package itself is a runtime
dependency (its `tailwind.css` is imported in `app/globals.css`); it needs a
`trustPolicyExclude` for `semver` — see `pnpm-workspace.yaml`.

## Supply-chain policy

`pnpm-workspace.yaml` carries the full policy: `minimumReleaseAge` (4 days),
`strictDepBuilds` + explicit `allowBuilds` (only `sharp`),
`blockExoticSubdeps`, `trustPolicy: no-downgrade` (with a reviewed
`trustPolicyExclude` for `semver`), `verifyDepsBeforeRun`, and
`engineStrict`. The Python side mirrors it: `uv.lock` is hash-pinned and CI
installs with `uv sync --locked`; Dependabot covers npm, uv, and GitHub
Actions weekly with a 4-day cooldown.

CI (`.github/workflows/ci.yml`) runs three least-privilege, SHA-pinned jobs:
`web` (vp check/test + builds), `api` (ruff, ty, pytest), and `contract`
(regenerate schema + client, fail on drift).

A pre-commit hook (`.vite-hooks/`) runs `vp check --fix` on staged files and
ruff on staged `*.py`. Only the hook itself is tracked — run `vp config` once
after cloning to activate it.

## License

[MIT](LICENSE) © builtbystef
