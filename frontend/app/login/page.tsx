"use client";

/** Cognito sign-in and self-service password recovery for the PayLens pilot. */

import { FormEvent, useState } from "react";
import { API_URL } from "../../lib/api";

type AuthMode = "SIGN_IN" | "REQUEST_RESET" | "CONFIRM_RESET";
type AuthConfig = { region: string; client_id: string };

async function loadAuthConfig(): Promise<AuthConfig> {
  const response = await fetch(`${API_URL}/auth/config`);
  const config = await response.json();
  if (!response.ok || !config.region || !config.client_id) {
    throw new Error("Pilot authentication is not configured.");
  }
  return config;
}

function cognitoError(code: string | undefined): string {
  const name = code?.split("#").pop();
  if (name === "CodeMismatchException") return "The verification code was not accepted.";
  if (name === "ExpiredCodeException") return "The verification code expired. Request a new code.";
  if (name === "InvalidPasswordException") return "The new password does not meet the password requirements.";
  if (name === "LimitExceededException") return "Too many attempts were made. Wait briefly and try again.";
  if (name === "NotAuthorizedException" || name === "UserNotFoundException") return "Email or password was not accepted.";
  return "Cognito could not complete the request.";
}

async function cognitoRequest(config: AuthConfig, target: string, body: Record<string, unknown>) {
  const response = await fetch(`https://cognito-idp.${config.region}.amazonaws.com/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-amz-json-1.1",
      "X-Amz-Target": `AWSCognitoIdentityProviderService.${target}`,
    },
    body: JSON.stringify({ ClientId: config.client_id, ...body }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(cognitoError(result?.__type));
  return result;
}

export default function LoginPage() {
  const [mode, setMode] = useState<AuthMode>("SIGN_IN");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(() =>
    typeof window !== "undefined" && new URLSearchParams(window.location.search).get("reason") === "session-expired"
      ? "Your session expired. Sign in again to continue."
      : ""
  );
  const [busy, setBusy] = useState(false);

  function changeMode(next: AuthMode) {
    setMode(next); setError(""); setNotice(""); setPassword(""); setConfirmation(""); setCode("");
  }

  async function signIn(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const config = await loadAuthConfig();
      const result = await cognitoRequest(config, "InitiateAuth", {
        AuthFlow: "USER_PASSWORD_AUTH",
        AuthParameters: { USERNAME: email, PASSWORD: password },
      });
      if (!result.AuthenticationResult?.AccessToken) throw new Error("Email or password was not accepted.");
      window.sessionStorage.setItem("paylens_access_token", result.AuthenticationResult.AccessToken);
      window.location.assign("/");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sign in failed."); setBusy(false);
    }
  }

  async function requestReset(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const config = await loadAuthConfig();
      await cognitoRequest(config, "ForgotPassword", { Username: email });
      setMode("CONFIRM_RESET");
      setNotice("A verification code was sent to your registered email address.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The reset code could not be requested.");
    } finally { setBusy(false); }
  }

  async function confirmReset(event: FormEvent) {
    event.preventDefault(); setError("");
    if (password !== confirmation) { setError("The new passwords do not match."); return; }
    setBusy(true);
    try {
      const config = await loadAuthConfig();
      await cognitoRequest(config, "ConfirmForgotPassword", {
        Username: email, ConfirmationCode: code, Password: password,
      });
      setMode("SIGN_IN"); setPassword(""); setConfirmation(""); setCode("");
      setNotice("Password reset complete. Sign in with your new password.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The password could not be reset.");
    } finally { setBusy(false); }
  }

  return <main className="app-shell"><section className="upload-card auth-card" aria-label="Sign in">
    <div className="upload-heading"><span className="status-dot"/><span>PayLens pilot</span></div>
    {mode === "SIGN_IN" && <>
      <h1>Sign in</h1><p>Use the merchant account issued by your PayLens administrator.</p>
      <form onSubmit={signIn} className="provider-details">
        <label>Email<input type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)}/></label>
        <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)}/></label>
        {notice && <div className="success-banner" role="status">{notice}</div>}
        {error && <div className="error-banner" role="alert">{error}</div>}
        <button className="primary-button" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <button type="button" className="text-button" onClick={() => changeMode("REQUEST_RESET")}>Forgot password?</button>
      </form>
    </>}
    {mode === "REQUEST_RESET" && <>
      <h1>Reset password</h1><p>We will email a one-time verification code to your registered address.</p>
      <form onSubmit={requestReset} className="provider-details">
        <label>Email<input type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)}/></label>
        {error && <div className="error-banner" role="alert">{error}</div>}
        <button className="primary-button" disabled={busy}>{busy ? "Sending code…" : "Send verification code"}</button>
        <button type="button" className="text-button" onClick={() => changeMode("SIGN_IN")}>Back to sign in</button>
      </form>
    </>}
    {mode === "CONFIRM_RESET" && <>
      <h1>Choose a new password</h1><p>Enter the latest verification code sent to {email}.</p>
      <form onSubmit={confirmReset} className="provider-details">
        <label>Verification code<input inputMode="numeric" autoComplete="one-time-code" required value={code} onChange={(event) => setCode(event.target.value)}/></label>
        <label>New password<input type="password" autoComplete="new-password" required value={password} onChange={(event) => setPassword(event.target.value)}/></label>
        <label>Confirm new password<input type="password" autoComplete="new-password" required value={confirmation} onChange={(event) => setConfirmation(event.target.value)}/></label>
        {notice && <div className="success-banner" role="status">{notice}</div>}
        {error && <div className="error-banner" role="alert">{error}</div>}
        <button className="primary-button" disabled={busy}>{busy ? "Resetting password…" : "Reset password"}</button>
        <button type="button" className="text-button" onClick={() => changeMode("REQUEST_RESET")}>Request another code</button>
      </form>
    </>}
  </section></main>;
}
