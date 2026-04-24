# OpenClaw Mission Control + Zero-Token — Project Patch Notes

**Last Updated:** 2026-04-11 09:30 UTC
**Git Branch:** master (HEAD: `2df6154`, 1 commit ahead of `origin/master`)

---

## Quick Reference for New CLIs

| Repo | Path | Purpose |
|------|------|---------|
| **mission-control** | `/root/openclaw-mission-control/` | Python/FastAPI backend + Next.js frontend control plane |
| **openclaw-zero-token** | `/root/openclaw-zero-token/` | TypeScript OpenClaw fork with browser cookie-based AI (no API keys) |

**Authentication:** Local mode (no Clerk). Token: see `.env` → `LOCAL_AUTH_TOKEN` (64+ hex chars).
**ngrok URL:** `https://unmapped-sleet-handled.ngrok-free.dev` (tunnels to frontend:3000)
**Public access:** `http://217.216.34.170:3000` (frontend), `http://217.216.34.170:8000` (backend)

**Docker Compose:** `cd /root/openclaw-mission-control && docker compose ps`
**5 containers:** backend, frontend, db, redis, webhook-worker (all running, all healthy)

**CRITICAL: There are 15 modified + 5 untracked files NOT committed.**
Any `docker compose up --build` will bake in these uncommitted changes.
Before pushing to remote, commit everything: `git add -A && git commit`

---

## Session 1: Zero-Token Gateway Monitoring & Re-Auth (2026-04-10)

### What was done
Implemented a complete monitoring and re-auth system for zero-token (browser cookie-based) AI providers across both repos. This lets Mission Control see which web providers (Claude, ChatGPT, Qwen, DeepSeek, etc.) have valid browser sessions and trigger re-auth when needed.

### openclaw-zero-token changes (12 files, committed)
| File | Type | What |
|------|------|------|
| `src/gateway/server-methods/browser-status.ts` | NEW | `browser.status` gateway method — reports health of all 13 web providers |
| `src/gateway/server-methods/channels-reauth.ts` | NEW | `channels.reauth` gateway method — triggers login/reauth flow |
| `src/gateway/protocol/schema/browser.ts` | NEW | TypeBox schemas: BrowserStatusParams, BrowserStatusResult, BrowserContextStatus, ChannelReauthParams, ChannelReauthResult |
| `src/zero-token/browser-context-registry.ts` | NEW | Singleton for centralized browser context health tracking |
| `src/gateway/server-methods-list.ts` | MOD | Registered `browser.status` and `channels.reauth` in BASE_METHODS |
| `src/gateway/server-methods.ts` | MOD | Added browserHandlers + channelsReauthHandlers to coreGatewayHandlers |
| `src/gateway/server-methods/channels.ts` | MOD | Extended channels.status response with auth_valid, needs_reauth, cookie_expiry, provider_type |
| `src/gateway/protocol/schema.ts` | MOD | Added browser.js re-export |
| `src/gateway/protocol/schema/protocol-schemas.ts` | MOD | Registered all new browser/reauth schemas |
| `src/gateway/protocol/schema/types.ts` | MOD | Added TypeScript type exports for new schemas |
| `src/gateway/protocol/schema/channels.ts` | MOD | Extended ChannelAccountSnapshotSchema with auth fields |
| `src/gateway/protocol/index.ts` | MOD | Added AJV validators + type/schema re-exports |

