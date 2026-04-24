"use client";

import { useEffect, useState } from "react";
import { getApiBaseUrl } from "@/lib/api-base";
import { getLocalAuthToken, isLocalAuthMode } from "@/auth/localAuth";

interface GatewayModelItem {
  id: string;
  name: string;
  provider: string;
  provider_type: "web" | "api";
  auth_valid: boolean;
  needs_reauth: boolean;
  context_window: number | null;
}

interface Props {
  boardId?: string;
  gatewayUrl?: string;
  gatewayToken?: string;
  value: string;
  onChange: (modelId: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

async function getAuthHeader(): Promise<string> {
  if (isLocalAuthMode()) {
    const token = getLocalAuthToken();
    return token ? `Bearer ${token}` : "";
  }
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

export function WebModelPicker({
  boardId,
  gatewayUrl,
  gatewayToken,
  value,
  onChange,
  disabled = false,
  placeholder = "Select a model…",
}: Props) {
  const [models, setModels] = useState<GatewayModelItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      const params = new URLSearchParams();
      if (boardId) params.set("board_id", boardId);
      if (gatewayUrl) params.set("gateway_url", gatewayUrl);
      if (gatewayToken) params.set("gateway_token", gatewayToken);

      try {
        const authHeader = await getAuthHeader();
        const apiBaseUrl = getApiBaseUrl();
        const res = await fetch(`${apiBaseUrl}/gateways/models?${params}`, {
          headers: authHeader ? { Authorization: authHeader } : {},
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setModels(data.models ?? []);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load models");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [boardId, gatewayUrl, gatewayToken]);

  const webModels = models.filter((m) => m.provider_type === "web");
  const apiModels = models.filter((m) => m.provider_type === "api");

  if (loading) {
    return (
      <div className="h-9 w-full animate-pulse rounded-md border border-slate-200 bg-slate-100" />
    );
  }

  if (error) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
        Failed to load models: {error}
      </div>
    );
  }

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
    >
      <option value="">{placeholder}</option>

      {webModels.length > 0 && (
        <optgroup label="Web Models (Zero-Token)">
          {webModels.map((m) => (
            <option key={m.id} value={m.id} disabled={!m.auth_valid}>
              {m.name}
              {!m.auth_valid ? " (needs reauth)" : ""}
            </option>
          ))}
        </optgroup>
      )}

      {apiModels.length > 0 && (
        <optgroup label="API Models">
          {apiModels.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </optgroup>
      )}
    </select>
  );
}
