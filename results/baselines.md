# Baseline detectors on the English Net splits

Generated 2026-10-19 18:21 by `python -m englishnet.baselines table`. Per-row scores: `results/baselines/<model>.jsonl`. Metrics are on each source's test split. acc, F1, FPR, TPR and catch@k%FPR are percentages; AUC is 0-1. catch@k%FPR = share of attacks caught at the score cutoff that flags k% of that source's benign rows. FPR is the only metric for benign-only sets (notinject) and TPR the only one for attack-only sets (gandalf).

Two thresholds: the model's native 0.5, and a threshold tuned on the dev split of the four training sources with `fit.tune_threshold` (maximizes mean per-source balanced accuracy). deepset is split into its official test (116 rows) and its official train (546 rows, `deepset-train546`).

## Models

| model | status | device | median latency per text (ms) | dev-tuned threshold | note |
|---|---|---|---|---|---|
| piguard | ran | mps | 21.9 | 0.13 | Its published training set (datasets/train.json, 20 public datasets) contains all 546 deepset-train546 rows and 7-20% of our safeguard, jackhhao and itw test rows verbatim (exact-match table below); its validation set used NotInject samples. |
| protectai | ran | mps | 27.2 | 0.05 | Model card lists jackhhao/jailbreak-classification among its training sets, so jackhhao numbers are likely in-distribution. Card says it does not target jailbreaks. |
| deepset | ran | mps | 21.3 | 0.95 | Fine-tuned on deepset/prompt-injections, so its deepset numbers are in-distribution (the 546 deepset-train546 rows are its literal training data). |
| promptguard2 | blocked: gated model, needs HF token + license acceptance |  |  |  | Meta has not published the training set. |
| tfidf | ran | cpu | 0.17 | 0.36 | Trained on our train split only (4 training sources); deepset, notinject and gandalf are unseen. |
| claude | deferred: Anthropic API refused the probe call with a billing/credit error |  |  |  | Zero-shot; returns a hard label, so AUC and catch@FPR are computed on a 0/1 score. |

## Threshold 0.5

