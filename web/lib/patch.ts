import replay from "@/data/replay.json";

/* Patch demo rows and the patch / fine-tune summary, from web/data/replay.json (written by
   `python -m englishnet.export_web` from results/patch.json and results/finetune.json). Kept out of the client
   component file so server components can read the numbers. */

export type Demo = { id: string; text: string; label: number; source: string; p_before: number };
export type Flips = {
  n: number; n_benign: number; catch_before: number | null; catch_after: number | null; new_false_alarms: number; false_alarms_removed: number;
  new_catches: number; new_misses: number; false_alarm_before: number | null; false_alarm_after: number | null;
};
export type Summary = {
  patch: { id: string; question: string; weight: number };
  rule: { p_confident: number; median_benign_logit: number; threshold: number };
  kappa: number;
  family: Flips;
  everything_else: Flips;
  finetune: { train_seconds: number; device: string; epochs: number; train_examples: { attack: number; benign: number }; family: Flips; everything_else: Flips };
};
export const R = replay as unknown as { patch_demo: Demo[]; summary: Summary };
export const S = R.summary;
