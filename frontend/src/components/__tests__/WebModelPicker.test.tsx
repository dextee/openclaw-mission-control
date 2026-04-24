import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WebModelPicker } from "../WebModelPicker";

vi.mock("@/lib/api-base", () => ({ getApiBaseUrl: () => "http://localhost:8000" }));
vi.mock("@/auth/localAuth", () => ({
  isLocalAuthMode: () => true,
  getLocalAuthToken: () => "test-token",
}));

const mockFetch = vi.fn();
global.fetch = mockFetch;

const mockModels = [
  {
    id: "claude-web/claude-sonnet-4-6",
    name: "Claude Sonnet 4.6 (Web)",
    provider: "claude-web",
    provider_type: "web",
    auth_valid: true,
    needs_reauth: false,
    context_window: 200000,
  },
  {
    id: "chatgpt-web/gpt-4",
    name: "GPT-4 (Web)",
    provider: "chatgpt-web",
    provider_type: "web",
    auth_valid: false,
    needs_reauth: true,
    context_window: 128000,
  },
];

describe("WebModelPicker", () => {
  beforeEach(() => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ models: mockModels }),
    });
  });

  it("renders model options after loading", async () => {
    render(<WebModelPicker value="" onChange={() => {}} />);
    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeInTheDocument();
      expect(screen.getByText(/Claude Sonnet/)).toBeInTheDocument();
    });
  });

  it("marks unauthenticated models as disabled", async () => {
    render(<WebModelPicker value="" onChange={() => {}} />);
    await waitFor(() => {
      const gpt4Option = screen.getByText(/GPT-4.*needs reauth/i);
      expect(gpt4Option).toBeInTheDocument();
    });
  });

  it("shows loading skeleton initially", () => {
    mockFetch.mockImplementation(() => new Promise(() => {}));
    const { container } = render(<WebModelPicker value="" onChange={() => {}} />);
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("shows error message on fetch failure", async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500 });
    render(<WebModelPicker value="" onChange={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText(/Failed to load models/)).toBeInTheDocument();
    });
  });
});
