"""Final evaluation. The ONLY module (besides the fixed-model baselines) that reads the test split.

  python -m englishnet.eval --final        # all tables -> results/final.json and results/tables.md
  python -m englishnet.eval --final --latency 100   # also measure uncached latency on 100 test texts

Protocol (also in README):
  - Neurons, weights, C and the threshold were chosen on train and dev only (englishnet.train). Nothing here feeds back.
  - Test rows: the test split of the four training sources, three sources never used in training (deepset, notinject,
    gandalf), and the round-9 adversarial set written against the final network and never trained on.
  - Every network version is scored with the weights and threshold stored in its snapshot (model/history/vXX.json).
  - Leave-one-source-out: the final neuron set is refit without source X (train+dev of the rest), threshold from
    out-of-fold predictions, then scored on X's test split. Caveat: the questions were proposed from errors that
    included X's train split; the never-trained sources are the clean transfer test.
"""
import argparse
import json
import math
import random
import re
import statistics
import time

import numpy as np

from . import jev
from . import neurons as N
from .config import JEV_MODEL, JEV_USD_PER_MTOK, MODEL_DIR, RESULTS
from .data import HELDOUT_SOURCES, TRAIN_SOURCES, load, normalize
from .fit import feature, fit, matrix, metrics, oof_predict, tune_threshold

WORKERS = 12
TEST_GROUPS = TRAIN_SOURCES + ["deepset", "deepset_extra", "notinject", "gandalf", "adversarial"]
GROUP_LABEL = {"deepset": "deepset (official test, 116)", "deepset_extra": "deepset (official train rows, 546)",
               "notinject": "NotInject (benign only, 339)", "gandalf": "Gandalf (attacks only, 223)",
               "adversarial": "Held-out adaptive attacks (round 9, 60)"}


def group_of(r):
    if r["source"] == "deepset" and r.get("subset") == "official_train":
        return "deepset_extra"
    return r["source"]


def answers(rows, neurons, purpose):
    return jev.ask_many([r["text"] for r in rows], neurons, purpose=purpose, workers=WORKERS, progress=False)


def predict_snapshot(net, A):
    act = N.active(net, 1)
    z = np.array([net["readout"]["intercept"] + sum(n["weight"] * feature(a[n["id"]], n.get("input", "prob")) for n in act)
                  for a in A])
    return 1 / (1 + np.exp(-z))


def by_group(rows, p, thr):
    out = {}
    for g in TEST_GROUPS:
        idx = [i for i, r in enumerate(rows) if group_of(r) == g]
        if idx:
            out[g] = metrics([rows[i]["label"] for i in idx], [p[i] for i in idx], thr)
    tr = [out[s] for s in TRAIN_SOURCES if s in out]
    out["macro_train_sources"] = {"acc": round(np.mean([m["acc"] for m in tr]), 1),
                                  "auc": round(np.mean([m["auc"] for m in tr]), 3)}
    return out


PERTURB_WORDS = ["ignore", "instructions", "previous", "prompt", "password", "system", "rules", "secret", "forget", "reveal"]


def perturb(t, kind, rng):
    if kind == "greeting":
        return f"Hi there! Hope you're well. {t} Thanks so much!"
    if kind == "uppercase":
        return t.upper()
    if kind == "tokenbreak":  # HiddenLayer-style: prepend a letter to trigger words
        return re.sub(r"\b(" + "|".join(PERTURB_WORDS) + r")", lambda m: "f" + m.group(1), t, flags=re.I)
    if kind == "char_noise":
        ws = t.split(" ")
        for i, w in enumerate(ws):
            if len(w) > 3 and rng.random() < 0.15:
                k = rng.randrange(1, len(w)); ws[i] = w[:k] + rng.choice("xqzj") + w[k:]
        return " ".join(ws)
    if kind == "zero_width":  # removed by normalize(); checks that the normalization step works
        return re.sub(r"\b(" + "|".join(PERTURB_WORDS) + r")\b", lambda m: "​".join(m.group(1)), t, flags=re.I)
    raise ValueError(kind)


