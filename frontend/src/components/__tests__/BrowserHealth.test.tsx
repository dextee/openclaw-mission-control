import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BrowserHealth } from "../BrowserHealth";

vi.mock("@/lib/api-base", () => ({ getApiBaseUrl: () => "http://localhost:8000" }));
vi.mock("@/auth/localAuth", () => ({
  isLocalAuthMode: () => true,
  getLocalAuthToken: () => "test-token",
}));

const mockFetch = vi.fn();
global.fetch = mockFetch;

const defaultProps = {};

const mockHealthyContext = {
  provider: "claude-web",
  healthy: true,
  cdp_connected: true,
  last_checked_at: Date.now(),
};

const mockUnhealthyContext = {
  provider: "chatgpt-web",
  healthy: false,
  cdp_connected: false,
  last_checked_at: Date.now(),
};

describe("BrowserHealth", () => {
  beforeEach(() => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        contexts: [mockHealthyContext, mockUnhealthyContext],
      }),
    });
  });

  it("renders healthy provider with green indicator", async () => {
    render(<BrowserHealth {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText("claude-web")).toBeInTheDocument();
    });
  });

  it("renders unhealthy provider with CDP down label", async () => {
    render(<BrowserHealth {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText("chatgpt-web")).toBeInTheDocument();
      expect(screen.getByText("(CDP down)")).toBeInTheDocument();
    });
  });

  it("shows error state when fetch fails", async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 503 });
    render(<BrowserHealth {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText(/Browser health error/)).toBeInTheDocument();
    });
  });

  it("shows empty state when no browser contexts running", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ contexts: [] }),
    });
    render(<BrowserHealth {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText(/No browser contexts running/)).toBeInTheDocument();
    });
  });
});
