# Mecha

A template for AI agent apps: a [Pydantic AI](https://pydantic.dev/docs/ai)
agent served by FastAPI, streamed over SSE into a Next.js chat UI built with
[shadcn/ui](https://ui.shadcn.com) (Base UI) and Tailwind CSS. Based on
[alloy](https://github.com/builtbystef/alloy): [Vite+](https://viteplus.dev)
(`vp`) and pnpm run the TypeScript side, [uv](https://docs.astral.sh/uv) and
ruff/ty run the Python side, and a generated, typed API client connects them.

The demo agent answers weather questions from live
[Open-Meteo](https://open-meteo.com) data (free, no API key, CC-BY 4.0) using
three tools: `search_locations` (geocoding), `get_weather_forecast`, and
`current_datetime`.

## Requirements

- Node 24 or newer (pinned in `.node-version`, enforced at install)
- uv (fetches the Python pinned in `.python-version` automatically)
- An LLM provider API key (Anthropic, OpenAI, and so on)

## Setup

```sh
pnpm install        # TS dependencies
uv sync             # Python venv + dependencies
vp config           # once after cloning: activates the pre-commit hook

cp apps/api/.env.example apps/api/.env   # then set MECHA_MODEL + provider key
pnpm dev            # FastAPI on :8000 + Next.js on :3000, together
```

`MECHA_MODEL` is a Pydantic AI model string like `anthropic:claude-sonnet-4-6`
or `openai:gpt-5.2`; set the matching `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`
too. `MECHA_MODEL=test` runs Pydantic AI's `TestModel`, which needs no key.

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

`apps/api/src/mecha_api/agent.py` defines a module-level `Agent`:

- **No fixed model.** The model string is passed per run, so tests swap in
  `TestModel` or `FunctionModel` with `agent.override()` and never call a
  provider (`ALLOW_MODEL_REQUESTS = False` in `tests/conftest.py`).
- **Typed dependencies.** Tools get an `httpx.AsyncClient` from
  `RunContext[AgentDeps]`; tests inject a `MockTransport` client.
- **Validated tool args.** Pydantic `Field` constraints on coordinates and
  forecast days. Bad values go back to the model as retries, and tools raise
  `ModelRetry` with a hint, such as "location not found".
- **Usage limits.** `UsageLimits` caps every run so tool-call loops can't run
  away.

### Streaming and persistence

`POST /api/conversations/{id}/messages` runs the agent with
`agent.run_stream_events()` and maps Pydantic AI events to a small SSE
vocabulary (`text-delta`, `tool-call`, `tool-result`, `done`, `error`). The
endpoint streams over POST, which `EventSource` can't do, so
`apps/web/hooks/use-chat.ts` reads it with `fetch` and a small parser.

Completed runs are appended to the database (`store.py`) as
`ModelMessagesTypeAdapter` JSON and passed back as `message_history=` on the
next turn. The UI builds its message list from that same history, so a refresh
restores the chat exactly.

[TanStack Query](https://tanstack.com/query/latest) owns the client's server
state: the conversation list and message history are queries (`lib/queries.ts`,
provider in `app/providers.tsx`), and the SSE stream writes into the message
cache with `setQueryData`, so fetched and streamed data render through one
path. Mutations invalidate the conversation list, since titles are assigned
server-side from the first message. The messages query is disabled mid-stream
so a background refetch can't overwrite messages that aren't saved yet.

## Database and migrations

`tables.py` declares the schema with SQLAlchemy's async ORM, and `store.py` is
the only thing that touches it. `MECHA_DATABASE_URL` picks the backend, so
going to production is a URL change rather than a rewrite:

```sh
MECHA_DATABASE_URL=postgresql+asyncpg://user:pass@host/mecha  # + uv add asyncpg
```

Alembic owns the schema, and `migrations/env.py` reads that same setting, so
the CLI and the app can't end up on different databases:

```sh
pnpm --filter api migrate:new "add users"   # diff tables.py → new revision
pnpm --filter api migrate                   # apply
```

The app also migrates itself at startup, which keeps `pnpm dev` one command.
Set `MECHA_MIGRATE_ON_STARTUP=false` and migrate from a release step once more
than one replica starts at a time.

Two details are worth keeping in a fork. A `connect` hook sets SQLite's
`foreign_keys`, `journal_mode=WAL`, and `busy_timeout`; without the first,
deleting a conversation leaves its runs behind. And `UtcDateTime` normalizes
timestamps both ways, since SQLite drops the offset and hands back a naive
datetime. `test_store.py` fails the build if `tables.py` and `migrations/`
disagree, the same way CI's `contract` job guards the OpenAPI client.

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

Nothing is exported until you set a sink: `LOGFIRE_TOKEN` for Logfire,
`OTEL_EXPORTER_OTLP_ENDPOINT` for any OTLP collector (Jaeger, Grafana,
Honeycomb, and so on). With neither, the app runs as it did untraced: no
network calls, no startup failure.

Prompts and replies are span attributes by default; set
`MECHA_TRACE_CONTENT=false` where conversations carry data that must not leave
the process. Stdlib log records attach to the active span, so
`logger.exception` lands on the trace that failed. `/api/health` is excluded,
since load balancers poll it.

## The typed API boundary

`apps/api`'s `build` dumps the FastAPI OpenAPI schema to `openapi.json`, and
`packages/api-client`'s `build` regenerates a typed fetch client from it with
[@hey-api/openapi-ts](https://heyapi.dev). Both are committed, and CI's
`contract` job fails on drift. Conversation CRUD goes through the client; only
the SSE stream uses raw `fetch`. After changing an endpoint:

```sh
pnpm build          # or: pnpm --filter api build && pnpm --filter @mecha/api-client build
```

In dev the browser only talks to Next.js: `next.config.ts` rewrites `/api/*` to
`http://localhost:8000` (override with `API_URL`), so there is no CORS setup.
Give new routes an `operation_id`; it becomes the generated function name.

## UI components

shadcn/ui with the Base UI (`@base-ui/react`) primitives, `base-nova` style.
Components are vendored source under `apps/web/components/ui`, added with
`npx shadcn@latest add <component>`. The `shadcn` package is a runtime
dependency, since `app/globals.css` imports its `tailwind.css`; it needs a
`trustPolicyExclude` for `semver` (see `pnpm-workspace.yaml`).

## Supply-chain policy

`pnpm-workspace.yaml` holds the full policy: `minimumReleaseAge` (4 days),
`strictDepBuilds` with an explicit `allowBuilds` (only `sharp`),
`blockExoticSubdeps`, `trustPolicy: no-downgrade`, `verifyDepsBeforeRun`, and
`engineStrict`. On the Python side, `uv.lock` is hash-pinned and CI installs
with `uv sync --locked`. Dependabot covers npm, uv, and GitHub Actions weekly
with a 4-day cooldown.

CI (`.github/workflows/ci.yml`) runs three least-privilege, SHA-pinned jobs:
`web` (vp check/test + builds), `api` (ruff, ty, pytest), and `contract`
(regenerate schema + client, fail on drift).

A pre-commit hook (`.vite-hooks/`) runs `vp check --fix` on staged files and
ruff on staged `*.py`. Only the hook is tracked, so run `vp config` once after
cloning to activate it.

## License

[MIT](LICENSE) © builtbystef
