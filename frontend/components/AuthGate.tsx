"use client";

/** Show login before private screens; this is UX, not a substitute for API authorization. */
import { useEffect, useSyncExternalStore } from "react";
import { usePathname } from "next/navigation";
import { hasActiveSession, hasLocalDevAccess, noServerSession, subscribeSession } from "../lib/session";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const signedIn = useSyncExternalStore(subscribeSession, hasActiveSession, noServerSession);
  useEffect(() => {
    if (pathname === "/login" || hasLocalDevAccess() || signedIn) return;
    const destination = window.location.pathname + window.location.search;
    window.location.replace(`/login?next=${encodeURIComponent(destination)}`);
  }, [pathname, signedIn]);

  if (pathname === "/login" || hasLocalDevAccess() || signedIn) return <>{children}</>;
  return <main className="app-shell page-state" role="status">Opening sign in…</main>;
}
