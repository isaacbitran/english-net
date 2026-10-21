import replay from "@/data/replay.json";
import { active } from "@/lib/network";
import { ask, feature, isLive } from "@/lib/forward";
import { err, failure, net, rateLimited } from "@/lib/guard";
import type { Neuron } from "@/lib/types";

/* "Patch in one sentence": add one English question as a neuron and rescore the patch-demo rows.
   The weight comes from the same rule as englishnet/patch.py: a yes at p = p_confident lifts the median benign
   train+dev text over the threshold. Every other weight stays as it is. The shipped sentence is answered from the
   bundled cache (real Jev answers); any other sentence needs TYPESAFE_API_KEY and costs one short call per row. */

type Demo = { id: string; text: string; label: number; source: string };
const R = replay as unknown as {
  patch_demo: Demo[];
  answers: Record<string, Record<string, number>>;
  summary: { patch: { id: string; question: string }; rule: { p_confident: number; median_benign_logit: number; threshold: number } };
};

const logit = (p: number) => Math.log(p / (1 - p));
const sig = (z: number) => 1 / (1 + Math.exp(-z));

export async function POST(req: Request) {
  if (rateLimited(req)) return err(429, "Too many requests: 30 per minute.");
  let body: { question?: unknown };
  try {
    body = await req.json();
  } catch {
    return err(400, "Body must be JSON: {\"question\": \"...\"}.");
  }
  const question = typeof body.question === "string" ? body.question.trim().replace(/\s+/g, " ") : "";
  if (question.length < 12 || question.length > 400) return err(400, "Write one yes/no question, 12 to 400 characters.");
  const shipped = question === R.summary.patch.question;
  if (!shipped && !isLive())
    return err(503, "Live scoring is off on this deployment (no TypeSafe API key), so only the shipped sentence can be added. Run the demo locally with a key to try your own.");

  const { p_confident, median_benign_logit, threshold } = R.summary.rule;
  const weight = (logit(threshold) - median_benign_logit) / p_confident;
  const neuron = { id: shipped ? R.summary.patch.id : "user_patch", question, layer: 1, input: "prob" } as unknown as Neuron;
  const l1 = active(net, 1);

  try {
    const rows = await Promise.all(
      R.patch_demo.map(async (d) => {
        const base = R.answers[d.text];
        const pp = shipped ? base[neuron.id] : (await ask(net, { text: d.text }, [neuron])).answers[neuron.id];
        let z = net.readout.intercept;
        for (const n of l1) z += n.weight * feature(base[n.id], n.input);
        return { id: d.id, p_before: sig(z), p_patch: pp, p_after: sig(z + weight * pp) };
      }),
    );
    return Response.json({ weight, threshold, shipped, rows });
  } catch (e) {
    return failure(e);
  }
}
