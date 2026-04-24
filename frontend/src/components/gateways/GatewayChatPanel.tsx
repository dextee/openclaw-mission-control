"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  type listGatewaySessionsApiV1GatewaysSessionsGetResponse,
  useListGatewaySessionsApiV1GatewaysSessionsGet,
  useGetSessionHistoryApiV1GatewaysSessionsSessionIdHistoryGet,
  useSendGatewaySessionMessageApiV1GatewaysSessionsSessionIdMessagePost,
  getGetSessionHistoryApiV1GatewaysSessionsSessionIdHistoryGetQueryKey,
} from "@/api/generated/gateways/gateways";
import { ApiError } from "@/api/mutator";
import { formatTimestamp } from "@/lib/formatters";

export type GatewaySessionItem = {
  key: string;
  label?: string | null;
  displayName?: string | null;
  status?: string | null;
  model?: string | null;
  updatedAt?: number | null;
};

export type GatewayMessageItem = {
  role?: string | null;
  content?: Array<{ type?: string; text?: string }> | null;
  timestamp?: number | null;
  senderLabel?: string | null;
  stopReason?: string | null;
};

type GatewayChatPanelProps = {
  gatewayUrl: string;
  gatewayToken?: string | null;
  boardId: string;
};

function sessionItemFromRaw(raw: unknown): GatewaySessionItem | null {
  if (typeof raw !== "object" || raw === null) return null;
  const obj = raw as Record<string, unknown>;
  const key = typeof obj.key === "string" ? obj.key : null;
  if (!key) return null;
  return {
    key,
    label: typeof obj.label === "string" ? obj.label : null,
    displayName: typeof obj.displayName === "string" ? obj.displayName : null,
    status: typeof obj.status === "string" ? obj.status : null,
    model: typeof obj.model === "string" ? obj.model : null,
    updatedAt: typeof obj.updatedAt === "number" ? obj.updatedAt : null,
  };
}

function messageItemFromRaw(raw: unknown): GatewayMessageItem | null {
  if (typeof raw !== "object" || raw === null) return null;
  const obj = raw as Record<string, unknown>;
  return {
    role: typeof obj.role === "string" ? obj.role : null,
    content: Array.isArray(obj.content) ? obj.content as Array<{ type?: string; text?: string }> : null,
    timestamp: typeof obj.timestamp === "number" ? obj.timestamp : null,
    senderLabel: typeof obj.senderLabel === "string" ? obj.senderLabel : null,
    stopReason: typeof obj.stopReason === "string" ? obj.stopReason : null,
  };
}

function extractTextContent(msg: GatewayMessageItem): string {
  const parts: string[] = [];
  if (msg.content && Array.isArray(msg.content)) {
    for (const part of msg.content) {
      if (typeof part.text === "string") {
        parts.push(part.text);
      } else if (part.type === "toolCall") {
        parts.push(`[tool: ${(part as unknown as Record<string, string>).name ?? "?"}]`);
      } else if (part.type === "toolResult") {
        parts.push(`[tool result]`);
      }
    }
  }
  return parts.join("").trim();
}