def latency(net, rows, n):
    """Uncached calls through the SDK with the final question set, to measure real latency and tokens."""
    from typesafe_sdk import Noul, TypeSafeClient
    client = TypeSafeClient(model=JEV_MODEL)
    act = N.active(net, 1)
    sample = random.Random(1).sample(rows, n)
    ms, tok = [], []
    for r in sample:
        qs = {f"q{i}": Noul(instructions=a["question"]) for i, a in enumerate(act)}
        t0 = time.perf_counter()
        res = client.system_one(state={"text": r["text"]}, questions=qs)
        ms.append((time.perf_counter() - t0) * 1000)
        t = int(res.usage.input_tokens or 0); tok.append(t)
        jev._charge({"t": round(time.time(), 2), "purpose": "final_latency", "model": res.model, "n_q": len(act),
                     "tokens": t, "ms": round(ms[-1], 1), "usd": t * JEV_USD_PER_MTOK / 1e6})
    ms.sort()
    return {"n": n, "n_questions": len(act), "median_ms": round(statistics.median(ms)), "p90_ms": round(ms[int(0.9 * n)]),
            "median_tokens": statistics.median(tok), "usd_per_input_median": round(statistics.median(tok) * JEV_USD_PER_MTOK / 1e6, 8),
            "usd_per_million_inputs": round(statistics.median(tok) * JEV_USD_PER_MTOK, 2),
            "where": "laptop in Providence, RI, sequential calls, TypeSafe API"}


def final(lat_n=0):
    net = N.load()
    tr, dv = load("train"), load("dev")
    te = load("test", allow_test=True)  # the only place the test split is opened
    print(f"test rows: {len(te)}")
    snaps = sorted(MODEL_DIR.glob("history/v*.json"))
    nets = {s.stem: json.loads(s.read_text()) for s in snaps}
    nets["final"] = net
    need = {}
    for v in nets.values():
        for n in N.active(v, 1):
            need[n["id"]] = n
    need[N.BASELINE_QUESTION["id"]] = {**N.BASELINE_QUESTION, "layer": 1}
    need = list(need.values())
    At = answers(te, need, "final_eval_test")
    Adv = answers(dv, need, "final_eval_dev")
    Atr = answers(tr, need, "final_eval_train")
    R = {"jev_model": JEV_MODEL, "network_version": net["version"], "n_test": len(te), "models": {}}

    # single question: threshold 0.5 and threshold tuned on dev
    sq = N.BASELINE_QUESTION["id"]
    p_sq = np.array([a[sq] for a in At])
    thr_sq = tune_threshold(dv, [a[sq] for a in Adv])
    R["models"]["Single Jev question (t=0.5)"] = by_group(te, p_sq, 0.5)
    R["models"][f"Single Jev question (dev-tuned t={thr_sq})"] = by_group(te, p_sq, thr_sq)

    # every network version with its stored readout
    traj = {}
    for k, v in nets.items():
        p = predict_snapshot(v, At)
        res = by_group(te, p, v["readout"]["threshold"])
        traj[k] = {"version": v["version"], "n_active": len(N.active(v)), "threshold": v["readout"]["threshold"], "test": res}
    R["trajectory"] = traj
    R["models"][f"English Net v0 (30 hand-written)"] = traj["v00"]["test"]
    if "v05" in traj and net["version"] != 5:
        R["models"]["English Net v5 (6 evolved/hand-written neurons, no broad question)"] = traj["v05"]["test"]
    R["models"][f"English Net final (v{net['version']}, {len(N.active(net))} neurons)"] = traj["final"]["test"]

    # baselines from englishnet.baselines (per-row score files)
    try:
        from .baselines import load_scores
        MODELS = ["piguard", "protectai", "deepset", "tfidf", "promptguard2", "claude"]
        for m in MODELS:
            sc = load_scores(m)
            if not sc or not all(r["id"] in sc for r in te):
                R.setdefault("baselines_missing", []).append(m); continue
            p = np.array([sc[r["id"]] for r in te])
            R["models"][f"{m} (t=0.5)"] = by_group(te, p, 0.5)
            dvp = [sc.get(r["id"]) for r in dv]
            if all(x is not None for x in dvp):
                t = tune_threshold(dv, dvp)
                R["models"][f"{m} (dev-tuned t={t})"] = by_group(te, p, t)
    except Exception as e:
        R["baselines_error"] = f"{type(e).__name__}: {e}"

    # leave-one-source-out with the final neuron set
    ids = [n["id"] for n in N.active(net, 1)]
    rows_tv, A_tv = tr + dv, Atr + Adv
    loso = {}
    for X in TRAIN_SOURCES:
        keep = [i for i, r in enumerate(rows_tv) if r["source"] != X]
        rr = [rows_tv[i] for i in keep]
        Xm = matrix([A_tv[i] for i in keep], ids, N.kinds(net))
        C = net["readout"]["C"]
        m = fit(Xm, rr, C)
        thr = tune_threshold(rr, oof_predict(Xm, rr, C))
        idx = [i for i, r in enumerate(te) if r["source"] == X]
        p = m.predict_proba(matrix([At[i] for i in idx], ids, N.kinds(net)))[:, 1]
        y = [te[i]["label"] for i in idx]
        ps = [p_sq[i] for i in idx]
        thr_sq_x = tune_threshold([r for r in dv if r["source"] != X], [a[sq] for a, r in zip(Adv, dv) if r["source"] != X])
        loso[X] = {"english_net": metrics(y, p, thr), "single_question": metrics(y, ps, thr_sq_x)}
    R["leave_one_source_out"] = loso

    # robustness on attacks from never-trained sources
    rng = random.Random(7)
    pool = [r for r in te if r["label"] == 1 and r["source"] in ("gandalf", "deepset") and not re.search(r"[äöüß]", r["text"])]
    base = rng.sample(pool, min(60, len(pool)))
    rob = {}
    for kind in ["original", "greeting", "uppercase", "tokenbreak", "char_noise", "zero_width"]:
        texts = [b["text"] if kind == "original" else normalize(perturb(b["text"], kind, rng)) for b in base]
        A = jev.ask_many(texts, [n for n in need if n["id"] in ids + [sq]], purpose="final_robustness", workers=WORKERS, progress=False)
        p = predict_snapshot(net, A)
        rob[kind] = {"english_net_catch": round(100 * float((p >= net["readout"]["threshold"]).mean()), 1),
                     "single_question_catch_dev_t": round(100 * float((np.array([a[sq] for a in A]) >= thr_sq).mean()), 1)}
    R["robustness"] = {"n_attacks": len(base), "sources": "gandalf + deepset attacks (English)", "results": rob}

    if lat_n:
        R["latency"] = latency(net, te, lat_n)
    elif (RESULTS / "final.json").exists():  # keep the last measured latency instead of spending on it again
        old = json.loads((RESULTS / "final.json").read_text())
        if "latency" in old:
            R["latency"] = old["latency"]
    (RESULTS / "final.json").write_text(json.dumps(R, indent=1))
    from .fresh import FRESH
    if FRESH.exists():
        fresh_report(te, At)
    write_tables(R)
    print((RESULTS / "tables.md").read_text())


