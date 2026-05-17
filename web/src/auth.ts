// Cognito Hosted-UI Authorization-Code + PKCE flow.
//
// Identity-only for Phase 7a: scopes are "openid email" (NO Drive scope —
// Drive access is Phase 7c). No refresh-token handling — that is out of
// scope for this slice (re-login on expiry is acceptable for 7a).

import { config } from "./config";

const VERIFIER_KEY = "pkce_verifier";
const ID_TOKEN_KEY = "id_token";
const ACCESS_TOKEN_KEY = "access_token";

let idTokenMem: string | null = null;
let accessTokenMem: string | null = null;

function base64UrlEncode(bytes: Uint8Array): string {
  let str = "";
  for (const b of bytes) str += String.fromCharCode(b);
  return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function randomVerifier(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes);
}

export async function pkceChallenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(verifier),
  );
  return base64UrlEncode(new Uint8Array(digest));
}

function redirectUri(): string {
  const origin = config.cloudFrontUrl || window.location.origin;
  return `${origin.replace(/\/$/, "")}/callback`;
}

export async function beginLogin(): Promise<void> {
  const verifier = randomVerifier();
  sessionStorage.setItem(VERIFIER_KEY, verifier);
  const challenge = await pkceChallenge(verifier);

  const params = new URLSearchParams({
    response_type: "code",
    client_id: config.userPoolClientId,
    identity_provider: "Google",
    scope: "openid email",
    redirect_uri: redirectUri(),
    code_challenge: challenge,
    code_challenge_method: "S256",
  });

  window.location.assign(
    `${config.cognitoDomain.replace(/\/$/, "")}/oauth2/authorize?${params.toString()}`,
  );
}

export async function completeLogin(code: string): Promise<void> {
  const verifier = sessionStorage.getItem(VERIFIER_KEY);
  if (!verifier) throw new Error("Missing PKCE verifier");

  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: config.userPoolClientId,
    code,
    redirect_uri: redirectUri(),
    code_verifier: verifier,
  });

  const res = await fetch(
    `${config.cognitoDomain.replace(/\/$/, "")}/oauth2/token`,
    {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
    },
  );
  if (!res.ok) throw new Error(`Token exchange failed: ${res.status}`);

  const json: unknown = await res.json();
  if (
    typeof json !== "object" ||
    json === null ||
    typeof (json as { id_token?: unknown }).id_token !== "string"
  ) {
    throw new Error("Token response missing id_token");
  }
  const tokens = json as { id_token: string; access_token?: string };

  idTokenMem = tokens.id_token;
  accessTokenMem = tokens.access_token ?? null;
  sessionStorage.setItem(ID_TOKEN_KEY, idTokenMem);
  if (accessTokenMem) sessionStorage.setItem(ACCESS_TOKEN_KEY, accessTokenMem);
  sessionStorage.removeItem(VERIFIER_KEY);
}

export function getIdToken(): string | null {
  if (idTokenMem) return idTokenMem;
  idTokenMem = sessionStorage.getItem(ID_TOKEN_KEY);
  return idTokenMem;
}

export function logout(): void {
  idTokenMem = null;
  accessTokenMem = null;
  sessionStorage.removeItem(ID_TOKEN_KEY);
  sessionStorage.removeItem(ACCESS_TOKEN_KEY);
  sessionStorage.removeItem(VERIFIER_KEY);
}
