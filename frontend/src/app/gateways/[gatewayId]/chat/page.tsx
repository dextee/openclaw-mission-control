"use client";

export const dynamic = "force-dynamic";

import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { Button } from "@/components/ui/button";
import GatewayChatPanel from "@/components/gateways/GatewayChatPanel";
import { ApiError } from "@/api/mutator";
import {
  type getGatewayApiV1GatewaysGatewayIdGetResponse,
  useGetGatewayApiV1GatewaysGatewayIdGet,
} from "@/api/generated/gateways/gateways";
import {
  type listBoardsApiV1BoardsGetResponse,
  useListBoardsApiV1BoardsGet,
} from "@/api/generated/boards/boards";
import { useOrganizationMembership } from "@/lib/use-organization-membership";

export default function GatewayChatPage() {
  const router = useRouter();
  const params = useParams();
  const { isSignedIn } = useAuth();
  const gatewayIdParam = params?.gatewayId;
  const gatewayId = Array.isArray(gatewayIdParam)
    ? gatewayIdParam[0]
    : gatewayIdParam;

  const { isAdmin } = useOrganizationMembership(isSignedIn);

  const gatewayQuery = useGetGatewayApiV1GatewaysGatewayIdGet<
    getGatewayApiV1GatewaysGatewayIdGetResponse,
    ApiError
  >(gatewayId ?? "", {
    query: {
      enabled: Boolean(isSignedIn && isAdmin && gatewayId),
      refetchInterval: 30_000,
    },
  });

  const gateway =
    gatewayQuery.data?.status === 200 ? gatewayQuery.data.data : null;

  const boardsQuery = useListBoardsApiV1BoardsGet<
    listBoardsApiV1BoardsGetResponse,
    ApiError
  >(
    gatewayId ? { gateway_id: gatewayId } : undefined,
    {
      query: {
        enabled: Boolean(isSignedIn && isAdmin && gatewayId),
        refetchInterval: 30_000,
      },
    },
  );

  const boards =
    boardsQuery.data?.status === 200
      ? (boardsQuery.data.data.items ?? [])
      : [];

  const board = boards[0] ?? null;

  if (!isSignedIn || !isAdmin) {
    return (
      <DashboardPageLayout
        signedOut={{
          message: "Sign in to view gateway chat.",
          forceRedirectUrl: gatewayId ? `/gateways/${gatewayId}/chat` : "/gateways",
        }}
        title="Gateway Chat"
      >
        <div className="flex h-64 items-center justify-center text-sm text-slate-500">
          You must be signed in as an admin to view this page.
        </div>
      </DashboardPageLayout>
    );
  }

  if (gatewayQuery.isLoading || boardsQuery.isLoading) {
    return (
      <DashboardPageLayout
        signedOut={{
          message: "Sign in to view gateway chat.",
          forceRedirectUrl: gatewayId ? `/gateways/${gatewayId}/chat` : "/gateways",
        }}
        title="Gateway Chat"
      >
        <div className="flex h-64 items-center justify-center text-sm text-slate-500">
          Loading gateway…
        </div>
      </DashboardPageLayout>
    );
  }

  if (!gateway) {
    return (
      <DashboardPageLayout
        signedOut={{
          message: "Sign in to view gateway chat.",
          forceRedirectUrl: gatewayId ? `/gateways/${gatewayId}/chat` : "/gateways",
        }}
        title="Gateway Chat"
      >
        <div className="flex h-64 items-center justify-center text-sm text-slate-500">
          Gateway not found.
        </div>
      </DashboardPageLayout>
    );
  }

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to view gateway chat.",
        forceRedirectUrl: gatewayId ? `/gateways/${gatewayId}/chat` : "/gateways",
      }}
      title={gateway?.name ? `${gateway.name} — Chat` : "Gateway Chat"}
      description="Chat directly with the gateway agent."
    >
      <div className="mx-auto max-w-5xl space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-slate-900">
              {gateway.name}
            </h1>
            <p className="text-xs text-slate-500">Gateway Chat</p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push(`/gateways/${gatewayId}`)}
            >
              Back to Gateway
            </Button>
          </div>
        </div>

        {!board ? (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-800">
            <p className="font-medium">No board linked to this gateway.</p>
            <p className="mt-1">
              Gateway chat requires a board to be linked to the gateway. Create a board and assign this gateway to it.
            </p>
          </div>
        ) : (
          <GatewayChatPanel
            gatewayUrl={gateway.url}
            gatewayToken={gateway.token}
            boardId={board.id}
          />
        )}
      </div>
    </DashboardPageLayout>
  );
}
