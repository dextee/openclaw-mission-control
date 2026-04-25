"use client";

import { useEffect, useState } from "react";
import { getApiBaseUrl } from "@/lib/api-base";
import { getLocalAuthToken, isLocalAuthMode } from "@/auth/localAuth";

interface ChannelAuthStatus {
  channel_id: string;
  auth_valid: boolean;
  needs_reauth: boolean;
  cookie_expiry: number | null;
  provider_type: "web" | "api";
}

interface Props {
  boardId?: string;
  gatewayUrl?: string;
  gatewayToken?: string;
}

const PROVIDER_LABELS: Record<string, string> = {
  "claude-web": "Claude",
  "chatgpt-web": "ChatGPT",
  "gemini-web": "Gemini",
  "deepseek-web": "DeepSeek",
  "grok-web": "Grok",
  "kimi-web": "Kimi",
  "qwen-web": "Qwen",
  "qwen-cn-web": "Qwen CN",
  "glm-web": "GLM",
  "glm-intl-web": "GLM Intl",
  "doubao-web": "Doubao",
  "perplexity-web": "Perplexity",
  "xiaomimo-web": "Xiaomi Mo",
};

async function getAuthHeader(): Promise<string> {
  if (isLocalAuthMode()) {
    const token = getLocalAuthToken();
    return token ? `Bearer ${token}` : "";
  }
  // Clerk path
  try {
    type ClerkGlobal = { session?: { getToken: () => Promise<string> } | null };
    const clerk = (window as unknown as { Clerk?: ClerkGlobal }).Clerk;
    if (clerk?.session) {
      const token = await clerk.session.getToken();
      if (token) return `Bearer ${token}`;
    }
  } catch {
    // fall through
  }
  return "";
}

function statusBadge(ch: ChannelAuthStatus) {
  if (ch.provider_type !== "web") return null;
  if (ch.auth_valid && !ch.needs_reauth)
    return (
      <span className="rounded bg-green-100 px-2 py-0.5 text-xs text-green-800">
        Authenticated
      </span>
    );
  if (ch.needs_reauth)
    return (
      <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-800">
        Needs Reauth
      </span>
    );
  return (
    <span className="rounded bg-yellow-100 px-2 py-0.5 text-xs text-yellow-800">
      Unknown
    </span>
  );
}

function expiryLabel(expiry: number | null): string {
  if (!expiry) return "";
  const diff = expiry - Date.now();
  if (diff <= 0) return "Expired";
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return "< 1h remaining";
  if (hours < 24) return `${hours}h remaining`;
  return `${Math.floor(hours / 24)}d remaining`;
}

export function WebProviderStatus({
  boardId,
  gatewayUrl,
  gatewayToken,
}: Props) {
  const [channels, setChannels] = useState<ChannelAuthStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reauthingId, setReauthingId] = useState<string | null>(null);

  const fetchStatus = async () => {
    const params = new URLSearchParams();
    if (boardId) params.set("board_id", boardId);
    if (gatewayUrl) params.set("gateway_url", gatewayUrl);
    if (gatewayToken) params.set("gateway_token", gatewayToken);

    try {
      const authHeader = await getAuthHeader();
      const apiBaseUrl = getApiBaseUrl();
      const res = await fetch(
        `${apiBaseUrl}/api/v1/gateways/channels/auth-status?${params}`,
        {
          headers: { Authorization: authHeader },
        },
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setChannels(
        (data.channels as ChannelAuthStatus[]).filter(
          (c) => c.provider_type === "web",
        ),
      );
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 30_000);
    return () => clearInterval(interval);
  }, [boardId, gatewayUrl, gatewayToken]);

  const handleReauth = async (channelId: string) => {
    setReauthingId(channelId);
    const params = new URLSearchParams();
    if (boardId) params.set("board_id", boardId);
    if (gatewayUrl) params.set("gateway_url", gatewayUrl);
    if (gatewayToken) params.set("gateway_token", gatewayToken);
    try {
      const authHeader = await getAuthHeader();
      const apiBaseUrl = getApiBaseUrl();
      const res = await fetch(
        `${apiBaseUrl}/api/v1/gateways/channels/${encodeURIComponent(channelId)}/reauth?${params}`,
        { method: "POST", headers: { Authorization: authHeader } },
      );
      const data = await res.json();
      if (data.auth_url) {
        window.open(data.auth_url, "_blank", "noopener,noreferrer");
      }
      await fetchStatus();
    } catch {
      // silent -- status will refresh on next poll
    } finally {
      setReauthingId(null);
    }
  };

  if (loading)
    return <div className="text-sm text-gray-500">Loading web provider status…</div>;
  if (error) return <div className="text-sm text-red-600">Error: {error}</div>;
  if (channels.length === 0)
    return <div className="text-sm text-gray-400">No web providers detected.</div>;

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-gray-700">Web Provider Auth Status</h3>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {channels.map((ch) => (
          <div
            key={ch.channel_id}
            className="flex items-center justify-between rounded border border-gray-200 bg-white px-3 py-2 shadow-sm"
          >
            <div className="flex flex-col gap-0.5">
              <span className="text-sm font-medium">
                {PROVIDER_LABELS[ch.channel_id] ?? ch.channel_id}
              </span>
              {ch.cookie_expiry && (
                <span className="text-xs text-gray-500">
                  {expiryLabel(ch.cookie_expiry)}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {statusBadge(ch)}
              {ch.needs_reauth && (
                <button
                  onClick={() => handleReauth(ch.channel_id)}
                  disabled={reauthingId === ch.channel_id}
                  className="rounded bg-blue-600 px-2 py-0.5 text-xs text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {reauthingId === ch.channel_id ? "…" : "Re-auth"}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