### mission-control changes (8 files, NOT committed)
| File | Type | What |
|------|------|------|
| `backend/app/services/openclaw/gateway_rpc.py` | MOD | Added `browser.status` and `channels.reauth` to GATEWAY_METHODS |
| `backend/app/schemas/gateway_api.py` | MOD | Added BrowserContextStatus, BrowserStatusResponse, ChannelAuthStatus, ChannelsAuthStatusResponse, ChannelReauthRequest, ChannelReauthResponse |
| `backend/app/services/openclaw/web_model_utils.py` | NEW | is_web_model(), provider_from_model_id(), display_name_for_model(), provider_type() |
| `backend/app/services/openclaw/session_service.py` | MOD | Added get_browser_status(), get_channels_auth_status(), reauth_channel() |
| `backend/app/api/gateway.py` | MOD | Added GET /gateways/browser-status, GET /gateways/channels/auth-status, POST /gateways/channels/{id}/reauth |
| `backend/tests/test_zero_token_gateway.py` | MOD | 11 schema + utility tests (all passing) |
| `frontend/src/components/WebProviderStatus.tsx` | NEW | React component showing web provider auth status with re-auth buttons |
| `frontend/src/components/BrowserHealth.tsx` | NEW | React component showing browser CDP connection health |
| `frontend/src/components/__tests__/WebProviderStatus.test.tsx` | NEW | 4 test cases (loading, success, error, empty) |
| `frontend/src/components/__tests__/BrowserHealth.test.tsx` | NEW | 4 test cases |
| `compose.yml` | MOD | Added openclaw service definition + 3 named volumes (openclaw_profiles, openclaw_cookies, openclaw_sessions) |
| `.env.example` | MOD | Added OPENCLAW_GATEWAY_TOKEN, OPENCLAW_GATEWAY_PORT, OPENCLAW_GATEWAY_URL |
| `docs/zero-token-setup.md` | NEW | Full operational setup guide |

---

## Session 2: Agent Model Assignment (2026-04-11)

### What was done
Added the ability to assign specific AI models (including zero-token web models) to agents. Added a model picker to board creation and edit forms, with a new `GET /gateways/models` endpoint that enriches model lists with web auth status.

### mission-control changes (NOT committed)
| File | Type | What |
|------|------|------|
| `backend/migrations/versions/b1c2d3e4f5a6_add_model_to_agents.py` | NEW | Migration adding `model TEXT` column to agents table |
| `backend/app/models/agents.py` | MOD | Added `model: str | None` field |
| `backend/app/schemas/agents.py` | MOD | Added `model` field to AgentBase and AgentUpdate |
| `backend/app/services/openclaw/gateway_rpc.py` | MOD | `ensure_session()` now accepts and passes `model` param to `sessions.patch` |
| `backend/app/services/openclaw/provisioning.py` | MOD | `ensure_agent_session()` accepts `model`; wake call passes `agent.model` |
| `backend/app/schemas/gateway_api.py` | MOD | Added GatewayModelItem, GatewayModelsResponse |
| `backend/app/services/openclaw/session_service.py` | MOD | Added `get_gateway_models()` — merges models.list with channels.status auth |
| `backend/app/api/gateway.py` | MOD | Added `GET /gateways/models` endpoint |
| `backend/tests/test_zero_token_gateway.py` | MOD | Added 5 new tests (16 total: GatewayModelItem, GatewayModelsResponse, AgentBase model field) |
| `frontend/src/components/WebModelPicker.tsx` | NEW | `<select>` component with Web/API optgroups, disabled for unauth'd web models |
| `frontend/src/components/__tests__/WebModelPicker.test.tsx` | NEW | 4 test cases |
| `frontend/src/app/boards/new/page.tsx` | MOD | Added model picker, stores selection in sessionStorage("pending_board_model") |
| `frontend/src/app/boards/[boardId]/edit/page.tsx` | MOD | Added model picker, pre-fills from lead agent, saves model on board update |

### Migration chain (linear, single head)
```
... → a9b1c2d3e4f7 → b1c2d3e4f5a6 (add_model_to_agents) ← HEAD
```

**⚠️ The migration file `b1c2d3e4f5a6` is UNTRACKED.** It has been applied to the DB but is not in git. A fresh build from scratch will fail without it.

---

## Session 4: sg-leadgen Skill Fix + YES. Response Fix (2026-04-11)

### What was found
The sg-leadgen skill had THREE critical issues:
1. **Hallucination**: The skill instructed the agent to use browser automation (CDP proxy on port 3456) that didn't exist. The LLM read the skill, understood what it SHOULD do, but had no execution path — so it fabricated 50 fake leads.
2. **"YES." responses**: The LLM was prefixing "YES." to every message (even conversational ones) because the tool-calling format prompt didn't explicitly forbid it.
3. **No actionable tools**: The skill never told the agent to use `web_search`, `web_fetch`, `exec` — the actual tools available to web models.