FRESH_ATTACK_ONLY = ["mosscap", "multiling_attack"]
FRESH_BENIGN_ONLY = ["aya_benign"]
FRESH_MIXED = ["spml", "jayavibhav"]
UNSEEN_OLD = ["deepset", "deepset_extra", "notinject", "gandalf", "adversarial"]


def paired_auc_ci(y, a, b, B=2000, seed=0):
    """AUC(a), AUC(b), and a 95% paired bootstrap interval for AUC(a) - AUC(b) (rows resampled with replacement)."""
    from sklearn.metrics import roc_auc_score
    y, a, b = np.asarray(y), np.asarray(a), np.asarray(b)
    rng = np.random.default_rng(seed)
    d = []
    for _ in range(B):
        s = rng.integers(0, len(y), len(y))
        if 0 < y[s].sum() < len(s):
            d.append(roc_auc_score(y[s], a[s]) - roc_auc_score(y[s], b[s]))
    lo, hi = np.percentile(d, [2.5, 97.5])
    return {"auc_a": round(float(roc_auc_score(y, a)), 4), "auc_b": round(float(roc_auc_score(y, b)), 4),
            "diff": round(float(roc_auc_score(y, a) - roc_auc_score(y, b)), 4), "ci95": [round(float(lo), 4), round(float(hi), 4)],
            "n": int(len(y)), "n_attack": int(y.sum())}


