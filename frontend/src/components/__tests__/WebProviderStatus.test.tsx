import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WebProviderStatus } from "../WebProviderStatus";

vi.mock("@/lib/api-base", () => ({ getApiBaseUrl: () => "http://localhost:8000" }));
vi.mock("@/auth/localAuth", () => ({
  isLocalAuthMode: () => true,
  getLocalAuthToken: () => "test-token",
}));

const mockFetch = vi.fn();
global.fetch = mockFetch;

const defaultProps = {};

const mockAuthenticatedChannel = {
  channel_id: "claude-web",
  auth_valid: true,
  needs_reauth: false,
  cookie_expiry: Date.now() + 3600000,
  provider_type: "web",
};

const mockExpiredChannel = {
  channel_id: "chatgpt-web",
  auth_valid: false,
  needs_reauth: true,
  cookie_expiry: Date.now() - 1000,
  provider_type: "web",
};

describe("WebProviderStatus", () => {
  beforeEach(() => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        channels: [mockAuthenticatedChannel, mockExpiredChannel],
      }),
    });
  });

  it("renders authenticated provider with green badge", async () => {
    render(<WebProviderStatus {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText("Claude")).toBeInTheDocument();
      expect(screen.getByText("Authenticated")).toBeInTheDocument();
    });
  });

  it("renders expired provider with reauth button", async () => {
    render(<WebProviderStatus {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText("ChatGPT")).toBeInTheDocument();
      expect(screen.getByText("Needs Reauth")).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /re-auth/i }),
      ).toBeInTheDocument();
    });
  });

  it("shows error state when fetch fails", async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500 });
    render(<WebProviderStatus {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText(/Error/)).toBeInTheDocument();
    });
  });

  it("shows empty state when no web providers", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ channels: [] }),
    });
    render(<WebProviderStatus {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText(/No web providers/)).toBeInTheDocument();
    });
  });
});
