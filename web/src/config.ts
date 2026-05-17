// Runtime configuration.
//
// The 4 config values (API base URL, Cognito Hosted-UI domain, user-pool
// client id, CloudFront URL) are CDK CfnOutputs produced *by* `cdk deploy`.
// The SPA bundle is built BEFORE the stack exists, so build-time
// `import.meta.env.VITE_*` injection would ship empty config and the
// deployed app could not sign in or call the API.
//
// Instead the CDK stack writes a `/config.json` into the SPA bucket from its
// own deploy-resolved values. This module fetches it at RUNTIME (relative to
// the SPA origin) and memoizes the result.
//
// Precedence:
//   1. `/config.json` (production — written by `cdk deploy`)
//   2. `import.meta.env.VITE_*` fallback (local `vite` dev, where
//      `/config.json` 404s) so localhost development still works.

export interface Config {
  apiBaseUrl: string;
  cognitoDomain: string;
  userPoolClientId: string;
  cloudFrontUrl: string;
}

const REQUIRED_KEYS: (keyof Config)[] = [
  "apiBaseUrl",
  "cognitoDomain",
  "userPoolClientId",
  "cloudFrontUrl",
];

let memoized: Config | null = null;
let inflight: Promise<Config> | null = null;

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function validate(raw: unknown, source: string): Config {
  if (!isObject(raw)) {
    throw new Error(`Invalid config from ${source}: expected an object`);
  }
  for (const key of REQUIRED_KEYS) {
    const value = raw[key];
    if (typeof value !== "string" || value.length === 0) {
      throw new Error(
        `Invalid config from ${source}: missing/empty "${key}"`,
      );
    }
  }
  return {
    apiBaseUrl: raw.apiBaseUrl as string,
    cognitoDomain: raw.cognitoDomain as string,
    userPoolClientId: raw.userPoolClientId as string,
    cloudFrontUrl: raw.cloudFrontUrl as string,
  };
}

function devFallback(): Config {
  const env = import.meta.env;
  return validate(
    {
      apiBaseUrl: env.VITE_API_BASE_URL ?? "",
      cognitoDomain: env.VITE_COGNITO_DOMAIN ?? "",
      userPoolClientId: env.VITE_USER_POOL_CLIENT_ID ?? "",
      cloudFrontUrl: env.VITE_CLOUDFRONT_URL ?? "",
    },
    "import.meta.env (dev fallback)",
  );
}

/**
 * Fetch + validate `/config.json` once, memoizing the result. On fetch
 * failure (e.g. local `vite` dev where `/config.json` 404s) falls back to
 * `import.meta.env.VITE_*`. Throws (loudly) if required fields are missing
 * from whichever source resolved.
 */
export async function loadConfig(): Promise<Config> {
  if (memoized) return memoized;
  if (inflight) return inflight;

  inflight = (async (): Promise<Config> => {
    try {
      const res = await fetch("/config.json", { cache: "no-store" });
      if (!res.ok) {
        throw new Error(`/config.json fetch failed: ${res.status}`);
      }
      const json: unknown = await res.json();
      memoized = validate(json, "/config.json");
    } catch (fetchErr) {
      // Production must have /config.json; only the dev fallback rescues a
      // failed fetch. If the fallback is also invalid, surface loudly.
      try {
        memoized = devFallback();
      } catch {
        throw fetchErr instanceof Error
          ? fetchErr
          : new Error("Failed to load /config.json");
      }
    }
    return memoized;
  })();

  try {
    return await inflight;
  } finally {
    inflight = null;
  }
}

/**
 * Synchronous accessor for the memoized config. Throws if `loadConfig()`
 * has not resolved yet — `main.tsx` awaits `loadConfig()` before rendering,
 * so any component / auth / api call site sees a populated config.
 */
export function getConfig(): Config {
  if (!memoized) {
    throw new Error(
      "getConfig() called before loadConfig() resolved — " +
        "ensure main.tsx awaits loadConfig() before render",
    );
  }
  return memoized;
}

/** Test-only: clear memoized state so each test loads fresh config. */
export function __resetConfigForTests(): void {
  memoized = null;
  inflight = null;
}
