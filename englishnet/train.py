"""The evolution loop. One round = answer, fit, report, propose, consistency gate, select, prune, save.

  python -m englishnet.train init            # round 0: the 30 hand-written neurons, fitted
  python -m englishnet.train round           # one evolution round (proposer = Claude API, or an in-session response)
  python -m englishnet.train refit           # refit readout of the current network (no proposals)
  python -m englishnet.train stack           # v6: add the broad question as a log-odds neuron, refit (no new answers)

Data: only train and dev rows are loaded here (englishnet.data.load raises on test). The proposer sees out-of-fold
errors from the train split only; selection uses dev; test is untouched until `englishnet.eval --final`.
"""
import argparse
import json
import random
import sys
from datetime import date

import numpy as np
from sklearn.metrics import cohen_kappa_score

from . import jev
from . import neurons as N
from .config import RESULTS
from .data import TRAIN_SOURCES, load
from .fit import Objective, fit, matrix, oof_predict, tune_threshold
from .propose import NeedsInSessionResponse, get_response, proposer_prompt

C_GRID = [0.1, 0.25, 0.5, 1.0, 2.0]
ADD_GAIN = 0.001          # a candidate must raise J by more than this
DROP_TOL = 0.0003         # a neuron is dropped if J falls by less than this without it
DROP_FLOOR = 0.001        # total J given up by drops in one round is at most this
KAPPA_MIN = 0.7           # consistency gate: Cohen's kappa between question and paraphrase, at 0.5
GATE_N = 300              # dev rows used by the consistency gate
WORKERS = 12


def rows_tv():
    tr, dv = load("train"), load("dev")
    return tr, dv


def answer(rows, neurons, purpose):
    l1 = [n for n in neurons if n["layer"] == 1]
    return jev.ask_many([r["text"] for r in rows], l1, purpose=purpose, workers=WORKERS)


def merge(a, b):
    for x, y in zip(a, b):
        x.update(y)
    return a


def objective_sources(dev):
    srcs = list(TRAIN_SOURCES)
    adv = [r for r in dev if r["source"] == "adversarial"]
    if adv and len({r["label"] for r in adv}) == 2:
        srcs.append("adversarial")
    return srcs


def build_objective(tr, dv, Atr, Adv, ids, C):
    return Objective(tr, dv, matrix(Atr, ids), matrix(Adv, ids), C=C, sources=objective_sources(dv))


def finalize(net, tr, dv, Atr, Adv, ids, C, round_no):
    """Fit the readout on train+dev, set threshold from out-of-fold predictions, write weights and activations."""
    rows = tr + dv
    X = matrix(Atr + Adv, ids, N.kinds(net))
    P = matrix(Atr + Adv, ids)
    m = fit(X, rows, C)
    p_oof = oof_predict(X, rows, C)
    thr = tune_threshold(rows, p_oof)
    y = np.array([r["label"] for r in rows])
    byid = N.by_id(net)
    for i, nid in enumerate(ids):
        n = byid[nid]
        n["weight"] = round(float(m.coef_[0][i]), 4)
        n["activation"] = {"attack": round(float((P[y == 1, i] >= 0.5).mean()), 3),
                           "benign": round(float((P[y == 0, i] >= 0.5).mean()), 3)}
    for nid in ids:
        if byid[nid]["weight"] == 0.0:
            byid[nid]["status"] = "pruned"
            byid[nid]["note"] = f"L1 set weight to 0 in round {round_no}"
    net["readout"] = {"type": "logistic", "intercept": round(float(m.intercept_[0]), 4), "threshold": thr, "C": C,
                      "fit_on": "train+dev", "sample_weighting": "equal total weight per (source, label)"}
    return thr


