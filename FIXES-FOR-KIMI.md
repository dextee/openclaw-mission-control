# Fixes for Kimi-Code — openclaw-mission-control

Actionable fix queue derived from `PRODUCTION-AUDIT-2026-04-25.md`. Each entry is self-contained: file paths, exact changes, verification, and a ready-to-paste prompt for kimi-code.

**Dispatch order:** FIX-01 → FIX-02 → FIX-03 → FIX-04 (all P1) → P2s in any order.

---

## FIX-01 — Systemic: invalid UUID → 500 on 23 endpoints

**Severity:** 🔴 P1
**Blast radius:** wide (all board-scoped agent + admin endpoints; 5 gateway query endpoints)
**Effort:** ~15 minutes of edits + re-run tests

### Root cause

Board / agent / group / webhook / etc. path and query parameters are typed as plain `str` in FastAPI handlers. When a client passes `not-a-uuid`, FastAPI accepts the string, it flows into SQLAlchemy/psycopg, which raises `InvalidTextRepresentation`, bubbles up as 500.

Correct pattern (already used by `tags.py`, `activity.py`, `approvals.py`, `board_groups.py`): type the parameter as `uuid.UUID`. FastAPI validates at the boundary and returns `422` automatically.

### Files and exact changes

**File 1: `backend/app/api/deps.py`** — change 5 function signatures.

Top of file should already import `UUID`:
```python
from uuid import UUID
```

Then, at lines 131, 142, 161, 180, 195 (five dependency functions: `get_board_or_404`, `get_board_for_actor_read`, `get_board_for_actor_write`, `get_board_for_user_read`, `get_board_for_user_write`):

```diff
-async def get_board_or_404(
-    board_id: str,
+async def get_board_or_404(
+    board_id: UUID,
     session: AsyncSession = SESSION_DEP,
 ) -> Board:
```

Apply the same `str` → `UUID` change for the other four functions. Do **not** change the body — `Board.objects.by_id(board_id)` accepts `object`, a `UUID` instance is fine.

**File 2: `backend/app/api/gateway.py`** — change 5 query-param declarations.

Add at top if not present:
```python
from uuid import UUID
```

At lines 41, 77, 94, 112, 131 (query param declarations across `gateways_status`, `gateway_sessions`, `gateway_session_detail`, `gateway_session_history`, `send_gateway_session_message`):

```diff
-    board_id: str | None = Query(default=None),
+    board_id: UUID | None = Query(default=None),
```
or where the BOARD_ID_QUERY alias is used:
```diff
-    board_id: str | None = BOARD_ID_QUERY,
+    board_id: UUID | None = BOARD_ID_QUERY,
```

If `BOARD_ID_QUERY` is defined in the same file as `Query(default=None, description=...)` typed against `str | None`, also update that alias declaration accordingly. Grep for it with `grep -n BOARD_ID_QUERY backend/app/api/gateway.py` and retype the default.

### Do NOT touch

- `backend/app/api/deps.py` code bodies (keep `Board.objects.by_id(board_id)` as-is — UUID is accepted).
- Other routers already using `UUID` correctly.

### Verification

```bash
cd /root/openclaw-mission-control
make backend-test                # should still be 487 passed
make backend-typecheck           # should still be clean

# The smoke script from the audit:
/tmp/rest_smoke2.sh > /tmp/retest.txt
grep "5xx" /tmp/retest.txt
# Expected: "5xx   = 0"  (was 22)

# Spot check:
source .env
AUTH="Authorization: Bearer $LOCAL_AUTH_TOKEN"
curl -sS -o /dev/null -w "%{http_code}\n" -H "$AUTH" "http://localhost:8000/api/v1/boards/not-a-uuid"
# Expected: 422  (was 500)

curl -sS -o /dev/null -w "%{http_code}\n" -H "$AUTH" "http://localhost:8000/api/v1/gateways/sessions?board_id=invalid-uuid"
# Expected: 422  (was 500)
```

### Prompt to paste into kimi-code

````
Fix the systemic "invalid UUID returns 500" bug in openclaw-mission-control backend.

