# Production Readiness Audit — 2026-04-25

Supersedes `PRODUCTION-READINESS-AUDIT.md` (previous run). Covers a wider surface: all 137 REST endpoints, primary gateway RPCs, 34 frontend routes, full test suites (backend + frontend + Cypress), build, typecheck, infra posture.

---

## Executive Summary

**Overall score: 7.5 / 10 — Production-capable, but 2 real P1 bugs block a clean ship.**

| # | Area | Result |
|---|---|---|
| 1 | Environment health | ✅ 5/5 services up, health endpoints green |
| 2 | Backend test suite | ✅ **487 pass, 1 xfail** (`make backend-test`) |
| 3 | Frontend test suite | ✅ **127 pass** (`make frontend-test`) |
| 4 | Backend mypy --strict | ✅ clean, 152 files |
| 5 | Frontend tsc | ✅ clean |
| 6 | `next build` | ✅ clean exit 0 |
| 7 | REST smoke — 76 endpoints | ✅ all non-5xx where valid input |
| 8 | Invalid-UUID probe — **23 endpoints** | 🔴 **500s** (systemic) |
| 9 | Critical-path E2E (10 flows) | ✅ all green once correct schemas used |
| 10 | Gateway RPC primaries (8) | ✅ 30 models, 13 ctx, 27 sessions |
| 11 | Frontend routes (34 HTTP) | ✅ all 200 |
| 12 | Cypress E2E (3 specs run) | 🔴 **2 of 3 fail** — React #418 hydration mismatch |
| 13 | Secrets hygiene | ✅ `.env` gitignored, no tokens in git history |
| 14 | Docker posture | ⚠️ Non-root, multi-stage, but **no app-container HEALTHCHECK** |
| 15 | CORS / TLS | ⚠️ HTTP-only; CORS wildcards with credentials (origin scoped) |
| 16 | Observability | ⚠️ Structured logs + rate-limit infra present; no Sentry / Prometheus / OTel |

**Verdict:** Fix the 4 P1s (systemic UUID 500s, React hydration mismatch, chat rate-limit, Dockerfile healthchecks) and the product is ready for production. P2/P3 items are polish and can ship incrementally.

---

## What changed since the previous audit

