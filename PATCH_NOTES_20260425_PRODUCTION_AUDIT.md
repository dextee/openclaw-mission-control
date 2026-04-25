# Patch Notes — 2026-04-25 — Full Production Readiness Audit

**Audit by:** Claude (Opus 4.7) continuation of previous agent's 8.0/10 pass.
**Overall score:** 7.5 / 10 — production-capable, 4 P1 bugs block a clean ship.
**No code changes landed in this commit** — this is an audit + fix queue. Kimi-code should read the full docs below and dispatch fixes in order.

## Documents produced

Read these in order:

1. **`PRODUCTION-AUDIT-2026-04-25.md`** (root of this repo)
   - Full test matrix across 8 phases.
   - Evidence for every finding (file:line, curl output, test counts).
   - Supersedes `PRODUCTION-READINESS-AUDIT.md` (prior partial audit).

2. **`FIXES-FOR-KIMI.md`** (root of this repo)
   - Nine self-contained fix packets.
   - Each has: files + line numbers, before/after diff, verification command, and a ready-to-paste kimi-code prompt block.
   - Dispatch order: FIX-01 → FIX-02 → FIX-03 → FIX-04 → P2s.

## TL;DR — what the audit found

### Green (keep as-is)
- Backend pytest: **487 passed, 1 xfailed** (77 s).
- Frontend vitest: **127 passed** (17 s, 100% coverage on scoped modules).
- mypy --strict: clean (152 files). tsc: clean. `next build`: clean.
- All 5 docker services up; db + redis healthy.
- 34/34 frontend routes return 200.
- All 10 critical-path E2E flows pass (board/task/webhook/invite/tag CRUD, gateway chat history, metrics, settings).
- Gateway RPC verified: 30 models, 13 browser contexts, 27 sessions.
- Secrets properly `.gitignore`d; no tokens in git history.

### 🔴 P1 — MUST fix before wide rollout

| ID | Issue | Where | One-line fix |
|---|---|---|---|
| **FIX-01** | **23 endpoints return 500 on invalid UUIDs** (systemic, not 1 like prior audit said) | `backend/app/api/deps.py:131,142,161,180,195` + `backend/app/api/gateway.py:41,77,94,112,131` | `board_id: str` → `board_id: UUID` (pattern already in `tags.py`) |
| **FIX-02** | **React hydration mismatch (#418)** on `/boards` and local-auth flow in production | `AuthProvider` / `LocalAuthLogin` / `boards/page.tsx` — reproduce in dev mode to pinpoint | Move client-only reads into `useEffect`, or `dynamic(..., { ssr: false })` |
| **FIX-03** | **No rate limit on `POST /api/v1/gateways/sessions/{id}/message`** — agent-token flood risk | `backend/app/api/gateway.py:127` — handler `send_gateway_session_message` | Add `chat_send_limiter` mirroring existing `webhook_ingest_limiter` pattern |
| **FIX-04** | **No HEALTHCHECK** in backend/frontend Dockerfiles; compose has none for backend/frontend/webhook-worker | `backend/Dockerfile`, `frontend/Dockerfile`, `compose.yml` | Add HEALTHCHECK directives + compose healthcheck blocks |

### 🟡 P2 — address before scaling
- FIX-05: HTTPS via Caddy reverse proxy.
- FIX-06: Tighten CORS (`allow_methods=["*"]` → explicit list).
- FIX-07: Sentry + Prometheus instrumentation.
- FIX-08: postgres backup + restore scripts.

### 🟢 P3 — defer
- FIX-09: `/api/v1/gateways/status` and `/sessions` routinely take ~1.5 s. File issue, don't prioritize until throughput matters.

## Reproducer scripts

All still in `/tmp/` — run them to verify any fix landed cleanly:

- `/tmp/rest_smoke.sh`, `/tmp/rest_smoke2.sh` — REST API smoke + invalid-UUID sweep.
- `/tmp/e2e_flows.sh`, `/tmp/e2e_flows2.sh` — 10 critical-path E2E flows.
- `/tmp/page_smoke.sh` — 34-route frontend HTTP smoke.

Outputs captured in `/tmp/*_output.txt` and `/tmp/cy_*.txt` for audit trail.

## Re-test gate after each fix

```bash
cd /root/openclaw-mission-control
make backend-test frontend-test backend-typecheck frontend-typecheck frontend-build
/tmp/rest_smoke2.sh > /tmp/retest.txt && grep "5xx" /tmp/retest.txt    # must show "5xx   = 0"
/tmp/e2e_flows.sh && /tmp/e2e_flows2.sh
cd frontend && bash ../scripts/with_node.sh --cwd . npx cypress run --headless --browser electron
# Success criteria: 0 pytest failures, 0 vitest failures, 0 5xx, 9/9 Cypress specs pass.
```

## Context for kimi-code

- Auth: `LOCAL_AUTH_TOKEN` in `.env` (64-char hex). `AUTH_MODE=local`.
- Real gateway attached: `ws://172.19.0.1:3001` with `dangerouslyDisableDeviceAuth=true` (accepted trade-off for Docker→host — do NOT try to remove).
- Real board: "SG Leadgen" (ID `0f9b9ec9-e3c1-40e4-b670-c4d743a33c8f`) — safe to read from; use `audit-*` prefix for anything you create.
- Do NOT spam the Telegram session when testing chat.send — a test session exists at key `agent:main:test-mc-session`.

## Git state at audit time

```
branch: master
ahead of origin/master: 4 commits
working tree: clean except for the two audit .md files and this file
```

Commits ahead:
```
857104e feat: gateway chat dashboard
f0f4c2b infra: fix gateway connectivity and remove broken docker service
c135902 feat: zero-token gateway monitoring, reauth, model assignment
2df6154 feat: add zero-token gateway monitoring and reauth
```

Do not force-push or amend these. Land fixes as new commits.

---

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
   Caddy auto-obtains a Let's Encrypt certificate.
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