def neuron_table(net, Atr, tr):
    y = np.array([r["label"] for r in tr])
    out = []
    for n in sorted(N.active(net, 1), key=lambda n: -abs(n["weight"])):
        x = np.array([a[n["id"]] for a in Atr])
        out.append({"id": n["id"], "question": n["question"], "weight": n["weight"],
                    "act_a": float((x[y == 1] >= 0.5).mean()), "act_b": float((x[y == 0] >= 0.5).mean())})
    return out


def worst_errors(net, tr, Atr, C, per_source=6):
    ids = [n["id"] for n in N.active(net, 1)]
    X = matrix(Atr, ids)
    p = oof_predict(X, tr, C)
    w = {n["id"]: n["weight"] for n in N.active(net, 1)}
    errs = []
    for s in sorted({r["source"] for r in tr}):
        idx = [i for i, r in enumerate(tr) if r["source"] == s]
        idx.sort(key=lambda i: -abs(tr[i]["label"] - p[i]))
        k = per_source * (2 if s == "adversarial" else 1)
        for i in idx[:k]:
            if abs(tr[i]["label"] - p[i]) < 0.3:
                continue
            contrib = sorted(((w[n] * Atr[i][n], n) for n in ids), key=lambda t: -abs(t[0]))[:3]
            errs.append({"row": tr[i], "p": float(p[i]), "top": [f"{n}({c:+.2f})" for c, n in contrib]})
    return errs


def gate(cands, dv, round_no):
    """Ask each candidate's paraphrase on GATE_N dev rows; return {id: (kappa, reason or None)}."""
    rng = random.Random(round_no)
    adv = [r for r in dv if r["source"] == "adversarial"]  # rare attack families must be in the gate sample
    rest = [r for r in dv if r["source"] != "adversarial"]
    sub = adv + rng.sample(rest, min(GATE_N, len(rest)))
    para = [{"id": c["id"] + "__para", "question": c["paraphrase"], "layer": 1} for c in cands if c.get("paraphrase")]
    A = answer(sub, cands + para, f"round{round_no:02d}_gate")
    out = {}
    for c in cands:
        if not c.get("paraphrase"):
            out[c["id"]] = (None, "no paraphrase given")
            continue
        a = np.array([x[c["id"]] for x in A]) >= 0.5
        b = np.array([x[c["id"] + "__para"] for x in A]) >= 0.5
        if a.sum() < 5 and b.sum() < 5:
            out[c["id"]] = (None, f"fires on fewer than 5 of {len(sub)} gate texts")
            continue
        k = float(cohen_kappa_score(a, b)) if (a.any() or b.any()) and not (a.all() and b.all()) else 1.0
        out[c["id"]] = (round(k, 3), None if k >= KAPPA_MIN else f"paraphrase disagrees (kappa {k:.2f} < {KAPPA_MIN})")
    return out


def summarize(added, dropped, revised, rejected, j0, j1, byid):
    bits = []
    if added:
        bits.append("Added " + "; ".join(f"\"{byid[a]['question']}\"" for a in added) + ".")
    if revised:
        bits.append(f"Reworded {', '.join(revised)}.")
    if dropped:
        bits.append(f"Dropped {', '.join(dropped)}.")
    bits.append(f"{len(rejected)} proposals rejected. Selection score {j0:.4f} -> {j1:.4f}.")
    return " ".join(bits)


def cmd_init():
    net = N.seed_network()
    tr, dv = rows_tv()
    l1 = N.active(net, 1)
    Atr, Adv = answer(tr, l1, "round00_seed"), answer(dv, l1, "round00_seed")
    ids = [n["id"] for n in l1]
    obj = build_objective(tr, dv, Atr, Adv, ids, 0.5)
    best_C = max(C_GRID, key=lambda C: build_objective(tr, dv, Atr, Adv, ids, C)(list(range(len(ids)))))
    obj = build_objective(tr, dv, Atr, Adv, ids, best_C)
    J = obj(list(range(len(ids))))
    pooled, loso = obj.parts(list(range(len(ids))))
    thr = finalize(net, tr, dv, Atr, Adv, ids, best_C, 0)
    net["version"] = 0
    net["history"].append({"round": 0, "kind": "seed", "at": "2026-10-19", "proposer": "human",
                           "added": ids, "dropped": [], "revised": [], "rejected": [],
                           "metrics": {"J": round(J, 4), "pooled_dev_auc": _r(pooled), "loso_dev_auc": _r(loso),
                                       "n_active": len(N.active(net)), "C": best_C, "threshold": thr},
                           "summary": f"30 hand-written questions. Selection score {J:.4f}."})
    N.save(net)
    print(json.dumps(net["history"][-1], indent=1))