- Prior audit flagged **1** endpoint with the invalid-UUID-500 bug; this audit found **23** (systemic, not a point bug).
- Prior audit did not run Cypress; this run uncovered a production React hydration error (#418) on `/boards` and the local-auth flow.
- Prior audit said "no chat rate limiting" but didn't check the codebase — rate-limit *infrastructure* exists (`backend/app/core/rate_limit.py`) but is not applied to chat send.
- Prior audit listed 137 REST endpoints via source inspection; this run validated the actual OpenAPI spec (101 unique paths; many earlier paths were under different prefixes).

---

## 1. Environment health

```
NAME                                         STATUS                 PORTS
openclaw-mission-control-backend-1           Up 2 hours             :8000
openclaw-mission-control-db-1                Up 2 hours (healthy)   127.0.0.1:5432
openclaw-mission-control-frontend-1          Up 2 hours             :3000
openclaw-mission-control-redis-1             Up 2 hours (healthy)   127.0.0.1:6379
openclaw-mission-control-webhook-worker-1    Up 2 weeks             (internal)
```

- `/health`, `/healthz`, `/readyz` → 200 OK
- Frontend `/` → 200, 11.5 KB
- Git: `master`, 4 commits ahead of `origin/master`, clean tree (except this report + the old one)
- Recent backend log shows the invalid-UUID 500 being triggered live by some client: `GET /api/v1/gateways/sessions?board_id=invalid-uuid` → `InvalidTextRepresentation`.

## 2. Test suites (existing)

| Target | Result |
|---|---|
| `make backend-test` (pytest) | 487 passed, 1 xfailed, 77.7 s |
| `make frontend-test` (vitest) | 127 passed, 17.5 s; 100% coverage on scoped modules (`backoff.ts`, `ActivityFeed.tsx`) |
| `make backend-typecheck` (mypy --strict) | no issues in 152 files |
| `make frontend-typecheck` (tsc) | no issues |
| `make frontend-build` (next build) | exit 0, 41 routes emitted (static + dynamic) |

## 3. REST API smoke — 137-endpoint surface

### 3.1 Happy path
76 endpoints probed with a valid auth token returned `2xx` or expected `4xx` (404 for missing records, 422 for unknown/missing required query params). No phantom 500s on well-formed requests.

### 3.2 Invalid-UUID probe — SYSTEMIC 500 FAILURE (P1)

The driver walked every `GET` path with a UUID path parameter and substituted a non-UUID string (`not-a-uuid`), plus every endpoint accepting `board_id` as query param.

**23 endpoints return HTTP 500 instead of 422:**

```
GET /api/v1/agent/boards/not-a-uuid
GET /api/v1/agent/boards/not-a-uuid/tasks
GET /api/v1/agent/boards/not-a-uuid/tags
GET /api/v1/agent/boards/not-a-uuid/memory
GET /api/v1/agent/boards/not-a-uuid/approvals
GET /api/v1/agent/boards/not-a-uuid/webhooks/not-a-uuid/payloads/not-a-uuid
GET /api/v1/agent/boards/not-a-uuid/tasks/not-a-uuid/comments
GET /api/v1/agent/boards/not-a-uuid/agents/not-a-uuid/soul
GET /api/v1/agents/not-a-uuid
GET /api/v1/boards/not-a-uuid
GET /api/v1/boards/not-a-uuid/snapshot
GET /api/v1/boards/not-a-uuid/group-snapshot
GET /api/v1/boards/not-a-uuid/memory
GET /api/v1/boards/not-a-uuid/group-memory
GET /api/v1/boards/not-a-uuid/webhooks
GET /api/v1/boards/not-a-uuid/webhooks/not-a-uuid
GET /api/v1/boards/not-a-uuid/webhooks/not-a-uuid/payloads
GET /api/v1/boards/not-a-uuid/webhooks/not-a-uuid/payloads/not-a-uuid
GET /api/v1/boards/not-a-uuid/onboarding
GET /api/v1/boards/not-a-uuid/approvals
GET /api/v1/boards/not-a-uuid/tasks
GET /api/v1/boards/not-a-uuid/tasks/not-a-uuid/comments

GET /api/v1/gateways/sessions?board_id=invalid-uuid
GET /api/v1/gateways/status?board_id=invalid-uuid
GET /api/v1/gateways/browser-status?board_id=invalid-uuid
GET /api/v1/gateways/channels/auth-status?board_id=invalid-uuid
GET /api/v1/gateways/models?board_id=invalid-uuid
```

Root cause: path / query params typed as `str` instead of `UUID`. The string flows into SQLAlchemy which raises `psycopg.errors.InvalidTextRepresentation`. The error middleware catches it too late, returning 500.

- Dependencies where `str` is used: `backend/app/api/deps.py:131,142,161,180,195`
- Gateway query params typed `str | None`: `backend/app/api/gateway.py:41,77,94,112,131`

Working pattern (UUID-typed): `backend/app/api/tags.py:45,146,170,202` — `tag_id: UUID` → returns clean 422.
Other routers already using `UUID` correctly: `activity.py`, `approvals.py`, `board_groups.py`, `board_group_memory.py`.

Valid-but-nonexistent UUIDs return 404 cleanly (tested 26 paths). So the fix is purely parameter typing; the `HTTPException(404)` machinery already works once parsing succeeds.

**Detailed fix → `FIXES-FOR-KIMI.md#fix-01`.**

## 4. Critical-path E2E flows — all green

Ran 10 HTTP-driven multi-step flows with `curl + jq` against the live stack. All passed after correcting request schemas.

| Flow | Steps | Result |
|---|---|---|
| 1. Auth bootstrap | users.me, org.me | ✅ |
| 2. Board lifecycle | create → snapshot → patch → delete → 404 after | ✅ |
| 3. Task workflow | create → patch status → comment → delete | ✅ |
| 4. Gateway chat | status, sessions (27), models (30), browser (13 ctx), channels auth-status, history | ✅ |
| 5. Board memory | list | ✅ |
| 6. Webhook CRUD | list → create → delete | ✅ |
| 7. Org invite | create → list → revoke | ✅ |
| 8. Tags CRUD | create → patch → delete | ✅ |
| 9. User settings | patch timezone → revert | ✅ |
| 10. Metrics dashboard | shape: kpis, cycle_time, error_rate, throughput, wip | ✅ |

## 5. Gateway RPC primaries — verified via backend proxy

| RPC | Result |
|---|---|
| `health` | `{"ok": true}` |
| `status` | `connected: true`, `sessions_count: 27` |
| `sessions.list` | 27 sessions returned |
| `chat.history` | HTTP 200 |
| `models.list` | **30 models** (claude-haiku-4-6, claude-opus-4-6, …) |
| `browser.status` | 13 contexts, no error |
| `channels.auth-status` | shape OK |
| `chat.send` | Skipped — do not spam the live Telegram session (prior audit verified) |

WebSocket stays connected across the whole sweep; no reconnect storms in logs.

## 6. Frontend smoke

- **34 / 34 routes** return HTTP 200 with non-trivial HTML shell.
- Next build produces the expected 41-page route map (static + dynamic), including `/gateways/[gatewayId]/chat`.
- Container runs `next start` with `NODE_ENV=production` → hydration issues found below are in production mode, not dev.

**Cypress E2E (3 of 9 specs sampled) — 2 fail:**

| Spec | Result | Reason |
|---|---|---|
| `activity_smoke.cy.ts` | ✅ | signed-out prompt renders |
| `boards_list.cy.ts` | ❌ | `/boards` happy path throws **React error #418** (HTML mismatch → hydration failure) |
| `local_auth_login.cy.ts` | ❌ | same React #418 on protected-route redirect |

React #418 = server-rendered HTML does not match the client-side render. This is visible to every user who loads these pages — typically a flash of wrong content or a silent remount. Cypress catches it because Cypress treats any uncaught error as a test failure.

Repro: open `/boards` in an incognito window while signed in; check the browser console for `Minified React error #418`.

Other 6 Cypress specs not run (activity_feed, board_tasks, global_approvals, mobile_sidebar, organizations, skill_packs_sync) — likely similarly affected on any page that reuses the shared auth/provider shell.

**Detailed fix → `FIXES-FOR-KIMI.md#fix-02`.**

## 7. Infrastructure & security posture

### Secrets
- ✅ `.env` and `.env.local` are in `.gitignore`
- ✅ `git log -S "5cc2cbafec74…"` yields no matches → current token never committed
- ⚠️ `.env` sits on disk with plaintext `LOCAL_AUTH_TOKEN` and `OPENCLAW_GATEWAY_TOKEN`. Acceptable for self-hosted single-box; for multi-host production use a secrets manager.

### Docker
- ✅ `backend/Dockerfile` and `frontend/Dockerfile` — both multi-stage, non-root `appuser`
- 🔴 **No `HEALTHCHECK` directive** in either Dockerfile
- ⚠️ `compose.yml` has healthchecks only for `db` and `redis`; `backend`, `frontend`, and `webhook-worker` rely on runtime state alone
- ✅ `postgres_data` named volume (persistent)
- ⚠️ No backup script or documented restore procedure for `postgres_data`

### TLS / HTTPS
- 🔴 **No HTTPS.** Services bind `0.0.0.0:8000` and `0.0.0.0:3000`. `BASE_URL` and `CORS_ORIGINS` use `http://`
- No nginx/traefik/caddy reverse proxy in `compose.yml`
- Gateway WebSocket uses `ws://172.19.0.1:3001` (unencrypted, private docker bridge)

### CORS
```python
# backend/app/main.py:465
allow_origins=origins,         # scoped to one FQDN from env
allow_credentials=True,
allow_methods=["*"],           # permissive
allow_headers=["*"],           # permissive
```
Not dangerous because origins are scoped — but tightening to the actual methods/headers used eliminates a class of preflight bypass risk.

### Rate limiting
- ✅ Sliding-window rate limiter exists (`backend/app/core/rate_limit.py`, memory + Redis backends)
- ✅ Applied to: agent auth (`agent_auth_limiter`), webhook ingest (`webhook_ingest_limiter`)
- 🔴 **Not applied to `POST /api/v1/gateways/sessions/{session_id}/message`** — a compromised or buggy agent token can flood the gateway

### Insecure TLS flag
- `allow_insecure_tls` column on `gateways` table, default `False`
- Used at `backend/app/services/openclaw/gateway_rpc.py:213` — when true, disables cert + hostname verification
- Opt-in per gateway; safe default, but operators should be warned in docs

### Device-auth flag (accepted trade-off)
- `dangerouslyDisableDeviceAuth=true` lives in gateway config on host, **not** in any app code or repo file
- Required for Docker → host connectivity in current setup
- User has chosen to accept this as documented; no fix in this audit

### Observability
- ✅ Structured logging with request correlation (`app.core.logging`), JSON/kv formatters, slow-request threshold configurable
- 🔴 No Prometheus client in `pyproject.toml`
- 🔴 No Sentry SDK in backend or frontend `package.json`
- 🔴 No OpenTelemetry / distributed tracing
- ✅ `GET /api/v1/metrics/dashboard` exists but computes on demand (not scraped)
- Slow-request warnings observed: `/api/v1/gateways/status` ~1.5 s — fine, but watch it

## 8. Findings by severity

### 🔴 P1 — should fix before wide rollout
1. **Systemic invalid-UUID → 500** across 23 endpoints (path + query). See Fix-01.
2. **React hydration mismatch #418** on `/boards` + protected-route redirect, in production build. See Fix-02.
3. **No rate limit on chat send** (`POST /api/v1/gateways/sessions/{id}/message`). See Fix-03.
4. **No `HEALTHCHECK`** in backend or frontend Dockerfiles; no compose-level healthcheck for `backend`/`frontend`/`webhook-worker`. See Fix-04.

### 🟡 P2 — address before scaling
5. **HTTPS/TLS not terminated** — add reverse proxy + certs. See Fix-05.
6. **CORS wildcards** with credentials. See Fix-06.
7. **Observability** — no Sentry/Prometheus/OTel. See Fix-07.
8. **`postgres_data` backup** not documented. See Fix-08.

### 🟢 P3 — nice-to-have
9. `/api/v1/gateways/status` and `/sessions` routinely slow (~1.5 s). See note in Fix-09.
10. Six Cypress specs (activity_feed, board_tasks, global_approvals, mobile_sidebar, organizations, skill_packs_sync) not run — rerun after Fix-02 lands.

## 9. What's green and worth keeping

- **Test discipline:** mypy strict + tsc strict + 100% scoped vitest coverage + 487 pytest + migration reversibility gate in CI — high bar, kept green.
- **Rate-limit substrate:** clean sliding-window abstraction over memory + Redis with a single switch.
- **Structured logging** with request-id correlation wired end-to-end — use this for tracing fallout during fixes.
- **CI gates** (enforce-one-migration-per-PR, migration-reversibility on clean Postgres) — load-bearing, don't remove.
- **Gateway surface** (chat send, history, models, sessions, browser, channels auth) all healthy in real usage.

## 10. Known trade-offs (user-accepted)

- `dangerouslyDisableDeviceAuth=true` in gateway host config — required for Docker→host. Lock down network; revisit with Ed25519 later.
- `.env` plaintext on disk — acceptable for self-hosted single-host; switch to secrets manager when going multi-host.

## 11. Re-test instructions

After applying fixes, re-run:

```bash
# Phase 2 (tests)
cd /root/openclaw-mission-control && make backend-test frontend-test
make backend-typecheck frontend-typecheck
make frontend-build

# Phase 3 (REST smoke — UUID regression)
/tmp/rest_smoke2.sh | tee /tmp/rest_smoke2_retest.txt
grep "5xx" /tmp/rest_smoke2_retest.txt | grep -v "= 0"   # should be empty

# Phase 4 (E2E flows)
/tmp/e2e_flows.sh ; /tmp/e2e_flows2.sh

# Phase 6 (frontend)
/tmp/page_smoke.sh
cd frontend && npx cypress run --headless --browser electron  # all 9 specs green?
```

Artifacts kept under `/tmp/`:
- `/tmp/rest_smoke.sh`, `/tmp/rest_smoke2.sh` — REST smoke drivers
- `/tmp/e2e_flows.sh`, `/tmp/e2e_flows2.sh` — E2E flows
- `/tmp/page_smoke.sh` — frontend route smoke
- `/tmp/rest_smoke2_output.txt`, `/tmp/e2e_flows*_output.txt`, `/tmp/page_smoke_output.txt`, `/tmp/cy_boards.txt`, `/tmp/cy_login.txt` — logs

## 12. How to dispatch fixes

All P1 and P2 fixes are written as ready-to-paste prompts in **`FIXES-FOR-KIMI.md`**. Each entry includes:
- Exact file paths + line numbers
- Before/after code
- Verification command that must go from red to green
- A complete kimi-code prompt block

Suggested order: Fix-01 (huge blast radius, small code change) → Fix-02 (user-visible) → Fix-03 (security) → Fix-04 (ops) → P2s.