### Root cause analysis
- The sg-leadgen SKILL.md was written for browser automation (CDP proxy or Zero Token browser control)
- The CDP proxy (`skills/browser-cdp/scripts/cdp_proxy.py`) tries to launch its own Chrome instance — conflicts with existing Chrome on port 9222
- Web models (Qwen) have access to: `web_search`, `web_fetch`, `exec`, `read`, `write`, `message`
- The skill never instructed the agent to use these tools

### openclaw-zero-token changes (NOT committed)
| File | Type | What |
|------|------|------|
| `skills/sg-leadgen/SKILL.md` | REWRITTEN | Now uses `web_search` for discovery, `web_fetch` for extraction, `exec` for dedup_score.py |
| `src/zero-token/tool-calling/web-tool-prompt.ts` | MOD | Added "IMPORTANT RESPONSE RULES" to prevent "YES." prefix abuse |

### Key changes to sg-leadgen SKILL.md
- Removed all browser automation references (navigate, click, JS injection)
- Replaced with tool-based workflow: `web_search` → `web_fetch` → `exec` (dedup_score.py) → `write`
- Added explicit "NEVER hallucinate leads" rule
- Added "ALWAYS show progress" and "Be transparent" rules
- Simplified from 7 stages to 5 stages
- Removed CDP proxy dependency entirely
- Added clear JSON/CSV format instructions for intermediate state

### Key changes to web-tool-prompt.ts
- Added EN_TEMPLATE and EN_STRICT_TEMPLATE response rules:
  - Never prefix responses with "YES." unless direct yes/no question
  - Present data directly, don't acknowledge with "YES." first
  - Answer conversational questions naturally

### How to test the fix
1. Send a message to the bot: "find 10 Singapore leads for digital marketing agencies"
2. The agent should now:
   - Use `web_search` to find companies
   - Use `web_fetch` to extract details from directories
   - Use `exec` to run `dedup_score.py`
   - Present REAL data (not hallucinated)
3. The agent should NOT prefix responses with "YES."

---

## Session 3: Infrastructure & Access (2026-04-10)

### Docker / networking fixes
- Created `/root/openclaw-mission-control/.env` with LOCAL_AUTH_TOKEN, OPENCLAW_GATEWAY_TOKEN, AUTH_MODE=local
- Changed compose port bindings from `127.0.0.1:3000` → `0.0.0.0:3000` (already done in compose.yml)
- Fixed frontend port: already bound to `0.0.0.0` in compose.yml
- Backend rebuilt and running on `0.0.0.0:8000`
- ngrok installed and running: `https://unmapped-sleet-handled.ngrok-free.dev` → port 3000 (single tunnel, frontend proxies API internally)

### Chrome / OpenClaw fixes
- Chrome was stale (28h uptime, CDP WebSocket degraded). Killed and restarted on `DISPLAY=:10` via XRDP
- Chrome launched under `remoteuser` with `--ozone-platform=x11` for GUI visibility in remote desktop
- OpenClaw gateway restarted via systemd, running healthy

---

## Current System State (as of 2026-04-11 09:30 UTC)

