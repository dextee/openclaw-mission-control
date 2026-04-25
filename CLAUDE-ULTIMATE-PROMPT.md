# Ultimate Claude Prompt — Mission Control E2E Testing, Audit & Fix

## 1. Project Overview

**Repository:** `/root/openclaw-mission-control`  
**Stack:** Python 3.12/FastAPI backend + Next.js 14 frontend + Docker Compose (5 services)  
**Database:** PostgreSQL 16 + Redis (RQ queues)  
**Gateway:** OpenClaw Zero-Token at `ws://172.19.0.1:3001` (separate repo at `/root/openclaw-zero-token`)  
**Auth:** `LOCAL_AUTH_TOKEN` mode (64-char hex in `.env`)  
**Git target:** `https://github.com/dextee/openclaw-mission-control.git` (fork of `abhi1693/...`) — push to this fork.

**Current state:** 14 commits ahead of upstream. All P1 bugs fixed. Score 9.0/10. Ready for deep E2E testing and refinement.

---

## 2. How to Access the Stack

### From browser (via ngrok — HTTPS)
```
https://unmapped-sleet-handled.ngrok-free.dev
```
Login with the `LOCAL_AUTH_TOKEN` from `.env` (64-char hex).

### Direct access (HTTP)
- Frontend: `http://217.216.34.170:3000`
- Backend API: `http://217.216.34.170:8000`
- Backend health: `http://217.216.34.170:8000/healthz` → `{"ok":true}`

### Local (on server)
```bash
cd /root/openclaw-mission-control
source .env
AUTH="Authorization: Bearer ${LOCAL_AUTH_TOKEN}"
```

---

## 3. What's Already Fixed (do not re-fix)

| Fix | Status | Commit |
|---|---|---|
| FIX-01 UUID validation (no 500s on invalid UUIDs) | ✅ Done | `a802553` |
| FIX-02 React hydration mismatch | ✅ Done | `69a9df8` |
| FIX-03 Chat-send rate limit (30 req/60s) | ✅ Done | `545ca93` |
| FIX-04 Docker HEALTHCHECKs | ✅ Done | `5330a1e` |
| FIX-05 HTTPS/Caddy reverse proxy | 🟡 Scaffolding only, dormant | `426251f` |
| FIX-06 CORS tightened | ✅ Done | `20c9048` |
| FIX-07 Sentry + Prometheus observability | ✅ Done | `39810c7` |
| FIX-08 Postgres backup/restore scripts | ✅ Done | `3fe3835` |
| FIX-09 Slow gateway endpoints (~1.3s) | 🟢 Deferred P3 | docs only |
| FIX-10 Lifecycle reconcile crash → agents stuck | ✅ Done | `badc346` |
| FIX-11 Frontend missing `/api/v1/` prefix on raw fetches | ✅ Done | `5634947` |
| FIX-12 Frontend ngrok same-origin API URLs | ✅ Done | `2bc78da` |

**Docs commits:** Patch notes, audit docs, FIX-10 verification.

---

## 4. Known Remaining Issues to Investigate

### 4.1 Agents go `offline` after max wake attempts (P2)
**What:** Board agents provision successfully, reach `status="online"`, then after 3 wake cycles with no heartbeat they go `status="offline"`.  
**Root cause:** The zero-token gateway agents do NOT automatically call MC's `/api/v1/agents/{id}/heartbeat` endpoint. The HEARTBEAT.md in their workspace tells them to, but the gateway's session runner doesn't execute it.  
**Impact:** Agents show as offline in MC UI even though the gateway sessions are functional.  
**How to test:**
```bash
cd /root/openclaw-mission-control
source .env
AUTH="Authorization: Bearer ${LOCAL_AUTH_TOKEN}"

# Create a board + agent
curl -sS -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"heartbeat-test","slug":"heartbeat-test","gateway_id":"8242530a-d23d-4309-bb07-79d0a00fb29b","board_type":"goal"}' \
  http://localhost:8000/api/v1/boards

# Create an agent on that board with deepseek-v4
curl -sS -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"board_id":"<BOARD_ID>","name":"Heartbeat Tester","model":"deepseek-v4"}' \
  http://localhost:8000/api/v1/agents

# Watch status over ~5 minutes
curl -sS -H "$AUTH" http://localhost:8000/api/v1/agents/<AGENT_ID>
```
**Expected:** Agent should stay `online` (or at least not permanently `offline`).  
**Possible fixes:**
- Option A: Increase `MAX_WAKE_ATTEMPTS_WITHOUT_CHECKIN` in `backend/app/services/openclaw/constants.py` from 3 to a much higher number (e.g., 100) since the gateway handles agent liveness internally.
- Option B: Patch the zero-token gateway to actually execute the heartbeat loop (much harder — touches external repo).
- Option C: Change lifecycle reconcile to not count wake attempts for zero-token gateway agents.
- **Recommended:** Option A — increase the threshold. The gateway is the source of truth for agent liveness; MC's wake/checkin model doesn't map well to zero-token gateway sessions.