def fresh_report(te=None, At=None):
    """v6 vs the single question vs v5 vs baselines on the fresh confirmation set (englishnet/fresh.py), plus
    paired-bootstrap AUC intervals on three pools: fresh_test, the old never-trained sources, the old training-source
    test splits. Writes results/fresh.json. Cached answers only for the old test rows; fresh rows are asked if missing."""
    from .fresh import load_fresh
    net = N.load()
    v5 = json.loads((MODEL_DIR / "history" / "v05.json").read_text())
    patched = MODEL_DIR / "network_patched.json"
    pnet = json.loads(patched.read_text()) if patched.exists() else None
    sq = N.BASELINE_QUESTION["id"]
    broad = "is_injection_broad"
    need = N.active(net, 1) + ([n for n in N.active(pnet, 1) if n["id"] not in {m["id"] for m in N.active(net, 1)}] if pnet else [])
    ft = load_fresh("fresh_test", allow_test=True)
    Af = jev.ask_many([r["text"] for r in ft], need, purpose="fresh_eval", workers=WORKERS, progress=False)
    if te is None:
        te = load("test", allow_test=True)
    At = jev.ask_many([r["text"] for r in te], N.active(net, 1), purpose="final_eval_test", workers=WORKERS, progress=False)
    dv = load("dev")
    Adv = jev.ask_many([r["text"] for r in dv], N.active(net, 1), offline=True, progress=False)
    thr_sq = tune_threshold(dv, [a[broad] for a in Adv])
    preds = lambda A: {"v6": predict_snapshot(net, A), "single": np.array([a[broad] for a in A]), "v5": predict_snapshot(v5, A)}
    Pf, Pt = preds(Af), preds(At)
    if pnet:
        Pf["v6+patch"] = predict_snapshot(pnet, Af)
    thr = {"v6": net["readout"]["threshold"], "single": thr_sq, "v5": v5["readout"]["threshold"], "v6+patch": net["readout"]["threshold"]}
    try:
        from .baselines import load_scores
        for m in ["piguard", "protectai", "deepset", "tfidf"]:
            sc = load_scores(m)
            if all(r["id"] in sc for r in ft):
                Pf[m] = np.array([sc[r["id"]] for r in ft]); thr[m] = 0.5
    except Exception as e:
        print("baselines unavailable:", e)
    yf = np.array([r["label"] for r in ft]); sf = np.array([r["source"] for r in ft])
    R = {"n_fresh_test": len(ft), "thresholds": thr, "by_source": {}, "pooled_auc": {}, "ci": {}}
    for name, p in Pf.items():
        row = {}
        for s in FRESH_ATTACK_ONLY + FRESH_BENIGN_ONLY + FRESH_MIXED:
            m = sf == s
            row[s] = metrics(yf[m], p[m], thr[name])
        row["all_benign_false_alarms"] = round(100 * float((p[yf == 0] >= thr[name]).mean()), 1)
        row["all_attacks_caught"] = round(100 * float((p[yf == 1] >= thr[name]).mean()), 1)
        from sklearn.metrics import roc_auc_score
        R["pooled_auc"][name] = round(float(roc_auc_score(yf, p)), 4)
        R["by_source"][name] = row
    yt = np.array([r["label"] for r in te]); gt = np.array([group_of(r) for r in te])
    unseen = np.isin(gt, UNSEEN_OLD)
    R["ci"]["fresh_test: v6 - single"] = paired_auc_ci(yf, Pf["v6"], Pf["single"])
    R["ci"]["fresh_test: v6 - v5"] = paired_auc_ci(yf, Pf["v6"], Pf["v5"])
    R["ci"]["old never-trained sources: v6 - single"] = paired_auc_ci(yt[unseen], Pt["v6"][unseen], Pt["single"][unseen])
    R["ci"]["old never-trained sources: v5 - single"] = paired_auc_ci(yt[unseen], Pt["v5"][unseen], Pt["single"][unseen])
    R["ci"]["old training-source tests: v6 - single"] = paired_auc_ci(yt[~unseen], Pt["v6"][~unseen], Pt["single"][~unseen])
    if pnet:
        R["ci"]["fresh_test: v6+patch - v6"] = paired_auc_ci(yf, Pf["v6+patch"], Pf["v6"])
        R["ci"]["fresh_test: v6+patch - single"] = paired_auc_ci(yf, Pf["v6+patch"], Pf["single"])
    for k in ("piguard", "protectai"):
        if k in Pf:
            R["ci"][f"fresh_test: v6 - {k}"] = paired_auc_ci(yf, Pf["v6"], Pf[k])
    (RESULTS / "fresh.json").write_text(json.dumps(R, indent=1))
    return R