Root cause: 5 dependency functions in `backend/app/api/deps.py` and 5 query-param declarations in `backend/app/api/gateway.py` type `board_id` as `str` instead of `uuid.UUID`. FastAPI therefore accepts non-UUID input, which later crashes SQLAlchemy.

Task:

1. In `backend/app/api/deps.py`, ensure `from uuid import UUID` is imported. Change the parameter type from `board_id: str` to `board_id: UUID` in these 5 functions (lines 131, 142, 161, 180, 195):
   - `get_board_or_404`
   - `get_board_for_actor_read`
   - `get_board_for_actor_write`
   - `get_board_for_user_read`
   - `get_board_for_user_write`
   Do NOT modify the function bodies.

2. In `backend/app/api/gateway.py`, ensure `from uuid import UUID` is imported. Change every `board_id: str | None` query-param declaration to `board_id: UUID | None` at lines 41, 77, 94, 112, 131. If a `BOARD_ID_QUERY` alias exists in this file, retype its default-returning `Query(...)` to `UUID | None` as well. Do NOT modify handler bodies.

3. Run `cd backend && uv run mypy` — must stay clean.
4. Run `cd backend && uv run pytest` — all 487 tests must still pass.
5. Verify the bug is fixed:
   ```
   source /root/openclaw-mission-control/.env
   AUTH="Authorization: Bearer $LOCAL_AUTH_TOKEN"
   curl -sS -o /dev/null -w "%{http_code}\n" -H "$AUTH" http://localhost:8000/api/v1/boards/not-a-uuid
   # expected 422
   curl -sS -o /dev/null -w "%{http_code}\n" -H "$AUTH" "http://localhost:8000/api/v1/gateways/sessions?board_id=invalid-uuid"
   # expected 422
   ```

Do not change any other files. Do not add error-handling branches. Do not touch query bodies. Submit the diff when tests are green.
````

---

## FIX-02 — React hydration mismatch (#418) on /boards and local-auth flow

**Severity:** 🔴 P1
**Blast radius:** every user loading `/boards` or hitting protected-route auth redirect
**Effort:** ~30-60 min investigation + targeted fix (depends on source of mismatch)

### Evidence

Cypress spec `boards_list.cy.ts` "happy path" throws uncaught `Minified React error #418` (HTML mismatch) in production build. Same error in `local_auth_login.cy.ts`. Container runs `next start` with `NODE_ENV=production`, so this is not a dev-mode artifact.

React #418: "Hydration failed because the server rendered HTML didn't match the client." Usually one of:
- Using `typeof window !== 'undefined'` / `navigator` / `localStorage` during render, producing different output on server vs client.
- Date/time formatting with client-locale on the server.
- Feature-flag / auth-state detection that differs between SSR and CSR.
- Third-party component that renders non-deterministically.

### Where to look first

Both failing routes share the `AuthProvider`:
- `frontend/src/components/providers/AuthProvider.tsx` — Clerk + local-auth fallback. Likely culprit: reading `localStorage` for local-auth token during render.
- `frontend/src/auth/redirects.ts` — referenced by failing specs.
- `frontend/src/app/boards/page.tsx` — the specific failing route.
- `frontend/src/components/organisms/LocalAuthLogin.tsx` — used in sign-in flow.

Suggested investigation (kimi should do this, then propose fix):

1. Run `cd frontend && NODE_ENV=development npm run dev` in a terminal.
2. Open `/boards` while signed in. Watch the browser console — development React prints the full, non-minified error with the exact component and the mismatched HTML snippet.
3. Grep for synchronous `localStorage` / `sessionStorage` / `window` reads within render functions (not inside `useEffect`) in the auth provider and components rendered on these routes:
   ```
   grep -rn "localStorage\|sessionStorage\|typeof window" frontend/src/components/providers frontend/src/auth frontend/src/app/boards/page.tsx
   ```
4. The fix is usually one of:
   - Wrap the client-only logic in `useEffect` and hold initial render to a consistent placeholder.
   - Use Next's `dynamic(..., { ssr: false })` for the offending child component.
   - For the auth provider: render the loading / skeleton shell on the server, only let the real identity-aware UI hydrate after `useEffect` resolves.

