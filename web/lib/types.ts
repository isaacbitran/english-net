export type Origin = "hand-written" | "evolved" | "adversarial" | "patch";
export type Status = "active" | "pruned" | "rejected" | "candidate";

export interface Neuron {
  id: string;
  layer: 1 | 2;
  type: "noul";
  question: string;
  criteria: { true?: string; false?: string } | null;
  inputs: string[];
  status: Status;
  born_round: number;
  born_at: string;
  origin: Origin;
  proposer: string;
  parent: { kind: "error" | "attack" | "none"; example_ids: string[]; excerpt: string };
  /** What the readout reads: the probability, or its log-odds ("logit"). */
  input: "prob" | "logit";
  weight: number;
  activation: { attack: number; benign: number } | null;
  consistency_kappa: number | null;
  paraphrase: string | null;
  note: string | null;
}

export interface HistoryEntry {
  round: number;
  kind: "evolution" | "adversarial" | "seed" | string;
  at: string;
  proposer: string;
  added: string[];
  dropped: string[];
  rejected: string[];
  metrics: Record<string, unknown>;
  summary: string;
}

export interface Network {
  name: string;
  task: string;
  version: number | string;
  jev_model: string;
  readout: { type: "logistic"; intercept: number; threshold: number; C: number | null };
  neurons: Neuron[];
  history: HistoryEntry[];
  metrics: Record<string, unknown>;
}

export interface Contribution {
  id: string;
  layer: number;
  question: string;
  p: number;
  input: "prob" | "logit";
  /** The value the readout multiplies by the weight: p, or log(p / (1 - p)). */
  x: number;
  weight: number;
  contribution: number;
}

export interface ScoreResult {
  p_attack: number;
  label: "attack" | "benign";
  threshold: number;
  logit: number;
  intercept: number;
  ms: number;
  tokens: number;
  usd: number;
  model: string;
  mock: boolean;
  /** True when every answer came from the bundled cache of real Jev answers (web/data/replay.json). */
  replay?: boolean;
  contributions: Contribution[];
}