| model | source | n | acc | f1 | auc | catch@1%fpr | catch@5%fpr | fpr | tpr |
|---|---|---|---|---|---|---|---|---|---|
| piguard | safeguard | 598 | 84.1 | 70.8 | 0.903 | 45.2 | 60.6 | 5.4 | 61.2 |
| piguard | jackhhao | 262 | 95.4 | 95.7 | 0.995 | 94.2 | 98.6 | 4.9 | 95.7 |
| piguard | itw | 478 | 84.9 | 84.5 | 0.93 | 28.4 | 77.1 | 19.6 | 90.4 |
| piguard | openpi | 499 | 83.2 | 81.7 | 0.93 | 14.8 | 63.6 | 8.8 | 75.2 |
| piguard | deepset | 116 | 82.8 | 80.0 | 0.96 | 81.7 | 91.7 | 0.0 | 66.7 |
| piguard | deepset-train546 | 546 | 96.7 | 95.4 | 0.996 | 96.1 | 99.0 | 0.0 | 91.1 |
| piguard | notinject | 339 | 88.5 |  |  |  |  | 11.5 |  |
| piguard | gandalf | 223 | 93.7 |  |  |  |  |  | 93.7 |
| piguard | adversarial | 60 | 71.7 | 74.6 | 0.874 | 25.0 | 60.0 | 10.0 | 62.5 |
| protectai | safeguard | 598 | 95.0 | 91.3 | 0.985 | 91.0 | 96.8 | 0.0 | 84.0 |
| protectai | jackhhao | 262 | 90.8 | 90.7 | 0.978 | 69.8 | 96.4 | 1.6 | 84.2 |
| protectai | itw | 478 | 81.4 | 77.8 | 0.892 | 30.3 | 60.1 | 10.4 | 71.6 |
| protectai | openpi | 499 | 61.9 | 41.7 | 0.652 | 4.8 | 30.8 | 3.2 | 27.2 |
| protectai | deepset | 116 | 67.2 | 53.7 | 0.871 | 53.3 | 71.7 | 0.0 | 36.7 |
| protectai | deepset-train546 | 546 | 78.0 | 59.2 | 0.877 | 41.9 | 69.5 | 1.2 | 42.9 |
| protectai | notinject | 339 | 56.6 |  |  |  |  | 43.4 |  |
| protectai | gandalf | 223 | 100.0 |  |  |  |  |  | 100.0 |
| protectai | adversarial | 60 | 76.7 | 81.1 | 0.857 | 20.0 | 32.5 | 20.0 | 75.0 |
| deepset | safeguard | 598 | 48.3 | 54.2 | 0.645 | 4.8 | 12.8 | 74.1 | 97.3 |
| deepset | jackhhao | 262 | 55.7 | 70.6 | 0.789 | 0.0 | 4.3 | 94.3 | 100.0 |
| deepset | itw | 478 | 46.4 | 62.9 | 0.54 | 0.0 | 0.9 | 98.1 | 99.5 |
| deepset | openpi | 499 | 54.7 | 68.9 | 0.86 | 0.4 | 8.0 | 90.8 | 100.0 |
| deepset | deepset | 116 | 99.1 | 99.2 | 0.997 | 98.3 | 98.3 | 0.0 | 98.3 |
| deepset | deepset-train546 | 546 | 99.8 | 99.8 | 1.0 | 100.0 | 100.0 | 0.3 | 100.0 |
| deepset | notinject | 339 | 28.6 |  |  |  |  | 71.4 |  |
| deepset | gandalf | 223 | 90.1 |  |  |  |  |  | 90.1 |
| deepset | adversarial | 60 | 75.0 | 83.9 | 0.782 | 15.0 | 27.5 | 70.0 | 97.5 |
| tfidf | safeguard | 598 | 97.3 | 95.6 | 0.995 | 95.7 | 97.3 | 0.5 | 92.6 |
| tfidf | jackhhao | 262 | 95.0 | 95.1 | 0.994 | 94.2 | 97.1 | 0.0 | 90.6 |
| tfidf | itw | 478 | 83.7 | 81.7 | 0.901 | 42.2 | 71.6 | 13.1 | 79.8 |
| tfidf | openpi | 499 | 99.8 | 99.8 | 1.0 | 100.0 | 100.0 | 0.4 | 100.0 |
| tfidf | deepset | 116 | 53.4 | 18.2 | 0.692 | 28.3 | 38.3 | 0.0 | 10.0 |
| tfidf | deepset-train546 | 546 | 65.4 | 14.5 | 0.74 | 15.3 | 44.8 | 0.6 | 7.9 |
| tfidf | notinject | 339 | 96.5 |  |  |  |  | 3.5 |  |
| tfidf | gandalf | 223 | 44.4 |  |  |  |  |  | 44.4 |
| tfidf | adversarial | 60 | 40.0 | 25.0 | 0.637 | 0.0 | 15.0 | 10.0 | 15.0 |

## Dev-tuned threshold

