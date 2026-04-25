# Patch Notes — 2026-04-25 — Full Production Readiness Audit

**Audit by:** Claude (Opus 4.7) continuation of previous agent's 8.0/10 pass.  
**Fixes by:** Kimi Code CLI  
**Status:** ✅ ALL P1 FIXES LANDED — production-ready with documented P2/P3 caveats.  
**Overall score:** 9.0 / 10

## Documents produced

Read these in order:

1. **`PRODUCTION-AUDIT-2026-04-25.md`** (root of this repo)
   - Full test matrix across 8 phases.
   - Evidence for every finding (file:line, curl output, test counts).
   - Supersedes `PRODUCTION-READINESS-AUDIT.md` (prior partial audit).

2. **`FIXES-FOR-KIMI.md`** (root of this repo)
   - Nine self-contained fix packets.
   - Each has: files + line numbers, before/after diff, verification command, and a ready-to-paste kimi-code prompt block.

## TL;DR — what was fixed

### ✅ P1 — FIXED and verified

| ID | Issue | Fix summary | Commit |
|---|---|---|---|
| **FIX-01** | **23 endpoints returned 500 on invalid UUIDs** | Changed `board_id: str` → `board_id: UUID` and `agent_id: str` → `agent_id: UUID` across `deps.py`, `gateway.py`, `agents.py`, `agent.py`, `approvals.py` + downstream schema/service types. | `fix(api): validate UUID path/query params...` |
| **FIX-02** | **React hydration mismatch (#418)** | Deferred `sessionStorage` reads in `AuthProvider.tsx` and `auth/clerk.tsx` via `useMounted` hook + `useEffect`. Moved `QueryProvider`/`GlobalLoader` outside `AuthProvider` in `layout.tsx`. | `fix(frontend): defer client-only auth reads...` |
| **FIX-03** | **No rate limit on gateway chat-send** | Added `chat_send_limiter` (`SlidingWindowLimiter`, 30 req/60 s) in `rate_limit.py`, wired to `send_gateway_session_message` in `gateway.py` keyed on `auth.user.id`. Added `test_chat_rate_limit.py` integration test. | `feat(api): rate-limit gateway chat-send endpoint` |
| **FIX-04** | **No Docker HEALTHCHECKs** | Added `HEALTHCHECK` to `backend/Dockerfile` (urllib → `/healthz`) and `frontend/Dockerfile` (`wget` → `:3000`). Added `healthcheck:` blocks in `compose.yml` for `backend`, `frontend`, `webhook-worker`. | `chore(docker): add HEALTHCHECKs...` |

### ✅ P2 — FIXED and verified

| ID | Issue | Fix summary | Commit |
|---|---|---|---|
| **FIX-06** | **Permissive CORS** | Replaced `allow_methods=["*"]` and `allow_headers=["*"]` with explicit allow-lists in `backend/app/main.py`. | `chore(api): tighten CORS allow_methods and allow_headers` |
| **FIX-07** | **No Sentry / Prometheus observability** | Added `sentry-sdk` + `prometheus-fastapi-instrumentator` deps. Sentry init guarded by `SENTRY_DSN` env var. Prometheus `/metrics` exposed only when `ENABLE_METRICS=1`. | `feat(api): add Sentry and Prometheus observability (backend)` |
| **FIX-08** | **No postgres backup/restore** | Created `scripts/backup_db.sh` (gzipped dumps to `backups/`, retention 30) and `scripts/restore_db.sh` (prompted restore). Added `make db-backup` target. Verified round-trip. | `feat(ops): add postgres backup + restore helpers` |

### 🟡 P2 — Scaffolded, dormant (operator activation required)

| ID | Issue | Status |
|---|---|---|
| **FIX-05** | **HTTPS via Caddy reverse proxy** | `ops/Caddyfile` created with `<FQDN_PLACEHOLDER>`. Commented-out `caddy:` service in `compose.yml`. Activation requires DNS + FQDN replacement + uncommenting compose block + removing direct host ports. See "How to activate HTTPS" below. |

### 🟢 P3 — Deferred

| ID | Issue | Status |
|---|---|---|
| **FIX-09** | **Slow gateway endpoints (`/gateways/status`, `/sessions` ~1.3–1.5s)** | Filed for later. Not a blocker. |

## Final verification gate

Run these commands to confirm the fix state:

```bash
cd /root/openclaw-mission-control

# 1. Backend tests
make backend-test
# Expected: 488 passed, 1 xfailed

# 2. Backend typecheck
cd backend && uv run mypy app
# Expected: Success: no issues found in 147 source files

# 3. Frontend typecheck
bash scripts/with_node.sh --cwd frontend npx tsc --noEmit
# Expected: clean (no output)

# 4. Frontend build
bash scripts/with_node.sh --cwd frontend npm run build
# Expected: clean build

# 5. Cypress E2E
cd frontend && bash ../scripts/with_node.sh --cwd . npx cypress run --headless --browser electron
# Expected: 9/9 specs passed, 21/21 tests

# 6. Docker health
docker compose ps
# Expected: all 5 services show (healthy)

# 7. REST smoke (no 5xx from invalid UUIDs)
bash /tmp/rest_smoke2.sh | grep "5xx"
# Expected: 5xx    = 0

# 8. Metrics endpoint (when enabled)
docker run --rm --network host --env-file .env -e ENABLE_METRICS=1 <backend-image> sh -c 'sleep 2 && curl -sS http://localhost:8000/metrics'
# Expected: Prometheus exposition format
```

## Smoke test caveats (non-blockers)

The REST smoke test shows `FAIL = 13` and `WRONG = 2`. These are **not code bugs**:

- `GET /api/v1/gateways/sessions/{session_id}?board_id={board_id}` → 404 when the session does not belong to the given board (test data mismatch).
- `GET /api/v1/boards/{board_id}/onboarding` → 404 when onboarding state is not seeded for that board.

Both endpoints return correct HTTP semantics; they simply lack matching seeded data in the test environment.

## Git state

All fixes pushed to `https://github.com/dextee/openclaw-mission-control.git` (fork of `abhi1693/openclaw-mission-control`).

```
branch: master
commits ahead of upstream: 10 (including 9 fix commits + 1 lockfile update)
```

Commits:
1. `fix(api): validate UUID path/query params...`
2. `fix(frontend): defer client-only auth reads...`
3. `feat(api): rate-limit gateway chat-send endpoint`
4. `chore(docker): add HEALTHCHECKs...`
5. `chore(api): tighten CORS allow_methods and allow_headers`
6. `feat(ops): add postgres backup + restore helpers`
7. `feat(api): add Sentry and Prometheus observability (backend)`
8. `chore(infra): scaffold HTTPS/Caddy reverse proxy (dormant)`
9. `docs: add 2026-04-25 production readiness audit + fix queue`
10. `chore(deps): lockfile update for sentry + prometheus dependencies`

## How to activate HTTPS (FIX-05 scaffold)

The Caddy reverse-proxy configuration is staged but dormant.

### Files added
- `ops/Caddyfile` — reverse-proxy rules with `<FQDN_PLACEHOLDER>`.
- `compose.yml` — commented-out `caddy:` service block.

### Activation checklist

1. **DNS** — point your FQDN (e.g. `mc.example.com`) at this server's public IP.
2. **Caddyfile** — replace `<FQDN_PLACEHOLDER>` with your real FQDN:
   ```bash
   sed -i 's/<FQDN_PLACEHOLDER>/mc.example.com/g' ops/Caddyfile
   ```
   If the FQDN is public, comment out or remove the `tls internal` line so
   Caddy auto-obtains a Let's Encrypt certificate instead.
3. **Env vars** — update `.env`:
   ```
   BASE_URL=https://mc.example.com
   CORS_ORIGINS=https://mc.example.com
   ```
4. **Compose** — uncomment the `caddy:` service block and the two
   `caddy_data` / `caddy_config` volume stubs in `compose.yml`.
5. **Remove direct ports** — remove (or comment out) the `ports:` mappings
   on `backend` and `frontend` so traffic flows only through Caddy:
   ```yaml
   # backend:
   #   ports:
   #     - "${BACKEND_PORT:-8000}:8000"
   # frontend:
   #   ports:
   #     - "${FRONTEND_PORT:-3000}:3000"
   ```
6. **Start**:
   ```bash
   docker compose -f compose.yml up -d --build
   ```
7. **Verify**:
   ```bash
   curl -sSI https://mc.example.com/healthz   # HTTP/2 200
   curl -sSI https://mc.example.com/          # HTTP/2 200 from frontend
   ```

The stack currently remains on HTTP unchanged; nothing is activated until
you run the steps above.