### Verification

```bash
cd /root/openclaw-mission-control/frontend
# After fix, rerun the two failing specs and all three must pass:
bash ../scripts/with_node.sh --cwd . npx cypress run --headless --browser electron \
  --spec "cypress/e2e/boards_list.cy.ts,cypress/e2e/local_auth_login.cy.ts,cypress/e2e/activity_smoke.cy.ts"
# Expected: 3 passing, 0 failing, 0 screenshots of failures.

# Manual: open http://localhost:3000/boards in a browser tab while signed-in,
# open DevTools console. Expected: no "Minified React error #418".
```

### Prompt to paste into kimi-code

````
Fix React hydration mismatch (error #418) in openclaw-mission-control frontend. Two Cypress specs currently fail with this error in production build:
  - cypress/e2e/boards_list.cy.ts ("happy path")
  - cypress/e2e/local_auth_login.cy.ts

The frontend container runs `next start` with NODE_ENV=production on localhost:3000, connected to the backend on localhost:8000. Live token in .env. Hydration error happens on /boards and on the protected-route auth redirect.

Task:

1. Reproduce in dev mode to see the unminified error:
   - `cd frontend && npm run dev` in a separate terminal.
   - Open http://localhost:3000/boards while signed in (local auth token in .env).
   - Capture the exact component name and mismatched HTML from the browser console.

2. Identify the mismatch. Most likely culprits:
   - `frontend/src/components/providers/AuthProvider.tsx` — reads localStorage synchronously during render.
   - `frontend/src/auth/redirects.ts` — produces different output server vs client.
   - Any component on `/boards` that calls `typeof window !== 'undefined'` or `localStorage.*` inside a render function.

3. Apply a minimal fix. Typical patterns:
   - Move the client-only read into `useEffect` and initialize state to a server-safe value.
   - Mark the offending child component as client-only via `dynamic(() => import(...), { ssr: false })`.
   - Render a loading skeleton on first paint and only hydrate the identity-dependent UI after `useEffect`.

4. Re-run the three failing specs:
   ```
   cd frontend
   bash ../scripts/with_node.sh --cwd . npx cypress run --headless --browser electron \
     --spec "cypress/e2e/boards_list.cy.ts,cypress/e2e/local_auth_login.cy.ts,cypress/e2e/activity_smoke.cy.ts"
   ```
   All three must pass.

5. Run all 9 Cypress specs to confirm no new regressions:
   ```
   bash ../scripts/with_node.sh --cwd . npx cypress run --headless --browser electron
   ```

6. Run `make frontend-test frontend-typecheck frontend-build` — must stay clean.

Do not suppress React error boundaries or silence hydration warnings with `suppressHydrationWarning` unless you can argue in writing why the mismatch is cosmetically unavoidable. Actually fix the root cause.
````

---

## FIX-03 — Apply rate limit to chat-send endpoint

**Severity:** 🔴 P1 (security / abuse)
**Effort:** 15 min

### Root cause

`POST /api/v1/gateways/sessions/{session_id}/message` has no rate limiter. A compromised agent token or buggy agent can flood the gateway (and downstream LLM providers, burning cost). The codebase already has sliding-window rate-limit infra (`backend/app/core/rate_limit.py`) wired to `agent_auth_limiter` and `webhook_ingest_limiter`. Add a third limiter and apply it to the chat-send handler.

### File and change

**File: `backend/app/core/rate_limit.py`**

Add (mirror the pattern of `webhook_ingest_limiter`):

```python
chat_send_limiter = SlidingWindowLimiter(
    namespace="chat.send",
    max_requests=30,           # tune to your threat model
    window_seconds=60,
)
```

**File: `backend/app/api/gateway.py`** (line ~127, the `send_gateway_session_message` handler)

Add a dependency that calls the limiter keyed on the authenticated actor (user id or agent id). Pattern to follow: `backend/app/core/agent_auth.py` use of `agent_auth_limiter`.

Example:
```python
from app.core.rate_limit import chat_send_limiter

@router.post("/sessions/{session_id}/message", response_model=OkResponse)
async def send_gateway_session_message(
    session_id: str,
    payload: ChatSendPayload,
    board_id: UUID | None = BOARD_ID_QUERY,
    actor: ActorContext = ACTOR_DEP,
    _: None = Depends(chat_send_limiter.dependency_for_actor),
    ...
):
    ...
```

If `SlidingWindowLimiter` doesn't already expose a FastAPI-dependency helper, add one beside the class or replicate the manual check pattern used in `agent_auth_limiter`.

### Verification

```bash
# One quick-fire loop should eventually 429
source .env
AUTH="Authorization: Bearer $LOCAL_AUTH_TOKEN"
for i in $(seq 1 40); do
  curl -sS -o /dev/null -w "%{http_code} " -X POST \
    -H "$AUTH" -H "Content-Type: application/json" \
    -d '{"text":"spam"}' \
    "http://localhost:8000/api/v1/gateways/sessions/<existing_session_id>/message?board_id=<board_id>"
done
echo
# Expected: early ones 200, later ones 429. Pre-fix all 200.

make backend-test  # must still pass
```

### Prompt to paste into kimi-code

````
Apply rate limiting to the chat-send endpoint in openclaw-mission-control backend.

Root cause: `POST /api/v1/gateways/sessions/{session_id}/message` (in `backend/app/api/gateway.py`, handler `send_gateway_session_message`) has no rate limiter. The codebase already uses `SlidingWindowLimiter` from `backend/app/core/rate_limit.py` for `agent_auth_limiter` and `webhook_ingest_limiter`. Follow that existing pattern.

Task:

1. In `backend/app/core/rate_limit.py`, add a new `chat_send_limiter = SlidingWindowLimiter(namespace="chat.send", max_requests=30, window_seconds=60)` beside the existing limiters.

2. In `backend/app/api/gateway.py`, attach this limiter to the `send_gateway_session_message` handler. Key the limit on the authenticated actor id (agent_id if actor_type=="agent", user_id otherwise) — see `backend/app/core/agent_auth.py` for how `agent_auth_limiter` is used.

3. On exceedance, return HTTP 429 with a JSON `{"detail": "Chat rate limit exceeded"}` body.

4. Write one new pytest test in `backend/tests/test_chat_rate_limit.py`:
   - Arrange: create a gateway + board, get a session via existing fixtures in other tests.
   - Act: fire 35 POST /message calls in a loop.
   - Assert: at least one returns 429; the first 30 return 200.

5. Run `make backend-test` — must pass.

6. Verify manually:
   ```
   source /root/openclaw-mission-control/.env
   AUTH="Authorization: Bearer $LOCAL_AUTH_TOKEN"
   SID=$(curl -s -H "$AUTH" "http://localhost:8000/api/v1/gateways/sessions?board_id=<real_board>" | jq -r '.sessions[0].sessionId')
   for i in $(seq 1 40); do
     curl -sS -o /dev/null -w "%{http_code} " -X POST -H "$AUTH" -H "Content-Type: application/json" \
       -d '{"text":"probe"}' "http://localhost:8000/api/v1/gateways/sessions/$SID/message?board_id=<real_board>"
   done
   ```
   Expected: first ~30 return 200, remainder return 429.

Do not change existing limiters or other handlers. Do not introduce a new rate-limit mechanism — use the existing `SlidingWindowLimiter`.
````

---

## FIX-04 — Add HEALTHCHECKs for backend, frontend, webhook-worker

**Severity:** 🔴 P1 (ops)
**Effort:** 10 min

### Root cause

`backend/Dockerfile` and `frontend/Dockerfile` have no `HEALTHCHECK` directive. `compose.yml` defines healthchecks for `db` and `redis` only. Orchestrators (Kubernetes, swarm, docker-compose restart policies) can't determine whether the app containers are actually serving, so `depends_on` conditions are effectively ignored after startup.

### File changes

**File: `backend/Dockerfile`** (just before `CMD`):

```dockerfile
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz', timeout=2).status == 200 else 1)"
```

**File: `frontend/Dockerfile`** (just before `CMD`):

Install `wget` in the runner stage (node:20-alpine has it). Then add:

```dockerfile
HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=3 \
  CMD wget -q --spider http://localhost:3000/ || exit 1
```

**File: `compose.yml`** — add healthcheck blocks to `backend`, `frontend`, and `webhook-worker`:

```yaml
  backend:
    ...
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz', timeout=2).status==200 else 1)\""]
      interval: 15s
      timeout: 3s
      retries: 3
      start_period: 20s

  frontend:
    ...
    healthcheck:
      test: ["CMD-SHELL", "wget -q --spider http://localhost:3000/ || exit 1"]
      interval: 15s
      timeout: 3s
      retries: 3
      start_period: 30s

  webhook-worker:
    ...
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import redis, os, sys; r=redis.from_url(os.environ['RQ_REDIS_URL']); sys.exit(0 if r.ping() else 1)\""]
      interval: 15s
      timeout: 3s
      retries: 3
      start_period: 10s
```

For `backend` downstream of `db` / `redis`, also tighten `depends_on`:

```yaml
  backend:
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
```

### Verification

```bash
docker compose -f /root/openclaw-mission-control/compose.yml up -d --build
sleep 45
docker compose -f /root/openclaw-mission-control/compose.yml ps
# All 5 services should report "Up X (healthy)".
docker inspect --format='{{.State.Health.Status}}' openclaw-mission-control-backend-1
# Expected: healthy
```

### Prompt to paste into kimi-code

````
Add HEALTHCHECKs to the openclaw-mission-control Docker setup.

Current state: `compose.yml` defines healthchecks only for `db` and `redis`. `backend/Dockerfile` and `frontend/Dockerfile` have no HEALTHCHECK. `webhook-worker` has none.

Task:

1. In `backend/Dockerfile`, add a HEALTHCHECK just before the CMD that hits `http://localhost:8000/healthz` via stdlib `urllib.request` (no new deps) and returns 0 on 200.

2. In `frontend/Dockerfile`, add a HEALTHCHECK that wgets `http://localhost:3000/` (node:20-alpine has wget built-in; if not, add it to the apk install list in the runner stage).

3. In `compose.yml`, add a `healthcheck:` block to the `backend`, `frontend`, and `webhook-worker` services. For `webhook-worker`, use a redis ping since it has no HTTP surface.

4. Tighten `backend.depends_on` so it waits for `db` and `redis` to report `service_healthy` (already the case if present — verify).

5. Rebuild and restart the stack:
   ```
   docker compose -f /root/openclaw-mission-control/compose.yml up -d --build
   sleep 45
   docker compose -f /root/openclaw-mission-control/compose.yml ps
   ```
   All 5 services must report `(healthy)`. If any is `(unhealthy)`, investigate and fix before submitting.

6. `docker inspect --format='{{.State.Health.Status}}' <container>` should return `healthy` for each.

Do not change the services' runtime behavior. Keep `HEALTHCHECK` intervals at 15s/3s/3 retries to match the compose-level ones already used for db/redis.
````

---

## FIX-05 — HTTPS via reverse proxy (P2)

**Severity:** 🟡 P2
**Effort:** 1-2 hours

### Scope

Add a `caddy` service in front of `backend` and `frontend`. Caddy auto-obtains Let's Encrypt certs for the production FQDN.

### Minimal change

**File: `compose.yml`** — new `caddy` service:

```yaml
  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./ops/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      backend:
        condition: service_healthy
      frontend:
        condition: service_healthy
    restart: unless-stopped
volumes:
  caddy_data: {}
  caddy_config: {}
```

Remove the `ports:` mapping on `backend` and `frontend` (they should only talk via the internal docker network).

**New file: `ops/Caddyfile`**:

```
mc.example.com {
  handle /api/* {
    reverse_proxy backend:8000
  }
  handle {
    reverse_proxy frontend:3000
  }
}
```

Replace `mc.example.com` with your real FQDN. Update `.env`:

```
BASE_URL=https://mc.example.com
CORS_ORIGINS=https://mc.example.com
```

### Verification

```bash
curl -sSI https://mc.example.com/health | head -3   # HTTP/2 200
curl -sSI https://mc.example.com/api/v1/users/me -H "Authorization: Bearer $LOCAL_AUTH_TOKEN"
```

### Prompt to paste into kimi-code

````
Add HTTPS to openclaw-mission-control via a Caddy reverse proxy.

Task:

1. Add a `caddy` service to `compose.yml` (image: caddy:2-alpine, ports 80 and 443, volumes for data+config, depends_on backend and frontend with service_healthy).

2. Remove the host-port mappings from `backend` (`0.0.0.0:8000:8000`) and `frontend` (`0.0.0.0:3000:3000`). They should only be reachable via the internal docker network by `caddy`.

3. Create `ops/Caddyfile` with a two-route config (mc.example.com): `/api/*` → backend:8000, everything else → frontend:3000. Leave the FQDN as a placeholder and note that the operator must edit it before deploying.

4. Update `.env.example` to document `BASE_URL=https://<your-fqdn>` and `CORS_ORIGINS=https://<your-fqdn>`.

5. Verify the stack still comes up clean: `docker compose up -d --build && sleep 60 && docker compose ps`. All services must be healthy including caddy.

6. Verify the original functionality still works through caddy (assuming the operator has set a real FQDN with DNS pointing at the box):
   ```
   curl -sSI https://<fqdn>/health   # expect HTTP/2 200
   curl -sSI https://<fqdn>/         # expect HTTP/2 200 from frontend
   ```

Do not add manual cert management — Caddy handles Let's Encrypt automatically. Do not configure cert paths by hand. Do not break local dev (the Caddyfile and compose change should still let someone run `http://localhost` locally with a self-signed cert or `tls internal`).
````

---

## FIX-06 — Tighten CORS (P2)

**Severity:** 🟡 P2
**Effort:** 15 min

### File: `backend/app/main.py:465`

Change from wildcards to explicit lists:

```diff
 app.add_middleware(
     CORSMiddleware,
     allow_origins=origins,
     allow_credentials=True,
-    allow_methods=["*"],
-    allow_headers=["*"],
+    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
+    allow_headers=["Authorization", "Content-Type", "X-Agent-Token", "X-Request-ID"],
     expose_headers=["X-Total-Count", "X-Limit", "X-Offset"],
 )
```

### Verification

- Run full Cypress + e2e flows; they should still work.
- `curl -sSI -X OPTIONS -H "Origin: http://217.216.34.170:3000" -H "Access-Control-Request-Method: DELETE" http://localhost:8000/api/v1/boards/any` should still return `Access-Control-Allow-Methods: ...DELETE...`.

### Prompt to paste into kimi-code

````
Tighten CORS in openclaw-mission-control backend.

In `backend/app/main.py` around line 465, replace `allow_methods=["*"]` and `allow_headers=["*"]` with explicit lists:
  allow_methods = ["GET","POST","PATCH","PUT","DELETE","OPTIONS"]
  allow_headers = ["Authorization","Content-Type","X-Agent-Token","X-Request-ID"]

Before shipping, grep for any custom X- headers the frontend actually sends (look in `frontend/src/api/mutator.ts` and anywhere that calls `fetch` or sets `headers:`) and add any missing ones to `allow_headers`.

Verify:
- `make backend-test` must still pass.
- Run all 9 Cypress specs — no new failures.
- Run the e2e flows in `/tmp/e2e_flows.sh` and `/tmp/e2e_flows2.sh` — all green.
````

---

## FIX-07 — Add observability (P2)

**Severity:** 🟡 P2
**Effort:** 2-4 hours

### Scope

Add: Sentry (error tracking, backend + frontend), Prometheus client (backend metrics).

### Backend (Sentry + prometheus_fastapi_instrumentator)

`backend/pyproject.toml` — add deps:
```toml
sentry-sdk = "^2.0"
prometheus-fastapi-instrumentator = "^7.0"
```

`backend/app/main.py` — on startup, init Sentry if `SENTRY_DSN` set. Mount Prometheus at `/metrics`.

### Frontend (Sentry)

`frontend/package.json` — add `@sentry/nextjs`.
Run `npx @sentry/wizard@latest -i nextjs`.
Gate on `NEXT_PUBLIC_SENTRY_DSN`.

### Prompt to paste into kimi-code

````
Add Sentry error reporting and Prometheus metrics to openclaw-mission-control.

Backend:
1. Add `sentry-sdk` and `prometheus-fastapi-instrumentator` to `backend/pyproject.toml`. Run `uv sync`.
2. In `backend/app/main.py` lifespan/startup, initialize Sentry when `SENTRY_DSN` env var is set. Use `traces_sample_rate=0.1` by default, settable via `SENTRY_TRACES_SAMPLE_RATE`.
3. Mount `Instrumentator().expose(app, endpoint="/metrics", include_in_schema=False)` — guard behind `ENABLE_METRICS` env flag so local dev isn't polluted.
4. Add both env vars to `backend/.env.example` with comments.

Frontend:
5. Install `@sentry/nextjs`. Run the wizard or hand-roll the config. Gate all init on `process.env.NEXT_PUBLIC_SENTRY_DSN` being non-empty.

Verify:
- `make backend-test` still green.
- `make frontend-build` still green.
- Start stack without SENTRY_DSN set — app must still work (no errors at startup, /metrics returns 404 or 200 based on ENABLE_METRICS).
- With SENTRY_DSN set, intentionally raise an exception in a throwaway test endpoint, confirm it shows up in Sentry.
````

---

## FIX-08 — Postgres backup script (P2)

**Severity:** 🟡 P2
**Effort:** 1 hour

Write `scripts/backup_db.sh` that `pg_dump`s into `backups/mc-YYYYMMDD-HHMMSS.sql.gz`. Document in `README.md` or `ops/RUNBOOK.md` how to run it from cron and how to restore.

### Prompt to paste into kimi-code

````
Add a postgres backup + restore helper for openclaw-mission-control.

1. Create `scripts/backup_db.sh` that:
   - Reads DATABASE_URL (or POSTGRES_* vars) from .env.
   - Runs `docker compose exec -T db pg_dump ...` into `backups/mc-YYYYMMDD-HHMMSS.sql.gz` (gzip-compressed).
   - Keeps the last N=30 backups, deletes older ones.
   - Fails loud on any error.
2. Create `scripts/restore_db.sh` that takes a `.sql.gz` path, confirms via a prompt (`RESTORE TO PRODUCTION? type YES:`), drops and recreates the target DB, and pipes the dump back in.
3. Add a `Makefile` target `db-backup` that runs the backup script.
4. Document in `README.md` under a new "Operations" section.

Verify:
- `make db-backup` produces a fresh file in `backups/`.
- `scripts/restore_db.sh <file>` restores correctly into a throwaway DB name.
````

---

## FIX-09 — Slow gateway endpoints (P3, note only)

`GET /api/v1/gateways/status`, `/sessions` consistently take ~1.3–1.5s. The backend emits `http.request.slow` warnings for each. Not a blocker.

Investigate later: is the RPC round-trip (backend ↔ gateway WS) the bottleneck? Cache gateway status for 1-2 s where safe? File an issue, don't prioritize until throughput matters.

---

## Dispatch checklist

- [ ] FIX-01 — Invalid UUID 500 (systemic)
- [ ] FIX-02 — React hydration mismatch
- [ ] FIX-03 — Chat-send rate limit
- [ ] FIX-04 — Docker healthchecks
- [ ] FIX-05 — HTTPS reverse proxy
- [ ] FIX-06 — Tighten CORS
- [ ] FIX-07 — Sentry + Prometheus
- [ ] FIX-08 — DB backup script
- [ ] FIX-09 — Slow endpoints (defer)

After each fix lands, re-run `PRODUCTION-AUDIT-2026-04-25.md#11` reproducers to confirm the bug is gone and no regressions. A clean run with no 5xx in the REST smoke and 9/9 Cypress specs passing is the gate for "ready to ship widely."
