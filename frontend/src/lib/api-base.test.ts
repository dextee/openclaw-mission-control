import { afterEach, describe, expect, it, vi } from "vitest";

import { getApiBaseUrl } from "./api-base";

function setLocation(url: string): void {
  const parsed = new URL(url);
  Object.defineProperty(window, "location", {
    configurable: true,
    value: {
      ...window.location,
      href: parsed.href,
      origin: parsed.origin,
      protocol: parsed.protocol,
      hostname: parsed.hostname,
      host: parsed.host,
      port: parsed.port,
    },
  });
}

describe("getApiBaseUrl", () => {
  const originalLocation = window.location;

  afterEach(() => {
    vi.unstubAllEnvs();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
  });

  it("returns normalized explicit URL", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com///");

    expect(getApiBaseUrl()).toBe("https://api.example.com");
  });

  it("auto-resolves from browser host when set to auto", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "auto");

    expect(getApiBaseUrl()).toBe("http://localhost:8000");
  });

  it("auto-resolves from browser host when unset", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");

    expect(getApiBaseUrl()).toBe("http://localhost:8000");
  });

  it("returns same-origin when served on default HTTPS port (reverse proxy)", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");
    setLocation("https://app.example.com/");

    expect(getApiBaseUrl()).toBe("");
  });

  it("returns same-origin when served on a non-3000 port (reverse proxy)", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");
    setLocation("https://app.example.com:8443/");

    expect(getApiBaseUrl()).toBe("");
  });

  it("returns same-origin for ngrok hostnames", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");
    setLocation("https://unmapped-sleet-handled.ngrok-free.dev/");

    expect(getApiBaseUrl()).toBe("");
  });
});
