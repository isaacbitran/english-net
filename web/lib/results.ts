/* Numbers for Figure 2, copied from results/tables.md ("Paired bootstrap AUC differences", 2,000 resamples,
   95% interval; "Fresh confirmation set"; "Sources never used in training"). Regenerate with
   `python -m englishnet.eval --final` and update these if they change. AUC is shown as "ranking score". */

export type Pair = { label: string; sub: string; a: number; b: number; d: number; lo: number; hi: number };

export const PAIRS: Pair[] = [
  { label: "Test splits of the 4 training sources", sub: "1,837 texts; questions were learned here", a: 0.9707, b: 0.9465, d: 0.0242, lo: 0.0182, hi: 0.0301 },
  { label: "5 sources never used in training", sub: "1,284 texts", a: 0.9811, b: 0.9831, d: -0.002, lo: -0.0048, hi: 0.0007 },
  { label: "Confirmation set: 5 new sources", sub: "2,193 texts, collected after the model was frozen", a: 0.9791, b: 0.9827, d: -0.0037, lo: -0.0062, hi: -0.0012 },
  { label: "Confirmation set, with the added sentence", sub: "same 2,193 texts", a: 0.9832, b: 0.9827, d: 0.0004, lo: -0.0022, hi: 0.0031 },
];

/** Accuracy-at-threshold rows from results/tables.md; percentages. */
export const BENCH = [
  { m: "English Net", train: 91.6, deepset: "81.0 / 0.968", notinject: 2.4, gandalf: 89.2, held: "92.5 / 5.0", multi: 77.7, me: true },
  { m: "Single Jev question", train: 87.2, deepset: "79.3 / 0.978", notinject: 5.0, gandalf: 96.9, held: "95.0 / 10.0", multi: 87.5 },
  { m: "PIGuard", train: 86.9, deepset: "82.8 / 0.960", notinject: 11.5, gandalf: 93.7, held: "62.5 / 10.0", multi: 72.4 },
  { m: "ProtectAI DeBERTa v2", train: 82.3, deepset: "67.2 / 0.871", notinject: 43.4, gandalf: 100.0, held: "75.0 / 20.0", multi: 97.9 },
];
