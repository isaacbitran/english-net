import "server-only";
import { active } from "./network";
import { mockAnswer } from "./mock";
import replay from "@/data/replay.json";
import type { Contribution, Network, Neuron, ScoreResult } from "./types";

/* Forward pass, matching englishnet/forward.py: layer 1 = one Jev call over {"text": text};
   layer 2 = one call per group of layer-2 neurons sharing inputs, over {"findings": {question: yes/no/unclear}};
   readout = sigmoid(intercept + sum(weight * x)), x = p or log(p / (1 - p)) for neurons with input "logit".
   The text must already be normalized.

   Modes. Live: TYPESAFE_API_KEY is set (and MOCK is not "1"); texts are sent to Jev. Cached (the default when no key
   is set, e.g. a public deploy): only texts with saved Jev answers in web/data/replay.json can be scored, and any other
   text is refused with OfflineError, so the deploy never calls Jev. Stand-in: MOCK=1 explicitly opts into
   keyword-based fake answers for local UI work; they are labelled as not Jev. */

const ENDPOINT = "https://api.typesafe.ai/v1/systemone";
const USD_PER_MTOK = 0.042;
const MAX_Q_PER_CALL = 64;

/** True only when a key is set and MOCK is not forced: the only mode that sends anything to Jev. */
export const isLive = () => Boolean(process.env.TYPESAFE_API_KEY) && process.env.MOCK !== "1";
/** Explicit opt-in to keyword stand-in answers (local development only). */
export const isStandIn = () => process.env.MOCK === "1";
/** Not live: cached answers only (or stand-in answers with MOCK=1). */
export const isMock = () => !isLive();

/** Raised when a text needs a live Jev call and no key is configured. */
export class OfflineError extends Error {
  constructor() {
    super("Live scoring is off on this deployment (no TypeSafe API key). Pick one of the preset texts, or run the demo locally with a key.");
    this.name = "OfflineError";
  }
}

const REPLAY = (replay as { answers: Record<string, Record<string, number>> }).answers;

/** Real cached Jev answers for this text, if every neuron is covered. */
export function replayed(text: string, neurons: Neuron[]): Record<string, number> | null {
  const a = REPLAY[text];
  if (!a || !neurons.every((n) => n.id in a)) return null;
  return Object.fromEntries(neurons.map((n) => [n.id, a[n.id]]));
}

export const feature = (p: number, input: "prob" | "logit") => {
  if (input !== "logit") return p;
  const q = Math.min(Math.max(p, 1e-4), 1 - 1e-4);
  return Math.log(q / (1 - q));
};

export const word = (p: number) => (p >= 0.6 ? "yes" : p <= 0.4 ? "no" : "unclear");

const round = (x: number, d = 4) => Math.round(x * 10 ** d) / 10 ** d;

function qspec(n: Neuron) {
  const spec: Record<string, unknown> = { type: "noul", instructions: n.question };
  if (n.criteria && Object.keys(n.criteria).length) spec.criteria = n.criteria;
  return spec;
}

interface Asked {
  answers: Record<string, number>;
  tokens: number;
  model?: string;
}

