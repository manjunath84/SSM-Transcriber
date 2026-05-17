// Typed fetch wrappers for the SSM-Transcriber backend API.
//
// Pure response parsers are exported so unit tests exercise the parsing
// logic directly without touching the network. TanStack Query hooks that
// consume these are Task 14 (not here).

import { getIdToken } from "./auth";
import { config } from "./config";

export interface TranscriptSummary {
  jobId: string;
  lastModified: string;
}

export interface TranscriptDetail {
  markdown: string;
  rawPresent: boolean;
}

export interface Me {
  email: string;
  monthlyBudgetUsd: number;
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function parseTranscripts(json: unknown): TranscriptSummary[] {
  if (!isObject(json) || !Array.isArray(json.transcripts)) {
    throw new Error("Malformed /transcripts response: expected {transcripts:[]}");
  }
  return json.transcripts.map((row): TranscriptSummary => {
    if (!isObject(row) || typeof row.job_id !== "string") {
      throw new Error("Malformed transcript row: missing job_id");
    }
    return {
      jobId: row.job_id,
      lastModified:
        typeof row.last_modified === "string" ? row.last_modified : "",
    };
  });
}

export function parseTranscript(json: unknown): TranscriptDetail {
  if (!isObject(json) || typeof json.markdown !== "string") {
    throw new Error("Malformed transcript response: missing markdown");
  }
  return {
    markdown: json.markdown,
    rawPresent: json.raw_present === true,
  };
}

export function parseMe(json: unknown): Me {
  if (!isObject(json) || typeof json.email !== "string") {
    throw new Error("Malformed /users/me response: missing email");
  }
  return {
    email: json.email,
    monthlyBudgetUsd:
      typeof json.monthly_budget_usd === "number"
        ? json.monthly_budget_usd
        : 0,
  };
}

function authHeaders(): HeadersInit {
  const token = getIdToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function apiUrl(path: string): string {
  return `${config.apiBaseUrl.replace(/\/$/, "")}${path}`;
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  const res = await fetch(apiUrl(path), {
    ...init,
    headers: { ...authHeaders(), ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    throw new Error(`Request failed: ${init?.method ?? "GET"} ${path} -> ${res.status}`);
  }
  return res.json();
}

export async function listTranscripts(): Promise<TranscriptSummary[]> {
  return parseTranscripts(await request("/transcripts"));
}

export async function getTranscript(id: string): Promise<TranscriptDetail> {
  return parseTranscript(
    await request(`/transcripts/${encodeURIComponent(id)}`),
  );
}

export async function deleteTranscript(id: string): Promise<void> {
  await request(`/transcripts/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function getMe(): Promise<Me> {
  return parseMe(await request("/users/me"));
}