### 4.2 Board memory doesn't sync gateway chat history (P2)
**What:** When you send a message to an agent via `/api/v1/gateways/sessions/{id}/message`, the agent responds in the gateway session. But the board memory (`/api/v1/boards/{id}/memory`) stays empty.  
**Root cause:** Board memory is populated by the agent's heartbeat loop pulling tasks/comments. Since the agent never heartbeats, memory never syncs.  
**Impact:** The MC chat UI for board agents shows no history.  
**How to test:** Send a message to an agent session, then check `/api/v1/boards/{id}/memory`.  
**Possible fix:** Add a webhook or callback from the gateway to MC when a session receives a message, OR have MC poll gateway session history periodically and sync to board memory.

### 4.3 Frontend API base URL logic needs refinement (P2)
**What:** `frontend/src/lib/api-base.ts` auto-resolves backend URL. For ngrok hostnames it now returns `""` (same-origin). For localhost it returns `:8000`. For everything else it returns `:8000`.  
**Problem:** When accessing via public IP `http://217.216.34.170:3000`, the frontend tries `http://217.216.34.170:8000` which works (CORS allows it). But if someone puts MC behind a reverse proxy on port 443, the `:8000` suffix breaks.  
**How to test:** Access via ngrok (`https://...`) and via public IP (`http://217.216.34.170:3000`). Both should work.  
**Possible fix:** Make `getApiBaseUrl()` smarter — if `window.location.port` is not 3000 and not empty, assume a reverse proxy and use same-origin.

### 4.4 Caddy ngrok setup is manual (P2)
**What:** Caddy runs on port 18080, ngrok tunnels it. This works but is fragile.  
**Improvement:** Document or automate the Caddy + ngrok setup so it's reproducible.

### 4.5 Gateway `agents.create` returns "already exists" as error (P2 — cosmetic)
**What:** The zero-token gateway returns `INVALID_REQUEST: agent "mc-..." already exists` when MC retries `agents.create`. MC swallows this correctly now, but the gateway logs show errors.  
**Impact:** Log noise only. No functional impact.  
**Fix location:** Zero-token gateway repo (`/root/openclaw-zero-token`) — make `agents.create` idempotent (return success if agent exists).

---

## 5. E2E Testing Checklist

Run these in order. Any failure is a bug to fix.

### 5.1 Infrastructure Health
```bash
cd /root/openclaw-mission-control

# All services healthy
docker compose ps

# Backend tests
make backend-test        # Expected: 488 passed, 1 xfailed
make backend-typecheck   # Expected: clean

# Frontend tests
make frontend-typecheck  # Expected: clean
make frontend-build      # Expected: clean

# REST smoke (no 5xx)
bash /tmp/rest_smoke2.sh | grep "5xx"   # Expected: 5xx = 0
```

### 5.2 Gateway Connectivity
```bash
source .env
AUTH="Authorization: Bearer ${LOCAL_AUTH_TOKEN}"

# Gateway connected
curl -sS -H "$AUTH" "http://localhost:8000/api/v1/gateways/status?board_id=0f9b9ec9-e3c1-40e4-b670-c4d743a33c8f" | jq '.connected'
# Expected: true

# Models list includes deepseek-v4
curl -sS -H "$AUTH" "http://localhost:8000/api/v1/gateways/models?board_id=0f9b9ec9-e3c1-40e4-b670-c4d743a33c8f" | jq '.models[] | select(.id == "deepseek-v4") | {id, auth_valid}'
# Expected: {"id": "deepseek-v4", "auth_valid": true}

# Browser status (should not return HTML 404)
curl -sS -H "$AUTH" "http://localhost:8000/api/v1/gateways/browser-status?board_id=0f9b9ec9-e3c1-40e4-b670-c4d743a33c8f" | jq '.contexts | length'
# Expected: a number (not HTML)
```

### 5.3 Agent Lifecycle E2E
```bash
# 1. Create test board
BOARD=$(curl -sS -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"e2e-test","slug":"e2e-test","gateway_id":"8242530a-d23d-4309-bb07-79d0a00fb29b","board_type":"goal"}' \
  http://localhost:8000/api/v1/boards | jq -r '.id')

# 2. Create agent with deepseek-v4
AGENT=$(curl -sS -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"board_id\":\"$BOARD\",\"name\":\"E2E Tester\",\"model\":\"deepseek-v4\"}" \
  http://localhost:8000/api/v1/agents | jq -r '.id')

# 3. Poll status for 5 minutes — should reach "online" within 2 min, NOT go "offline" within 5 min
for i in {1..10}; do
  echo "=== Check $i ==="
  curl -sS -H "$AUTH" "http://localhost:8000/api/v1/agents/$AGENT" | jq '{status, wake_attempts, last_seen_at, last_provision_error}'
  sleep 30
done

# 4. Send a task via gateway session
curl -sS -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"content":"Write a 3-sentence summary of fintech compliance in Singapore"}' \
  "http://localhost:8000/api/v1/gateways/sessions/$(curl -sS -H "$AUTH" "http://localhost:8000/api/v1/gateways/sessions?board_id=$BOARD" | jq -r '.sessions[] | select(.key | contains("mc-'"$AGENT"'")) | .sessionId')/message?board_id=$BOARD"

# 5. Check session history has assistant response
sleep 60
curl -sS -H "$AUTH" "http://localhost:8000/api/v1/gateways/sessions/$(curl -sS -H "$AUTH" "http://localhost:8000/api/v1/gateways/sessions?board_id=$BOARD" | jq -r '.sessions[] | select(.key | contains("mc-'"$AGENT"'")) | .sessionId')/history?board_id=$BOARD" | jq '.history[] | {role, content_type: (.content[0].type // "text")}'

# 6. Cleanup
curl -sS -X DELETE -H "$AUTH" "http://localhost:8000/api/v1/agents/$AGENT"
curl -sS -X DELETE -H "$AUTH" "http://localhost:8000/api/v1/boards/$BOARD"
```