async function callJev(model: string, state: unknown, questions: Record<string, unknown>) {
  if (!isLive()) throw new OfflineError();
  for (let attempt = 0; ; attempt++) {
    const res = await fetch(ENDPOINT, {
      method: "POST",
      headers: { Authorization: `Bearer ${process.env.TYPESAFE_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({ model, state, questions }),
      signal: AbortSignal.timeout(30_000),
      cache: "no-store",
    });
    if (res.ok) return (await res.json()) as {
      model?: string;
      answers?: Record<string, { noul?: number }>;
      usage?: { input_tokens?: number };
    };
    if ((res.status === 429 || res.status >= 500) && attempt < 2) {
      await new Promise((r) => setTimeout(r, 800 * (attempt + 1)));
      continue;
    }
    // Never include headers or the key in the error; the body is TypeSafe's error description.
    const body = (await res.text()).slice(0, 300);
    throw new Error(`Jev returned HTTP ${res.status}: ${body}`);
  }
}

/** Ask every neuron about one state. Identical question specs are asked once, 64 questions per call. */
export async function ask(net: Network, state: Record<string, unknown>, neurons: Neuron[]): Promise<Asked & { replay?: boolean }> {
  if (typeof state.text === "string") {
    const hit = replayed(state.text, neurons);
    if (hit && (isMock() || process.env.REPLAY_FIRST !== "0")) return { answers: hit, tokens: 0, model: net.jev_model, replay: true };
  }
  if (!isLive()) {
    if (!isStandIn()) throw new OfflineError();
    const answers: Record<string, number> = {};
    for (const n of neurons) answers[n.id] = mockAnswer(n, state);
    return { answers, tokens: 0, model: net.jev_model };
  }
  const byKey = new Map<string, Neuron[]>();
  for (const n of neurons) {
    const k = JSON.stringify(qspec(n));
    byKey.set(k, [...(byKey.get(k) ?? []), n]);
  }
  const keys = [...byKey.keys()];
  const out: Asked = { answers: {}, tokens: 0 };
  for (let i = 0; i < keys.length; i += MAX_Q_PER_CALL) {
    const chunk = keys.slice(i, i + MAX_Q_PER_CALL);
    const qs: Record<string, unknown> = {};
    chunk.forEach((k, j) => (qs[`q${j}`] = JSON.parse(k)));
    const r = await callJev(net.jev_model, state, qs);
    out.tokens += Number(r.usage?.input_tokens ?? 0) || 0;
    out.model = r.model ?? out.model;
    chunk.forEach((k, j) => {
      const p = r.answers?.[`q${j}`]?.noul;
      if (typeof p !== "number") throw new Error(`Jev answer q${j} has no noul probability`);
      for (const n of byKey.get(k)!) out.answers[n.id] = p;
    });
  }
  return out;
}

export async function score(text: string, net: Network): Promise<ScoreResult> {
  const t0 = performance.now();
  const l1 = active(net, 1);
  const a1 = await ask(net, { text }, l1);
  const answers = { ...a1.answers };
  let tokens = a1.tokens;
  const fromReplay = Boolean(a1.replay);
  let model = a1.model;

  const l2 = active(net, 2);
  if (l2.length) {
    const byId = new Map(net.neurons.map((n) => [n.id, n]));
    const groups = new Map<string, Neuron[]>();
    for (const n of l2) {
      const k = JSON.stringify(n.inputs);
      groups.set(k, [...(groups.get(k) ?? []), n]);
    }
    const results = await Promise.all(
      [...groups.values()].map((ns) => {
        const findings: Record<string, string> = {};
        for (const i of ns[0].inputs) {
          const src = byId.get(i);
          if (src && i in a1.answers) findings[src.question] = word(a1.answers[i]);
        }
        return ask(net, { findings }, ns);
      }),
    );
    for (const r of results) {
      Object.assign(answers, r.answers);
      tokens += r.tokens;
      model = r.model ?? model;
    }
  }
  const ms = performance.now() - t0;

  let z = net.readout.intercept;
  const contributions: Contribution[] = active(net).map((n) => {
    const p = answers[n.id] ?? 0;
    const x = feature(p, n.input);
    const c = n.weight * x;
    z += c;
    return { id: n.id, layer: n.layer, question: n.question, p, input: n.input, x: round(x), weight: n.weight, contribution: round(c) };
  });
  contributions.sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));
  const p = 1 / (1 + Math.exp(-z));
  const thr = net.readout.threshold;
  return {
    p_attack: round(p),
    label: p >= thr ? "attack" : "benign",
    threshold: thr,
    logit: round(z),
    intercept: net.readout.intercept,
    ms: round(ms, 1),
    tokens,
    usd: (tokens * USD_PER_MTOK) / 1e6,
    model: model ?? net.jev_model,
    mock: !isLive() && !fromReplay,
    replay: fromReplay,
    contributions,
  };
}