def _r(d):
    return {k: round(float(v), 4) for k, v in d.items()}


def cmd_round(kind="evolution"):
    net = N.load()
    round_no = max(h["round"] for h in net["history"]) + 1
    tr, dv = rows_tv()
    l1 = N.active(net, 1)
    ids = [n["id"] for n in l1]
    Atr, Adv = answer(tr, l1, f"round{round_no:02d}_active"), answer(dv, l1, f"round{round_no:02d}_active")
    C = net["readout"]["C"] or 0.5
    # refresh weights on the current data (adversarial rows may have been added since the last round)
    finalize(net, tr, dv, Atr, Adv, ids, C, round_no)
    ids = [n["id"] for n in N.active(net, 1)]
    obj = build_objective(tr, dv, Atr, Adv, ids, C)
    J0 = obj(list(range(len(ids))))
    pooled, loso = obj.parts(list(range(len(ids))))

    rejected_prev = [{"id": n["id"], "question": n["question"], "reason": n.get("note") or "rejected"}
                     for n in net["neurons"] if n["status"] == "rejected" and n["born_round"] == round_no - 1]
    errs = worst_errors(net, tr, Atr, C)
    prompt = proposer_prompt(round_no, neuron_table(net, Atr, tr), {s: (pooled[s], loso[s]) for s in pooled},
                             errs, rejected_prev)
    try:
        resp, proposer = get_response(round_no, "proposer", prompt)
    except NeedsInSessionResponse as e:
        print(str(e))
        sys.exit(2)

    byid = N.by_id(net)
    err_by_id = {e["row"]["id"]: e for e in errs}
    cands = []
    for a in resp.get("add", []):
        nid = a["id"]
        if nid in byid:
            nid = f"{nid}_r{round_no}"
        pids = [p for p in a.get("parent_example_ids", []) if p in err_by_id]
        kind_ = "attack" if any(err_by_id[p]["row"]["source"] == "adversarial" for p in pids) else ("error" if pids else "none")
        parent = {"kind": kind_, "example_ids": pids,
                  "excerpt": err_by_id[pids[0]]["row"]["text"][:300] if pids else a.get("parent_excerpt", ""),
                  "why": a.get("why", "")}
        n = N.make_neuron(nid, a["question"], round_no, "adversarial" if kind_ == "attack" else "evolved",
                          proposer, parent=parent, paraphrase=a.get("paraphrase"))
        cands.append(n)
    revs = []
    for rv in resp.get("revise", []):
        if rv["id"] in byid and byid[rv["id"]]["status"] == "active":
            n = N.make_neuron(f"{rv['id']}_v{round_no}", rv["question"], round_no, "evolved", proposer,
                              parent={"kind": "revision", "example_ids": [], "excerpt": "", "why": f"rewording of {rv['id']}"},
                              paraphrase=rv.get("paraphrase"))
            n["revises"] = rv["id"]
            revs.append(n)

    # consistency gate
    g = gate(cands + revs, dv, round_no)
    for n in cands + revs:
        n["consistency_kappa"], reason = g[n["id"]]
        if reason:
            n["status"], n["note"] = "rejected", reason
    live = [n for n in cands + revs if n["status"] == "candidate"]

    # answer survivors on all train+dev rows
    if live:
        merge(Atr, answer(tr, live, f"round{round_no:02d}_candidates"))
        merge(Adv, answer(dv, live, f"round{round_no:02d}_candidates"))
    pool = ids + [n["id"] for n in live]
    objp = build_objective(tr, dv, Atr, Adv, pool, C)
    col = {nid: i for i, nid in enumerate(pool)}
    J = lambda S: objp([col[s] for s in S])

    cur = list(ids)
    Jc = J(cur)
    single = {n["id"]: J(cur + [n["id"]]) for n in live if "revises" not in n}
    added = []
    for nid in sorted(single, key=lambda k: -single[k]):
        if np.std([a[nid] for a in Atr]) < 0.02:
            N.by_id({"neurons": cands})[nid].update(status="rejected", note="answers are flat on train")
            continue
        j = J(cur + [nid])
        if j > Jc + ADD_GAIN:
            cur.append(nid); Jc = j; added.append(nid)
    revised = []
    for n in revs:
        if n["status"] != "candidate" or n["revises"] not in cur:
            continue
        trial = [n["id"] if x == n["revises"] else x for x in cur]
        j = J(trial)
        if j > Jc + ADD_GAIN:
            cur, Jc = trial, j; revised.append(n["revises"]); added.append(n["id"])
    J_after_add = Jc
    dropped = []
    proposed_drops = [d for d in resp.get("drop", []) if d in cur]
    wabs = {n["id"]: abs(n["weight"]) for n in net["neurons"]}
    # Backward elimination: proposer drops first, then the weakest neurons. A one-off check in round 1 (all neurons
    # kept: J 0.918, openpi leave-out AUC 0.677; eliminated to 9 neurons: J 0.951, 0.883) showed that neurons tracking
    # one dataset's style hurt transfer, so elimination stays on.
    order = proposed_drops + sorted([x for x in cur if x not in proposed_drops and x not in added], key=lambda x: wabs.get(x, 0))
    for nid in order:
        if nid not in cur or len(cur) <= 5:
            continue
        trial = [x for x in cur if x != nid]
        j = J(trial)
        if j >= Jc - DROP_TOL and j >= J_after_add - DROP_FLOOR:
            cur, Jc = trial, j; dropped.append(nid)

    # tune C on the selected set
    bestC = max(C_GRID, key=lambda c: build_objective(tr, dv, Atr, Adv, cur, c)(list(range(len(cur)))))
    objf = build_objective(tr, dv, Atr, Adv, cur, bestC)
    J1 = objf(list(range(len(cur))))
    pooled1, loso1 = objf.parts(list(range(len(cur))))

    # write statuses
    allc = {n["id"]: n for n in cands + revs}
    for nid, n in allc.items():
        if n["status"] == "candidate":
            n["status"] = "active" if nid in cur else "rejected"
            if n["status"] == "rejected" and not n.get("note"):
                n["note"] = f"did not raise the selection score by more than {ADD_GAIN}"
    net["neurons"] += list(allc.values())
    byid = N.by_id(net)
    for nid in dropped:
        byid[nid]["status"] = "pruned"
        byid[nid]["note"] = f"dropped in round {round_no}: selection score unchanged without it"
    for old in revised:
        byid[old]["status"] = "pruned"
        byid[old]["note"] = f"replaced by a reworded version in round {round_no}"
    thr = finalize(net, tr, dv, Atr, Adv, cur, bestC, round_no)
    net["version"] += 1
    rejected = [{"id": n["id"], "reason": n.get("note")} for n in allc.values() if n["status"] == "rejected"]
    entry = {"round": round_no, "kind": kind, "at": date.today().isoformat(), "proposer": proposer,
             "added": added, "dropped": dropped, "revised": revised, "rejected": rejected,
             "metrics": {"J_before": round(J0, 4), "J": round(J1, 4), "pooled_dev_auc": _r(pooled1),
                         "loso_dev_auc": _r(loso1), "n_active": len(N.active(net)), "C": bestC, "threshold": thr,
                         "n_proposed": len(cands), "n_revisions_proposed": len(revs),
                         "n_passed_gate": len(live)},
             "summary": summarize(added, dropped, revised, rejected, J0, J1, byid)}
    net["history"].append(entry)
    N.save(net)
    (RESULTS / "rounds").mkdir(exist_ok=True)
    (RESULTS / "rounds" / f"round_{round_no:02d}.json").write_text(json.dumps(entry, indent=1))
    print(json.dumps(entry, indent=1))


