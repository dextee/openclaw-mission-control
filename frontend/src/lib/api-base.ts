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
    if (host) {
      // When served through a reverse proxy (ngrok, Caddy, etc.),
      // the API is on the same origin.
      if (
        host.endsWith(".ngrok-free.dev") ||
        host.endsWith(".ngrok.io") ||
        host.endsWith(".ngrok.app")
      ) {
        return "";
      }
      return `${protocol}://${host}:8000`;
    }
  }

  throw new Error(
    "NEXT_PUBLIC_API_URL is not set and cannot be auto-resolved outside the browser.",
  );
}
