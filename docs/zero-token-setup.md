# Zero-Token OpenClaw Setup Guide

This guide gets openclaw-zero-token running with Mission Control from scratch.

## Prerequisites

- Docker Engine + Docker Compose v2 (`docker compose`)
- Both repos as sibling directories:
  ```
  ./openclaw-zero-token/
  ./openclaw-mission-control/
  ```
- Run all commands from `openclaw-mission-control/`

## 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set:

| Variable | Value |
|----------|-------|
| `LOCAL_AUTH_TOKEN` | Random string, 50+ chars — this is your Mission Control login token |
| `OPENCLAW_GATEWAY_TOKEN` | Random string, 32+ chars — shared secret between openclaw and Mission Control |
| `BASE_URL` | `http://localhost:8000` (default, fine for local use) |
| `CORS_ORIGINS` | `http://localhost:3000` (default) |

Generate tokens quickly:
```bash
openssl rand -hex 32   # use for OPENCLAW_GATEWAY_TOKEN
openssl rand -hex 32   # use for LOCAL_AUTH_TOKEN (add more chars to hit 50+)
```

## 2. Build and start the full stack

```bash
docker compose up -d --build
```

Services started:
- `db` — PostgreSQL on port 5432 (localhost only)
- `redis` — Redis on port 6379 (localhost only)
- `openclaw` — Zero-token OpenClaw gateway on port 4096 (localhost only)
- `backend` — Mission Control API on port 8000
- `frontend` — Mission Control UI on port 3000
- `webhook-worker` — Background task worker

## 3. Log in to Mission Control

1. Open http://localhost:3000
2. Enter your `LOCAL_AUTH_TOKEN` value as the bearer token

## 4. Register the gateway

1. In Mission Control: go to **Settings → Gateways → Add Gateway**
2. Fill in:
   - **URL**: `ws://localhost:4096` (or `ws://openclaw:4096` if resolving inside Docker)
   - **Token**: your `OPENCLAW_GATEWAY_TOKEN` value
3. Save — the gateway should show **Online**

## 5. Authenticate web providers

1. Navigate to the gateway's detail page
2. The **Zero-Token Web Providers** panel shows auth status for all 13 providers
3. For any provider showing **Needs Reauth**, click **Re-auth**
4. A browser login URL will open — complete the login in your browser
5. The provider's cookie is saved inside the `openclaw_cookies` Docker volume

## 6. Verify health

```bash
# Gateway health
curl http://localhost:4096/healthz

# Backend health
curl http://localhost:8000/healthz

# New endpoints (replace TOKEN with your LOCAL_AUTH_TOKEN)
curl -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/gateways/browser-status?gateway_url=ws://localhost:4096&gateway_token=OPENCLAW_GATEWAY_TOKEN"

curl -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/gateways/channels/auth-status?gateway_url=ws://localhost:4096&gateway_token=OPENCLAW_GATEWAY_TOKEN"
```

## 7. Stop the stack

```bash
docker compose down
```

Cookie and session data is preserved in named Docker volumes (`openclaw_cookies`,
`openclaw_sessions`, `openclaw_profiles`).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Gateway shows Offline | Check `OPENCLAW_GATEWAY_TOKEN` matches in both services; check `docker compose logs openclaw` |
| All providers show Needs Reauth | Expected on first run — complete the Re-auth flow for each provider you want to use |
| Browser health shows CDP down | Normal if no browser contexts have been started yet; start a chat session to wake them |
| `LOCAL_AUTH_TOKEN` login fails | Token must be at least 50 characters |
