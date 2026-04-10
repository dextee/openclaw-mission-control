"use client";

import { useEffect, useState } from "react";

interface BrowserContextStatus {
  provider: string;
  healthy: boolean;
  cdp_connected: boolean;
  last_checked_at: number | null;
}

interface Props {
  boardId?: string;
  gatewayUrl?: string;
  gatewayToken?: string;
  apiBaseUrl: string;
  authHeader: string;
}

export function BrowserHealth({
  boardId,
  gatewayUrl,
  gatewayToken,
  apiBaseUrl,
  authHeader,
}: Props) {
  const [contexts, setContexts] = useState<BrowserContextStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchStatus = async () => {
      const params = new URLSearchParams();
      if (boardId) params.set("board_id", boardId);
      if (gatewayUrl) params.set("gateway_url", gatewayUrl);
      if (gatewayToken) params.set("gateway_token", gatewayToken);
      try {
        const res = await fetch(
          `${apiBaseUrl}/gateways/browser-status?${params}`,
          {
            headers: { Authorization: authHeader },
          },
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setContexts(data.contexts ?? []);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load");
      } finally {
        setLoading(false);
      }
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 15_000);
    return () => clearInterval(interval);
  }, [boardId, gatewayUrl, gatewayToken]);

  if (loading)
    return <div className="text-sm text-gray-500">Checking browser health…</div>;
  if (error)
    return (
      <div className="text-sm text-red-600">Browser health error: {error}</div>
    );
  if (contexts.length === 0)
    return (
      <div className="text-sm text-gray-400">No browser contexts running.</div>
    );

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-gray-700">Browser Context Health</h3>
      <div className="flex flex-wrap gap-2">
        {contexts.map((ctx) => (
          <div
            key={ctx.provider}
            className={`flex items-center gap-1.5 rounded border px-2 py-1 text-xs ${
              ctx.healthy && ctx.cdp_connected
                ? "border-green-200 bg-green-50 text-green-800"
                : "border-red-200 bg-red-50 text-red-800"
            }`}
          >
            <span
              className={`inline-block h-2 w-2 rounded-full ${
                ctx.healthy && ctx.cdp_connected ? "bg-green-500" : "bg-red-500"
              }`}
            />
            {ctx.provider}
            {!ctx.cdp_connected && (
              <span className="opacity-70">(CDP down)</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
