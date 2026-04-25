export function getApiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (raw && raw.toLowerCase() !== "auto") {
    const normalized = raw.replace(/\/+$/, "");
    if (!normalized) {
      throw new Error("NEXT_PUBLIC_API_URL is invalid.");
    }
    return normalized;
  }

  if (typeof window !== "undefined") {
    const protocol = window.location.protocol === "https:" ? "https" : "http";
    const host = window.location.hostname;
    const port = window.location.port;
    if (host) {
      // When served through a reverse proxy (ngrok, Caddy, etc.) the API is
      // on the same origin. Detect that by: empty port (default 80/443) OR a
      // port that isn't the dev frontend port (3000). Direct dev mode keeps
      // sending requests to backend:8000.
      if (!port || port !== "3000") {
        return "";
      }
      return `${protocol}://${host}:8000`;
    }
  }

  throw new Error(
    "NEXT_PUBLIC_API_URL is not set and cannot be auto-resolved outside the browser.",
  );
}