BROAD_ID = "is_injection_broad"
STACK_C_GRID = [0.05, 0.1, 0.25, 0.5, 1.0]


def cmd_stack():
    """v5 -> v6: add the broad single question as a neuron read as log-odds, refit the readout.

    Why: v5's six specific questions lost to that one question as a ranker on sources never used in training. With
    the broad question inside the network, the readout can fall back on it, and the specific questions only have
    to add what it misses. Choices made on train/dev only: input transform (probability vs log-odds of the broad
    answer) and C, both by the selection score J. Train/dev answers for the broad question are already cached."""
    net = N.load()
    if any(n["id"] == BROAD_ID for n in net["neurons"]):
        sys.exit("network already has the broad neuron")
    tr, dv = rows_tv()
    broad = N.make_neuron(BROAD_ID, N.BASELINE_QUESTION["question"], 10, "hand-written", "human",
                          note="The single-question baseline, added as a neuron in v6 so the network cannot rank worse than it.")
    broad["status"] = "active"
    broad["paraphrase"] = None
    net["neurons"].insert(0, broad)
    l1 = N.active(net, 1)
    ids = [n["id"] for n in l1]
    Atr, Adv = answer(tr, l1, "stack"), answer(dv, l1, "stack")
    trials = {}
    for kind in ("prob", "logit"):
        broad["input"] = kind
        for C in STACK_C_GRID:
            o = Objective(tr, dv, matrix(Atr, ids, N.kinds(net)), matrix(Adv, ids, N.kinds(net)), C=C,
                          sources=objective_sources(dv))
            trials[(kind, C)] = o(list(range(len(ids))))
    (kind, C), J = max(trials.items(), key=lambda kv: kv[1])
    broad["input"] = kind
    thr = finalize(net, tr, dv, Atr, Adv, ids, C, 10)
    net["version"] = 6
    net["history"].append({"round": 10, "kind": "stack", "at": date.today().isoformat(), "proposer": "human",
                           "added": [BROAD_ID], "dropped": [n["id"] for n in l1 if n["weight"] == 0.0],
                           "revised": [], "rejected": [],
                           "metrics": {"J": round(J, 4), "trials": {f"{k}/C={c}": round(v, 4) for (k, c), v in trials.items()},
                                       "input": kind, "C": C, "threshold": thr, "n_active": len(N.active(net))},
                           "summary": f"Added the broad question as a neuron (input {kind}). Selection score {J:.4f}; "
                                      f"chosen from {len(trials)} settings on dev."})
    N.save(net)
    print(json.dumps(net["history"][-1], indent=1))


def cmd_refit():
    net = N.load()
    tr, dv = rows_tv()
    l1 = N.active(net, 1)
    ids = [n["id"] for n in l1]
    Atr, Adv = answer(tr, l1, "refit"), answer(dv, l1, "refit")
    finalize(net, tr, dv, Atr, Adv, ids, net["readout"]["C"] or 0.5, max(h["round"] for h in net["history"]))
    N.save(net, snapshot=False)
    print(net["readout"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["init", "round", "refit", "stack"])
    ap.add_argument("--kind", default="evolution")
    a = ap.parse_args()
    {"init": cmd_init, "round": lambda: cmd_round(a.kind), "refit": cmd_refit, "stack": cmd_stack}[a.cmd]()
