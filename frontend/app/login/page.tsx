"use client";

import { FormEvent, useState } from "react";
import { API_URL } from "../../lib/api";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function signIn(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const configResponse = await fetch(`${API_URL}/auth/config`);
      const config = await configResponse.json();
      if (!config.region || !config.client_id) throw new Error("Pilot authentication is not configured.");
      const response = await fetch(`https://cognito-idp.${config.region}.amazonaws.com/`, {
        method: "POST", headers: { "Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth" },
        body: JSON.stringify({ AuthFlow: "USER_PASSWORD_AUTH", ClientId: config.client_id, AuthParameters: { USERNAME: email, PASSWORD: password } }),
      });
      const result = await response.json();
      if (!response.ok || !result.AuthenticationResult?.AccessToken) throw new Error("Email or password was not accepted.");
      window.sessionStorage.setItem("paylens_access_token", result.AuthenticationResult.AccessToken);
      window.location.assign("/");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Sign in failed."); setBusy(false); }
  }

  return <main className="app-shell"><section className="upload-card" aria-label="Sign in">
    <div className="upload-heading"><span className="status-dot"/><span>PayLens pilot</span></div>
    <h1>Sign in</h1><p>Use the merchant account issued by your PayLens administrator.</p>
    <form onSubmit={signIn} className="provider-details">
      <label>Email<input type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)}/></label>
      <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)}/></label>
      {error && <div className="error-banner" role="alert">{error}</div>}
      <button className="primary-button" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
    </form>
  </section></main>;
}
