import { appendFile, mkdir, readFile } from "node:fs/promises";
import path from "node:path";
import { isLive, isMock } from "@/lib/forward";
import { err, failure, net, parseText, rateLimited, scoreCached, textKey } from "@/lib/guard";

/* "Try to break it": scores the text. With {"submit": true}, a text the network let through (p_attack below
   the threshold) that the user says is an attack is appended to data/submissions.jsonl, the queue the next
   Python adversarial round reads. Only the text, the score, a timestamp and the network version are stored. */

// Mock-mode scores are fake, so mock submissions go to a separate file the Python side never reads.
const QUEUE = path.join(process.cwd(), "data", isMock() ? "submissions.mock.jsonl" : "submissions.jsonl");

async function queued(): Promise<string[]> {
  try {
    return (await readFile(QUEUE, "utf8")).split("\n").filter(Boolean);
  } catch {
    return [];
  }
}

export async function POST(req: Request) {
  if (rateLimited(req)) return err(429, "Too many requests: 30 per minute.");
  const parsed = await parseText(req);
  if (!parsed.ok) return err(parsed.status, parsed.error);
  let result;
  try {
    result = await scoreCached(parsed.text);
  } catch (e) {
    return failure(e);
  }
  if (parsed.body.submit !== true) return Response.json({ result });
  if (!isLive()) return err(503, "The attack queue only accepts texts scored by a live Jev call; it is off on this deployment.");

  if (result.p_attack >= result.threshold) return err(409, "The network already flags this text as an attack.");
  const id = `web-${textKey(parsed.text).slice(0, 16)}`;
  const lines = await queued();
  if (lines.some((l) => l.includes(`"id":"${id}"`))) return Response.json({ result, queued: true, duplicate: true, queue: lines.length });
  const rec = { id, text: parsed.text, p_attack: result.p_attack, submitted_at: new Date().toISOString(), model_version: net.version };
  try {
    await mkdir(path.dirname(QUEUE), { recursive: true });
    await appendFile(QUEUE, JSON.stringify(rec) + "\n", "utf8");
  } catch {
    // Serverless hosts have a read-only file system; the queue is a local-development feature.
    return err(503, "The attack queue is not writable on this deployment.");
  }
  return Response.json({ result, queued: true, queue: lines.length + 1 });
}
