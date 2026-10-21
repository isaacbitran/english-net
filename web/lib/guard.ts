import "server-only";
import { createHash } from "node:crypto";
import { loadNetwork } from "./network";
import { OfflineError, isMock, score } from "./forward";
import { MAX_CHARS, charCount, normalizeFull } from "./normalize";
import type { ScoreResult } from "./types";

/* Shared request handling for /api/score and /api/break: rate limit, input validation, and a small
   in-memory result cache so the same text is not paid for twice (e.g. score, then submit to the queue). */

const WINDOW_MS = 60_000;
const LIMIT = 30;
const hits = new Map<string, number[]>();

export function rateLimited(req: Request): boolean {
  const ip = (req.headers.get("x-forwarded-for") ?? "").split(",")[0].trim() || req.headers.get("x-real-ip") || "local";
  const now = Date.now();
  const recent = (hits.get(ip) ?? []).filter((t) => now - t < WINDOW_MS);
  if (recent.length >= LIMIT) {
    hits.set(ip, recent);
    return true;
  }
  recent.push(now);
  hits.set(ip, recent);
  if (hits.size > 5000) hits.clear();
  return false;
}

export const net = loadNetwork();
export const netPatched = loadNetwork("patched");

export type Parsed = { ok: true; text: string; body: Record<string, unknown> } | { ok: false; status: number; error: string };

export async function parseText(req: Request): Promise<Parsed> {
  const raw = await req.text();
  if (raw.length > 64_000) return { ok: false, status: 413, error: `Text is over ${MAX_CHARS} characters.` };
  let body: Record<string, unknown>;
  try {
    body = JSON.parse(raw);
  } catch {
    return { ok: false, status: 400, error: "Body must be JSON: {\"text\": \"...\"}." };
  }
  if (!body || typeof body.text !== "string") return { ok: false, status: 400, error: "Missing \"text\" string." };
  const text = normalizeFull(body.text);
  if (!text) return { ok: false, status: 400, error: "Text is empty." };
  if (charCount(text) > MAX_CHARS) return { ok: false, status: 413, error: `Text is over ${MAX_CHARS} characters.` };
  return { ok: true, text, body };
}

const cache = new Map<string, ScoreResult>();
export const textKey = (text: string, patched = false) =>
  createHash("sha256").update(`${patched ? netPatched.version : net.version}|${net.jev_model}|${isMock()}|${text}`).digest("hex");

export function cached(text: string) {
  return cache.get(textKey(text));
}

export async function scoreCached(text: string, patched = false): Promise<ScoreResult & { cached?: boolean }> {
  const k = textKey(text, patched);
  const hit = cache.get(k);
  if (hit) return { ...hit, cached: true };
  const r = await score(text, patched ? netPatched : net);
  if (cache.size > 500) cache.delete(cache.keys().next().value!);
  cache.set(k, r);
  return r;
}

export const err = (status: number, error: string) => Response.json({ error }, { status });

export function failure(e: unknown) {
  if (e instanceof OfflineError) return err(503, e.message);
  const msg = e instanceof Error ? e.message : "Scoring failed.";
  console.error("[score]", msg);
  return err(502, msg.startsWith("Jev") ? msg : "Scoring failed.");
}