### 5.4 Frontend Browser E2E
```bash
cd /root/openclaw-mission-control/frontend
bash ../scripts/with_node.sh --cwd . npx cypress run --headless --browser electron
# Expected: 9/9 specs passed, 21/21 tests
```

### 5.5 ngrok Access E2E
1. Open `https://unmapped-sleet-handled.ngrok-free.dev`
2. Paste the `LOCAL_AUTH_TOKEN` from `.env`
3. Navigate to `/boards` → create a board → should load without errors
4. Navigate to `/gateways` → should show "Connected" badge
5. Navigate to `/agents` → should list agents
6. Browser DevTools Console should show zero red errors

---

## 6. How to Fix Issues You Find

### Coding conventions
- Follow existing style (black + ruff for Python, prettier for TS).
- Run `make backend-format` after Python changes.
- Add tests for backend changes in `backend/tests/`.
- Keep commits atomic: one fix = one commit with conventional message (`fix(api): ...`, `feat(frontend): ...`, `chore(docker): ...`).
- Push to `dextee/openclaw-mission-control.git` master.

### Before any commit
```bash
cd /root/openclaw-mission-control
make backend-test backend-typecheck frontend-typecheck frontend-build
# All must pass
```

### After any backend change
```bash
cd /root/openclaw-mission-control
docker compose build backend webhook-worker
docker compose up -d backend webhook-worker
```

### After any frontend change
```bash
cd /root/openclaw-mission-control
docker compose build frontend
docker compose up -d frontend
```

---

## 7. Critical Files Reference

| File | Purpose |
|---|---|
| `backend/app/services/openclaw/lifecycle_reconcile.py` | Agent reconcile worker — FIX-10 applied here |
| `backend/app/services/openclaw/lifecycle_orchestrator.py` | Agent lifecycle transitions |
| `backend/app/services/openclaw/constants.py` | `MAX_WAKE_ATTEMPTS_WITHOUT_CHECKIN=3` |
| `backend/app/services/openclaw/provisioning.py` | Gateway RPC calls (`agents.create`, `agents.update`) |
| `frontend/src/lib/api-base.ts` | Frontend API URL resolution |
| `frontend/src/components/BrowserHealth.tsx` | Browser health display |
| `frontend/src/components/WebModelPicker.tsx` | Model selector |
| `frontend/src/components/WebProviderStatus.tsx` | Provider auth status |
| `compose.yml` | Docker Compose stack |
| `ops/Caddyfile` | Dormant HTTPS reverse proxy |
| `.env` | Secrets, tokens, URLs |

---

## 8. ngrok / Caddy Reverse Proxy Setup (current state)

Caddy runs on port 18080:
```bash
ps aux | grep "caddy run --config /tmp/Caddyfile.ngrok"
# Routes /api/* → backend:8000, everything else → frontend:3000
```

Ngrok tunnels 18080:
```bash
curl -s http://localhost:4040/api/tunnels | jq '.tunnels[0].public_url'
# → https://unmapped-sleet-handled.ngrok-free.dev
```

If ngrok dies, restart:
```bash
pkill -f "ngrok http 18080"
nohup ngrok http 18080 > /tmp/ngrok-final.log 2>&1 &
```

---

## 9. Your Mission

1. **Run the full E2E checklist** (Section 5). Document any failures with exact error messages, file:line references, and curl commands to reproduce.
2. **Investigate the 4 known remaining issues** (Section 4). For each, determine if it's truly a bug or expected behavior. If it's a bug, write a fix, test it, commit it.
3. **Focus on agent heartbeat / offline issue** (4.1) — this is the biggest UX gap. An agent that can generate leads and social plans should show as "online" in the UI.
4. **Do not break existing functionality.** The test suite is the guardrail.
5. **Update this doc** (`CLAUDE-ULTIMATE-PROMPT.md`) with any new findings so the next agent can pick up seamlessly.

**Goal:** Get Mission Control to a state where a user can create a board, create a deepseek-v4 agent, send it a task, see the response in board memory, and the agent stays "online" — all verified by automated tests.