export default function GatewayChatPanel({
  gatewayUrl,
  gatewayToken,
  boardId,
}: GatewayChatPanelProps) {
  const queryClient = useQueryClient();
  const [selectedSessionKey, setSelectedSessionKey] = useState<string | null>(null);
  const [composerValue, setComposerValue] = useState("");
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const sessionsQuery = useListGatewaySessionsApiV1GatewaysSessionsGet<
    listGatewaySessionsApiV1GatewaysSessionsGetResponse,
    ApiError
  >(
    { board_id: boardId },
    {
      query: {
        enabled: Boolean(boardId),
        refetchInterval: 10_000,
      },
    },
  );

  const rawSessions = sessionsQuery.data?.status === 200
    ? (sessionsQuery.data.data.sessions ?? [])
    : [];

  const sessions: GatewaySessionItem[] = rawSessions
    .map(sessionItemFromRaw)
    .filter((s): s is GatewaySessionItem => s !== null);

  const mainSessionKey =
    sessionsQuery.data?.status === 200
      ? ((sessionsQuery.data.data as unknown as Record<string, unknown>).main_session as string | undefined) ?? null
      : null;

  const effectiveSessionKey = selectedSessionKey ?? mainSessionKey ?? (sessions[0]?.key || null);

  const historyQuery = useGetSessionHistoryApiV1GatewaysSessionsSessionIdHistoryGet(
    effectiveSessionKey ?? "",
    { board_id: boardId },
    {
      query: {
        enabled: Boolean(boardId && effectiveSessionKey),
        refetchInterval: 2_000,
      },
    },
  );

  const rawHistory =
    historyQuery.data?.status === 200
      ? ((historyQuery.data.data as unknown as Record<string, unknown>).history as unknown[] | undefined) ?? []
      : [];

  const messages: GatewayMessageItem[] = rawHistory
    .map(messageItemFromRaw)
    .filter((m): m is GatewayMessageItem => m !== null);

  const sendMutation = useSendGatewaySessionMessageApiV1GatewaysSessionsSessionIdMessagePost({
    mutation: {
      onSuccess: () => {
        setComposerValue("");
        if (effectiveSessionKey) {
          void queryClient.invalidateQueries({
            queryKey: getGetSessionHistoryApiV1GatewaysSessionsSessionIdHistoryGetQueryKey(
              effectiveSessionKey,
              { board_id: boardId },
            ),
          });
        }
      },
      onSettled: () => {
        setIsSending(false);
        setTimeout(() => textareaRef.current?.focus(), 0);
      },
    },
  });

  const handleSend = useCallback(async () => {
    const trimmed = composerValue.trim();
    if (!trimmed || !effectiveSessionKey || isSending) return;
    setIsSending(true);
    await sendMutation.mutateAsync({
      sessionId: effectiveSessionKey,
      data: { content: trimmed },
      params: { board_id: boardId },
    });
  }, [composerValue, effectiveSessionKey, isSending, sendMutation, boardId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  return (
    <div className="flex h-[calc(100vh-200px)] min-h-[500px] flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-slate-800">Gateway Chat</h2>
          <span className="text-xs text-slate-400">{gatewayUrl}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">Session:</span>
          <select
            className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 focus:outline-none focus:ring-1 focus:ring-slate-300"
            value={effectiveSessionKey ?? ""}
            onChange={(e) => setSelectedSessionKey(e.target.value || null)}
          >
            {sessions.length === 0 && (
              <option value="">No sessions</option>
            )}
            {sessions.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label || s.displayName || s.key} {s.status ? `(${s.status})` : ""}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-3 pr-1">
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">
            No messages yet. Send a message to start chatting.
          </div>
        )}
        {messages.map((msg, index) => {
          const text = extractTextContent(msg);
          const isUser = msg.role === "user";
          const isTool = msg.role === "toolResult" || msg.role === "assistant" && msg.stopReason === "toolUse";
          return (
            <div
              key={index}
              className={`flex ${isUser ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                  isUser
                    ? "bg-slate-800 text-white"
                    : isTool
                    ? "bg-amber-50 text-amber-800 border border-amber-100"
                    : "bg-slate-100 text-slate-800"
                }`}
              >
                <div className="mb-1 text-[10px] font-medium opacity-70">
                  {isUser ? "You" : msg.senderLabel ?? msg.role ?? "Agent"}
                  {msg.timestamp ? ` · ${formatTimestamp(new Date(msg.timestamp).toISOString())}` : ""}
                </div>
                <div className="whitespace-pre-wrap break-words">{text}</div>
              </div>
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* Composer */}
      <div className="border-t border-slate-100 pt-3">
        <div className="flex gap-2">
          <Textarea
            ref={textareaRef}
            value={composerValue}
            onChange={(e) => setComposerValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void handleSend();
              }
            }}
            placeholder="Message the gateway agent..."
            disabled={isSending || !effectiveSessionKey}
            className="min-h-[60px] flex-1 resize-none"
          />
          <div className="flex flex-col justify-end">
            <Button
              onClick={() => void handleSend()}
              disabled={isSending || !composerValue.trim() || !effectiveSessionKey}
              className="h-10 px-4"
            >
              {isSending ? "Sending…" : "Send"}
            </Button>
          </div>
        </div>
        {sendMutation.isError && (
          <p className="mt-2 text-xs text-red-500">
            Failed to send: {String((sendMutation.error as ApiError)?.message ?? "Unknown error")}
          </p>
        )}
      </div>
    </div>
  );
}