def fresh_tables(R):
    L = ["", "## Fresh confirmation set (never read before v6 was frozen; `englishnet/fresh.py`)", "",
         f"{R['n_fresh_test']} fresh_test rows. Attack catch % on attack-only sources, false alarms % on benign-only, "
         "acc / AUC on mixed. Thresholds: " + ", ".join(f"{k} {v}" for k, v in R["thresholds"].items()) + ".", "",
         "| Model | Mosscap catch | Multilingual catch | Aya benign false alarms | SPML acc / AUC | jayavibhav acc / AUC | all attacks caught | all benign false alarms | pooled AUC |",
         "|---|---|---|---|---|---|---|---|---|"]
    for name, r in R["by_source"].items():
        L.append(f"| {name} | {r['mosscap']['tpr']} | {r['multiling_attack']['tpr']} | {r['aya_benign']['fpr']} | "
                 f"{r['spml']['acc']} / {r['spml']['auc']:.3f} | {r['jayavibhav']['acc']} / {r['jayavibhav']['auc']:.3f} | "
                 f"{r['all_attacks_caught']} | {r['all_benign_false_alarms']} | {R['pooled_auc'][name]:.4f} |")
    L += ["", "## Paired bootstrap AUC differences (2,000 resamples, 95% interval)", "",
          "| Pool | n (attacks) | AUC A | AUC B | A - B | 95% interval |", "|---|---|---|---|---|---|"]
    for k, c in R["ci"].items():
        L.append(f"| {k} | {c['n']} ({c['n_attack']}) | {c['auc_a']:.4f} | {c['auc_b']:.4f} | {c['diff']:+.4f} | "
                 f"[{c['ci95'][0]:+.4f}, {c['ci95'][1]:+.4f}] |")
    return L


def _fmt(m, keys):
    return " | ".join(("" if k not in m else (f"{m[k]:.3f}" if k == "auc" else f"{m[k]}")) for k in keys)


