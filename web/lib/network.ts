import raw from "@/data/network.json";
import rawPatched from "@/data/network_patched.json";
import type { HistoryEntry, Network, Neuron } from "./types";

/* Fills defaults so a partial or older network.json never crashes the page or the forward pass. */

const num = (v: unknown, d: number) => (typeof v === "number" && Number.isFinite(v) ? v : d);
const str = (v: unknown, d = "") => (typeof v === "string" ? v : d);
const strs = (v: unknown) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

function neuron(n: Record<string, unknown>): Neuron {
  const parent = (n.parent ?? {}) as Record<string, unknown>;
  const act = n.activation as Record<string, unknown> | null | undefined;
  const crit = n.criteria as Neuron["criteria"] | undefined;
  return {
    id: str(n.id),
    layer: n.layer === 2 ? 2 : 1,
    type: "noul",
    question: str(n.question),
    criteria: crit && typeof crit === "object" ? crit : null,
    inputs: strs(n.inputs),
    status: (["active", "pruned", "rejected", "candidate"].includes(n.status as string) ? n.status : "candidate") as Neuron["status"],
    born_round: num(n.born_round, 0),
    born_at: str(n.born_at),
    origin: (["hand-written", "evolved", "adversarial", "patch"].includes(n.origin as string) ? n.origin : "hand-written") as Neuron["origin"],
    proposer: str(n.proposer),
    parent: {
      kind: (["error", "attack", "none"].includes(parent.kind as string) ? parent.kind : "none") as Neuron["parent"]["kind"],
      example_ids: strs(parent.example_ids),
      excerpt: str(parent.excerpt),
    },
    input: n.input === "logit" ? "logit" : "prob",
    weight: num(n.weight, 0),
    activation: act && typeof act === "object" ? { attack: num(act.attack, 0), benign: num(act.benign, 0) } : null,
    consistency_kappa: typeof n.consistency_kappa === "number" ? n.consistency_kappa : null,
    paraphrase: typeof n.paraphrase === "string" ? n.paraphrase : null,
    note: typeof n.note === "string" ? n.note : null,
  };
}

function history(h: Record<string, unknown>): HistoryEntry {
  return {
    round: num(h.round, 0),
    kind: str(h.kind, "evolution"),
    at: str(h.at),
    proposer: str(h.proposer),
    added: strs(h.added),
    dropped: strs(h.dropped),
    rejected: strs(h.rejected),
    metrics: h.metrics && typeof h.metrics === "object" ? (h.metrics as Record<string, unknown>) : {},
    summary: str(h.summary),
  };
}

export function loadNetwork(which: "v6" | "patched" = "v6"): Network {
  const r = (which === "patched" ? rawPatched : raw) as unknown as Record<string, unknown>;
  const ro = (r.readout ?? {}) as Record<string, unknown>;
  return {
    name: str(r.name, "English Net"),
    task: str(r.task),
    version: typeof r.version === "number" || typeof r.version === "string" ? r.version : 0,
    jev_model: str(r.jev_model, "jev-1.13.0"),
    readout: {
      type: "logistic",
      intercept: num(ro.intercept, 0),
      threshold: num(ro.threshold, 0.5),
      C: typeof ro.C === "number" ? ro.C : null,
    },
    neurons: (Array.isArray(r.neurons) ? r.neurons : [])
      .map((n) => neuron(n as Record<string, unknown>))
      .filter((n) => n.id && n.question),
    history: (Array.isArray(r.history) ? r.history : []).map((h) => history(h as Record<string, unknown>)),
    metrics: r.metrics && typeof r.metrics === "object" ? (r.metrics as Record<string, unknown>) : {},
  };
}

export const active = (net: Network, layer?: 1 | 2) =>
  net.neurons.filter((n) => n.status === "active" && (layer === undefined || n.layer === layer));
