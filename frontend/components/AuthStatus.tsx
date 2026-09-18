"use client";

/** Consistent, keyboard-accessible session control in the upper-right navigation. */
import Link from "next/link";
import { useSyncExternalStore } from "react";
import { clearSession, hasActiveSession, hasLocalDevAccess, noServerSession, subscribeSession } from "../lib/session";

export function AuthStatus() {
  const signedIn = useSyncExternalStore(subscribeSession, hasActiveSession, noServerSession);

  if (hasLocalDevAccess()) return <span className="local-badge">Local development</span>;
  if (!signedIn) return <Link className="secondary-button" href="/login">Sign in</Link>;
  return <span className="auth-status"><span className="session-label">● Signed in</span><button type="button" className="secondary-button" onClick={() => { clearSession(); window.location.assign("/login"); }}>Sign out</button></span>;
}
