/** Browser-side session hints for navigation only; the API still validates every token. */
export const SESSION_KEY = "paylens_access_token";
export const SESSION_CHANGED = "paylens-session-changed";

export function hasLocalDevAccess(): boolean {
  return Boolean(process.env.NEXT_PUBLIC_PAYLENS_DEV_API_KEY);
}

export function hasActiveSession(): boolean {
  if (typeof window === "undefined") return false;
  const token = window.sessionStorage.getItem(SESSION_KEY);
  if (!token) return false;
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))) as { exp?: number };
    return typeof payload.exp === "number" && payload.exp * 1000 > Date.now();
  } catch {
    return false;
  }
}

export function clearSession(): void {
  window.sessionStorage.removeItem(SESSION_KEY);
  window.dispatchEvent(new Event(SESSION_CHANGED));
}

export function subscribeSession(update: () => void): () => void {
  window.addEventListener(SESSION_CHANGED, update);
  window.addEventListener("focus", update);
  return () => { window.removeEventListener(SESSION_CHANGED, update); window.removeEventListener("focus", update); };
}

export function noServerSession(): boolean { return false; }

/** Prevent external redirects and keep the original in-app destination after sign-in. */
export function safeReturnPath(value: string | null): string {
  return value?.startsWith("/") && !value.startsWith("//") && !value.startsWith("/\\") && !value.startsWith("/login") ? value : "/";
}