### Database entities
| Table | Rows | Notes |
|-------|------|-------|
| organizations | 1 | "Personal" (id: 845969d3-...) |
| boards | 1 | "SG Leadgen" (goal-type) |
| agents | 1 | "OpenClaw Zero-Token Gateway Agent" — status=online, **NOT a board lead**, **NO model assigned**, **NOT linked to any board** |
| gateways | 1 | "OpenClaw Zero-Token" (ws://172.19.0.1:3001) |
| users | 1 | "Local User" (admin@home.local) |
| organization_members | 1 | Local User → Personal org |
| board_memory | 0 | Empty (expected — no conversations yet) |
| board_group_memory | 0 | Empty |

### ⚠️ Known Issues

1. **No board lead agent** — The "SG Leadgen" board has 0 lead agents. The only agent is a gateway agent (not board-scoped). The board needs a lead agent provisioned for memory/chat to work.

2. **15 modified + 5 untracked files NOT committed** — All the work from Sessions 1-3 is uncommitted. If the repo is cloned fresh, none of this code will be present. **Must commit before any remote push.**

3. **Migration file untracked** — `b1c2d3e4f5a6_add_model_to_agents.py` exists on disk and is applied to the DB, but is not in git.

4. **Webhook worker reconciliation maxed** — The gateway agent hit 3/3 wake attempts at some point. It recovered (status=online) but this indicates the initial provisioning had issues.

5. **No Clerk auth configured** — AUTH_MODE=local. The "ATO Partners" org name and 3D robot login page are from Clerk.com (a third-party auth service), which is not currently active for this instance.

6. **Memory system is structurally sound but empty** — Both `board_memory` and `board_group_memory` tables exist with proper schemas, indexes, and foreign keys. They're empty because there are no active board conversations.

### What works
- ✅ Mission Control UI accessible via ngrok and direct IP
- ✅ Local auth login with token
- ✅ Backend API serving 200s on all endpoints
- ✅ Gateway connected and online
- ✅ Organization "Personal" created and functional
- ✅ Board "SG Leadgen" created
- ✅ Docker compose: all 5 containers healthy
- ✅ All new gateway methods registered (browser.status, channels.reauth, models.list)

### What doesn't work yet
- ❌ Board has no lead agent (needs provisioning)
- ❌ No model assigned to any agent
- ❌ Memory tables are empty (no conversations to populate them)
- ❌ Web provider auth status not yet checked (no Chrome sessions for AI providers)
- ❌ No code committed to git (15 modified + 5 untracked files)

---

## How to Continue Work

### Starting from scratch (rebuild everything)
```bash
cd /root/openclaw-mission-control
# Make sure the migration file exists (it's untracked!)
ls backend/migrations/versions/b1c2d3e4f5a6_add_model_to_agents.py
docker compose up -d --build
```

### Running tests
```bash
# Backend tests
cd /root/openclaw-mission-control/backend
python3 -m pytest tests/test_zero_token_gateway.py -v  # 16 tests expected

# Frontend build check
cd /root/openclaw-mission-control/frontend
npm run build  # must complete with 0 type errors
```

### Accessing the app
- **ngrok:** https://unmapped-sleet-handled.ngrok-free.dev (click "Visit Site" on interstitial)
- **Direct:** http://217.216.34.170:3000
- **Login token:** see `.env` → LOCAL_AUTH_TOKEN

### Restarting ngrok
```bash
pkill ngrok
nohup ngrok http 3000 > /tmp/ngrok-fwd.log 2>&1 &
sleep 6
curl -s http://127.0.0.1:4040/api/tunnels | python3 -c "import sys,json; [print(t['public_url']) for t in json.load(sys.stdin)['tunnels']]"
```

---

## File Change Summary

### Total files changed/created in this session
| Location | Created | Modified |
|----------|---------|----------|
| `openclaw-zero-token/src/` | 4 | 8 |
| `openclaw-mission-control/backend/` | 2 | 6 |
| `openclaw-mission-control/frontend/` | 4 | 4 |
| `openclaw-mission-control/` (root) | 1 | 2 |
| `openclaw-mission-control/docs/` | 1 | 0 |
| **Total** | **12** | **20** |

---

## Updated File Change Summary

### Session 4 additional changes (2026-04-11)
| File | Change |
|------|--------|
| `openclaw-zero-token/skills/sg-leadgen/SKILL.md` | FULL REWRITE — tool-based instead of browser-based |
| `openclaw-zero-token/src/zero-token/tool-calling/web-tool-prompt.ts` | Added response rules to prevent "YES." prefix abuse |

### Total files changed across all sessions
| Location | Created | Modified |
|----------|---------|----------|
| `openclaw-zero-token/src/` | 4 | 10 |
| `openclaw-zero-token/skills/` | 0 | 1 |
| `openclaw-mission-control/backend/` | 2 | 6 |
| `openclaw-mission-control/frontend/` | 4 | 4 |
| `openclaw-mission-control/` (root) | 2 | 2 |
| `openclaw-mission-control/docs/` | 1 | 0 |
| **Total** | **13** | **23** |

**⚠️ NONE of these changes are committed to git yet.**