def write_tables(R):
    L = ["# Results", "", f"Generated by `python -m englishnet.eval --final` from cached answers. Jev model `{R['jev_model']}`. "
         f"Test rows: {R['n_test']}. Accuracy and rates in %.", ""]
    L += ["## Training sources (test splits)", "", "Accuracy at each model's threshold / AUC.", "",
          "| Model | " + " | ".join(TRAIN_SOURCES) + " | macro acc | macro AUC |", "|---" * (len(TRAIN_SOURCES) + 3) + "|"]
    for name, res in R["models"].items():
        cells = [f"{res[s]['acc']} / {res[s]['auc']:.3f}" if s in res else "" for s in TRAIN_SOURCES]
        L.append(f"| {name} | " + " | ".join(cells) + f" | {res['macro_train_sources']['acc']} | {res['macro_train_sources']['auc']:.3f} |")
    L += ["", "## Sources never used in training", "",
          "| Model | deepset test acc / AUC | deepset extra acc / AUC | NotInject false alarms | Gandalf catch | Held-out adaptive attacks: acc / catch / false alarms |",
          "|---|---|---|---|---|---|"]
    for name, res in R["models"].items():
        d, dx, ni, g, a = (res.get(k, {}) for k in ["deepset", "deepset_extra", "notinject", "gandalf", "adversarial"])
        L.append(f"| {name} | {d.get('acc','')} / {d.get('auc',0):.3f} | {dx.get('acc','')} / {dx.get('auc',0):.3f} | "
                 f"{ni.get('fpr','')} | {g.get('tpr','')} | {a.get('acc','')} / {a.get('tpr','')} / {a.get('fpr','')} |")
    L += ["", "Catch rate at a fixed false-alarm rate (threshold-free), deepset official test:", "",
          "| Model | catch @1% FPR | catch @5% FPR |", "|---|---|---|"]
    for name, res in R["models"].items():
        d = res.get("deepset", {})
        L.append(f"| {name} | {d.get('catch@1%fpr','')} | {d.get('catch@5%fpr','')} |")
    L += ["", "## Leave one training source out (final neuron set, readout refit without that source)", "",
          "| Held-out source | English Net acc / AUC | Single question acc / AUC |", "|---|---|---|"]
    for s, v in R["leave_one_source_out"].items():
        L.append(f"| {s} | {v['english_net']['acc']} / {v['english_net']['auc']:.3f} | {v['single_question']['acc']} / {v['single_question']['auc']:.3f} |")
    L += ["", "## Every network version on the test sets", "",
          "| Version | Neurons | macro acc (training sources) | deepset acc / AUC | NotInject false alarms | Gandalf catch | Held-out attacks catch |",
          "|---|---|---|---|---|---|---|"]
    for k, v in R["trajectory"].items():
        t = v["test"]
        L.append(f"| {k} | {v['n_active']} | {t['macro_train_sources']['acc']} | {t['deepset']['acc']} / {t['deepset']['auc']:.3f} | "
                 f"{t['notinject']['fpr']} | {t['gandalf']['tpr']} | {t['adversarial']['tpr']} |")
    rb = R["robustness"]
    L += ["", f"## Robustness ({rb['n_attacks']} attacks from {rb['sources']}; catch rate %)", "",
          "| Perturbation | English Net | Single question (dev-tuned) |", "|---|---|---|"]
    for k, v in rb["results"].items():
        L.append(f"| {k} | {v['english_net_catch']} | {v['single_question_catch_dev_t']} |")
    if "latency" in R:
        l = R["latency"]
        L += ["", "## Latency and cost (uncached calls)", "",
              f"{l['n']} test texts, {l['n_questions']} questions per call: median {l['median_ms']} ms, p90 {l['p90_ms']} ms, "
              f"median {l['median_tokens']} input tokens = {l['usd_per_input_median']} USD per input "
              f"({l['usd_per_million_inputs']} USD per million inputs). {l['where']}."]
    if R.get("baselines_missing"):
        L += ["", f"Baselines without complete test scores (not in the tables): {', '.join(R['baselines_missing'])}."]
    if (RESULTS / "fresh.json").exists():
        L += fresh_tables(json.loads((RESULTS / "fresh.json").read_text()))
    if (RESULTS / "patch.json").exists():
        P = json.loads((RESULTS / "patch.json").read_text())
        f, e = P["family"], P["everything_else"]
        L += ["", "## One-sentence patch (`englishnet/patch.py`, fresh_test + every test split)", "",
              f"Neuron: \"{P['patch']['question']}\" Weight {P['patch']['weight']} (rule: a yes at p = {P['rule']['p_confident']} lifts "
              f"the median benign train+dev text over the threshold). Paraphrase kappa on fresh_dev {P['paraphrase_kappa_fresh_dev']}.", "",
              "| Rows | n | catch before -> after | false alarms before -> after | new catches | new false alarms | new misses |",
              "|---|---|---|---|---|---|---|",
              f"| Mosscap (the family) | {f['n']} | {f['catch_before']} -> {f['catch_after']} | | {f['new_catches']} | {f['new_false_alarms']} | {f['new_misses']} |",
              f"| everything else | {e['n']} | {e['catch_before']} -> {e['catch_after']} | {e['false_alarm_before']} -> {e['false_alarm_after']} | "
              f"{e['new_catches']} | {e['new_false_alarms']} | {e['new_misses']} |"]
    (RESULTS / "tables.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true", help="required: this opens the test split")
    ap.add_argument("--latency", type=int, default=0)
    ap.add_argument("--tables-only", action="store_true")
    ap.add_argument("--fresh-only", action="store_true", help="only the fresh confirmation set and bootstrap intervals")
    a = ap.parse_args()
    if a.fresh_only:
        fresh_report()
        write_tables(json.loads((RESULTS / "final.json").read_text()))
    elif a.tables_only:
        write_tables(json.loads((RESULTS / "final.json").read_text()))
    elif a.final:
        final(a.latency)
    else:
        ap.error("pass --final to run the test-set evaluation")