| model | source | n | acc | f1 | auc | catch@1%fpr | catch@5%fpr | fpr | tpr |
|---|---|---|---|---|---|---|---|---|---|
| piguard | safeguard | 598 | 84.8 | 74.4 | 0.903 | 45.2 | 60.6 | 8.5 | 70.2 |
| piguard | jackhhao | 262 | 96.6 | 96.8 | 0.995 | 94.2 | 98.6 | 6.5 | 99.3 |
| piguard | itw | 478 | 79.5 | 80.9 | 0.93 | 28.4 | 77.1 | 33.8 | 95.4 |
| piguard | openpi | 499 | 83.6 | 83.4 | 0.93 | 14.8 | 63.6 | 15.3 | 82.4 |
| piguard | deepset | 116 | 87.1 | 85.7 | 0.96 | 81.7 | 91.7 | 0.0 | 75.0 |
| piguard | deepset-train546 | 546 | 97.8 | 97.0 | 0.996 | 96.1 | 99.0 | 0.9 | 95.6 |
| piguard | notinject | 339 | 84.7 |  |  |  |  | 15.3 |  |
| piguard | gandalf | 223 | 96.9 |  |  |  |  |  | 96.9 |
| piguard | adversarial | 60 | 78.3 | 82.2 | 0.874 | 25.0 | 60.0 | 15.0 | 75.0 |
| protectai | safeguard | 598 | 95.7 | 92.6 | 0.985 | 91.0 | 96.8 | 0.0 | 86.2 |
| protectai | jackhhao | 262 | 91.6 | 91.5 | 0.978 | 69.8 | 96.4 | 1.6 | 85.6 |
| protectai | itw | 478 | 80.3 | 77.5 | 0.892 | 30.3 | 60.1 | 14.6 | 74.3 |
| protectai | openpi | 499 | 62.3 | 43.7 | 0.652 | 4.8 | 30.8 | 4.4 | 29.2 |
| protectai | deepset | 116 | 69.0 | 57.1 | 0.871 | 53.3 | 71.7 | 0.0 | 40.0 |
| protectai | deepset-train546 | 546 | 78.9 | 61.5 | 0.877 | 41.9 | 69.5 | 1.2 | 45.3 |
| protectai | notinject | 339 | 54.6 |  |  |  |  | 45.4 |  |
| protectai | gandalf | 223 | 100.0 |  |  |  |  |  | 100.0 |
| protectai | adversarial | 60 | 78.3 | 83.1 | 0.857 | 20.0 | 32.5 | 25.0 | 80.0 |
| deepset | safeguard | 598 | 49.2 | 54.4 | 0.645 | 4.8 | 12.8 | 72.4 | 96.3 |
| deepset | jackhhao | 262 | 56.5 | 70.9 | 0.789 | 0.0 | 4.3 | 92.7 | 100.0 |
| deepset | itw | 478 | 47.3 | 63.3 | 0.54 | 0.0 | 0.9 | 96.5 | 99.5 |
| deepset | openpi | 499 | 56.9 | 69.9 | 0.86 | 0.4 | 8.0 | 86.3 | 100.0 |
| deepset | deepset | 116 | 97.4 | 97.4 | 0.997 | 98.3 | 98.3 | 0.0 | 95.0 |
| deepset | deepset-train546 | 546 | 99.8 | 99.8 | 1.0 | 100.0 | 100.0 | 0.0 | 99.5 |
| deepset | notinject | 339 | 32.7 |  |  |  |  | 67.3 |  |
| deepset | gandalf | 223 | 89.7 |  |  |  |  |  | 89.7 |
| deepset | adversarial | 60 | 75.0 | 83.9 | 0.782 | 15.0 | 27.5 | 70.0 | 97.5 |
| tfidf | safeguard | 598 | 97.7 | 96.2 | 0.995 | 95.7 | 97.3 | 1.0 | 94.7 |
| tfidf | jackhhao | 262 | 95.0 | 95.1 | 0.994 | 94.2 | 97.1 | 0.8 | 91.4 |
| tfidf | itw | 478 | 82.0 | 80.7 | 0.901 | 42.2 | 71.6 | 18.5 | 82.6 |
| tfidf | openpi | 499 | 99.8 | 99.8 | 1.0 | 100.0 | 100.0 | 0.4 | 100.0 |
| tfidf | deepset | 116 | 55.2 | 23.5 | 0.692 | 28.3 | 38.3 | 0.0 | 13.3 |
| tfidf | deepset-train546 | 546 | 66.8 | 21.0 | 0.74 | 15.3 | 44.8 | 0.6 | 11.8 |
| tfidf | notinject | 339 | 95.0 |  |  |  |  | 5.0 |  |
| tfidf | gandalf | 223 | 52.0 |  |  |  |  |  | 52.0 |
| tfidf | adversarial | 60 | 41.7 | 31.4 | 0.637 | 0.0 | 15.0 | 15.0 | 20.0 |

## Training-data overlap (PIGuard)

Rows of our test split whose normalized text appears verbatim in PIGuard's published train.json (case and whitespace folded).

| source | test rows | in PIGuard train | share |
|---|---|---|---|
| safeguard | 598 | 80 | 13.4% |
| jackhhao | 262 | 19 | 7.3% |
| itw | 478 | 87 | 18.2% |
| openpi | 499 | 0 | 0.0% |
| deepset | 116 | 2 | 1.7% |
| deepset-train546 | 546 | 546 | 100.0% |
| notinject | 339 | 0 | 0.0% |
| gandalf | 223 | 0 | 0.0% |
| train+dev (all training sources) | 4184 | 1969 | 47.1% |
