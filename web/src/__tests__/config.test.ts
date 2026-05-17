import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

const VALID = {
  apiBaseUrl: "https://api.example.com",
  cognitoDomain: "https://pool.auth.us-east-1.amazoncognito.com",
  userPoolClientId: "abc123",
  cloudFrontUrl: "https://d111.cloudfront.net",
};

function mockFetch(impl: () => Promise<Response> | Response) {
  vi.stubGlobal("fetch", vi.fn(impl));
}

async function freshConfigModule() {
  vi.resetModules();
  return import("../config");
}

describe("config runtime loader", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("loadConfig fetches + validates /config.json and getConfig returns it", async () => {
    mockFetch(
      () =>
        new Response(JSON.stringify(VALID), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    const { loadConfig, getConfig } = await freshConfigModule();

    const cfg = await loadConfig();
    expect(cfg).toEqual(VALID);
    expect(getConfig()).toEqual(VALID);
  });

  test("loadConfig memoizes (second call does not re-fetch)", async () => {
    const fetchMock = vi.fn(
      () =>
        new Response(JSON.stringify(VALID), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { loadConfig } = await freshConfigModule();

    await loadConfig();
    await loadConfig();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  test("getConfig throws before loadConfig resolves", async () => {
    const { getConfig } = await freshConfigModule();
    expect(() => getConfig()).toThrow(/before loadConfig/);
  });

  test("loadConfig throws when required fields are missing (no dev fallback)", async () => {
    mockFetch(
      () =>
        new Response(JSON.stringify({ apiBaseUrl: "https://api.example.com" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    // Ensure no VITE_* env so the dev fallback also fails -> loud throw.
    vi.stubEnv("VITE_API_BASE_URL", "");
    vi.stubEnv("VITE_COGNITO_DOMAIN", "");
    vi.stubEnv("VITE_USER_POOL_CLIENT_ID", "");
    vi.stubEnv("VITE_CLOUDFRONT_URL", "");
    const { loadConfig } = await freshConfigModule();

    await expect(loadConfig()).rejects.toThrow(/missing\/empty/);
  });

  test("falls back to import.meta.env.VITE_* when /config.json fetch fails", async () => {
    mockFetch(() => new Response("not found", { status: 404 }));
    vi.stubEnv("VITE_API_BASE_URL", VALID.apiBaseUrl);
    vi.stubEnv("VITE_COGNITO_DOMAIN", VALID.cognitoDomain);
    vi.stubEnv("VITE_USER_POOL_CLIENT_ID", VALID.userPoolClientId);
    vi.stubEnv("VITE_CLOUDFRONT_URL", VALID.cloudFrontUrl);
    const { loadConfig } = await freshConfigModule();

    const cfg = await loadConfig();
    expect(cfg).toEqual(VALID);
  });
});
