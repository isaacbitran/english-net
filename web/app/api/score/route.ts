import { err, failure, parseText, rateLimited, scoreCached } from "@/lib/guard";
import { isLive, isStandIn } from "@/lib/forward";
import { connection } from "next/server";

export async function GET() {
  await connection();
  return Response.json({ live: isLive(), mock: !isLive(), standIn: !isLive() && isStandIn() });
}

export async function POST(req: Request) {
  if (rateLimited(req)) return err(429, "Too many requests: 30 per minute.");
  const parsed = await parseText(req);
  if (!parsed.ok) return err(parsed.status, parsed.error);
  try {
    return Response.json(await scoreCached(parsed.text, parsed.body.patched === true));
  } catch (e) {
    return failure(e);
  }
}
