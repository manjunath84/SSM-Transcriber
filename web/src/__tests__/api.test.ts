import { describe, expect, test } from "vitest";
import { parseMe, parseTranscript, parseTranscripts } from "../api";

describe("parseTranscripts", () => {
  test("returns [] for empty list", () => {
    expect(parseTranscripts({ transcripts: [] })).toEqual([]);
  });

  test("preserves order", () => {
    const out = parseTranscripts({
      transcripts: [
        { job_id: "j2", last_modified: "2026-05-02T00:00:00Z" },
        { job_id: "j1", last_modified: "2026-05-01T00:00:00Z" },
      ],
    });
    expect(out.map((t) => t.jobId)).toEqual(["j2", "j1"]);
    expect(out[0].lastModified).toBe("2026-05-02T00:00:00Z");
  });

  test("throws on null body", () => {
    expect(() => parseTranscripts(null)).toThrow();
  });

  test("throws on string body", () => {
    expect(() => parseTranscripts("x")).toThrow();
  });

  test("throws on missing transcripts array", () => {
    expect(() => parseTranscripts({})).toThrow();
  });
});

describe("parseTranscript", () => {
  test("extracts markdown + rawPresent (snake -> camel)", () => {
    expect(parseTranscript({ markdown: "# t", raw_present: true })).toEqual({
      markdown: "# t",
      rawPresent: true,
    });
  });

  test("defaults rawPresent to false when absent", () => {
    expect(parseTranscript({ markdown: "# t" })).toEqual({
      markdown: "# t",
      rawPresent: false,
    });
  });

  test("throws on body missing markdown", () => {
    expect(() => parseTranscript({ raw_present: true })).toThrow();
  });

  test("throws on null body", () => {
    expect(() => parseTranscript(null)).toThrow();
  });
});

describe("parseMe", () => {
  test("maps monthly_budget_usd -> monthlyBudgetUsd", () => {
    expect(parseMe({ email: "a@b.com", monthly_budget_usd: 5 })).toEqual({
      email: "a@b.com",
      monthlyBudgetUsd: 5,
    });
  });

  test("throws on body missing email", () => {
    expect(() => parseMe({ monthly_budget_usd: 5 })).toThrow();
  });
});
