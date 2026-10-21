"""Adversarial self-play rounds.

  python -m englishnet.adversary prompt               # write the attacker prompt for the next round (white-box)
  python -m englishnet.adversary score [--heldout]    # score the attacker's texts with the CURRENT network, log the
                                                      # raw catch rate, and add the texts to data/adversarial.jsonl
  python -m englishnet.adversary import-web           # turn web/data/submissions.jsonl into attacker texts

Protocol
  - The attacker sees every neuron and weight and writes attacks it expects to slip through, plus benign hard negatives.
  - The raw catch rate is measured on ALL attacker texts, before any training on them. That number is the honest
    "adaptive attack" result for that network version.
  - Training rounds: the texts are split 50/50 (stratified) into train and dev rows of source "adversarial". The next
    evolution round's proposer sees the train-split misses; the dev half enters the selection score.
  - The final round (--heldout) writes split "test": never trained on, locked like every test set.
"""
import argparse
import json
import random
import sys
from datetime import date
from pathlib import Path

from . import neurons as N
from .config import ROOT
from .data import ADV_FILE, normalize
from .forward import score
from .propose import NeedsInSessionResponse, attacker_prompt, get_response


def next_round(net):
    return max(h["round"] for h in net["history"]) + 1


def cmd_prompt():
    net = N.load()
    r = next_round(net)
    table = [{"id": n["id"], "question": n["question"], "weight": n["weight"]} for n in N.active(net)]
    try:
        get_response(r, "attacker", attacker_prompt(r, table))
        print(f"response for round {r} already present; run `score`")
    except NeedsInSessionResponse as e:
        print(str(e)); sys.exit(2)


def cmd_score(heldout=False):
    net = N.load()
    r = next_round(net)
    table = [{"id": n["id"], "question": n["question"], "weight": n["weight"]} for n in N.active(net)]
    resp, proposer = get_response(r, "attacker", attacker_prompt(r, table))
    items = [("a", a, 1) for a in resp["attacks"]] + [("b", b, 0) for b in resp.get("benign", [])]
    thr = net["readout"]["threshold"]
    scored = []
    for kind, it, y in items:
        v = score(it["text"], net, purpose=f"round{r:02d}_attack")
        scored.append({"id": f"adv-r{r:02d}-{it['id']}", "label": y, "family": it.get("family", "benign hard negative"),
                       "text": normalize(it["text"]), "p_attack": v["p_attack"], "caught": (v["p_attack"] >= thr) == bool(y),
                       "top": [f"{c['id']}({c['contribution']:+.2f})" for c in v["contributions"][:3]]})
    att = [s for s in scored if s["label"] == 1]
    ben = [s for s in scored if s["label"] == 0]
    fams = {}
    for s in att:
        fams.setdefault(s["family"], []).append(s["caught"])
    metrics = {"network_version": net["version"], "n_attacks": len(att), "n_benign": len(ben),
               "catch_rate": round(100 * sum(s["caught"] for s in att) / max(1, len(att)), 1),
               "false_alarm_rate_hard_benign": round(100 * sum(not s["caught"] for s in ben) / max(1, len(ben)), 1),
               "by_family": {f: f"{sum(v)}/{len(v)}" for f, v in fams.items()}, "threshold": thr}
    out = {"round": r, "kind": "attack-heldout" if heldout else "attack", "at": date.today().isoformat(),
           "proposer": proposer, "metrics": metrics, "items": scored}
    (ROOT / "attacks").mkdir(exist_ok=True)
    (ROOT / "attacks" / f"round_{r:02d}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))

    # add to the adversarial source
    rng = random.Random(r)
    rows = []
    for lab in (1, 0):
        grp = [s for s in scored if s["label"] == lab]
        rng.shuffle(grp)
        for i, s in enumerate(grp):
            split = "test" if heldout else ("train" if i % 2 == 0 else "dev")
            rows.append({"id": s["id"], "text": s["text"], "label": lab, "source": "adversarial", "split": split,
                         "group": s["id"], "round": r, "family": s["family"]})
    existing = {json.loads(l)["id"] for l in ADV_FILE.open()} if ADV_FILE.exists() else set()
    with ADV_FILE.open("a") as f:
        for row in rows:
            if row["id"] not in existing:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    missed = [s for s in att if not s["caught"]]
    summary = (f"Attacker wrote {len(att)} attacks and {len(ben)} benign hard negatives against network v{net['version']}. "
               f"Caught {metrics['catch_rate']}% of attacks; false alarms on {metrics['false_alarm_rate_hard_benign']}% of the hard negatives."
               + ("" if heldout else f" {len(missed)} missed attacks go to the next evolution round (half as training rows, half as selection rows)."))
    net["history"].append({"round": r, "kind": out["kind"], "at": out["at"], "proposer": proposer, "added": [], "dropped": [],
                           "revised": [], "rejected": [], "metrics": metrics, "summary": summary,
                           "examples_missed": [{"id": s["id"], "family": s["family"], "excerpt": s["text"][:200], "p_attack": s["p_attack"]} for s in missed[:12]]})
    N.save(net, snapshot=False)
    print(json.dumps(metrics, indent=1)); print(summary)


def cmd_import_web():
    f = ROOT / "web" / "data" / "submissions.jsonl"
    if not f.exists():
        print("no submissions"); return
    net = N.load(); r = next_round(net)
    subs = [json.loads(l) for l in f.open() if l.strip()]
    rf = ROOT / "proposals" / f"round_{r:02d}_attacker_response.json"
    d = json.loads(rf.read_text()) if rf.exists() else {"proposer": "web-submissions", "attacks": [], "benign": []}
    have = {a["text"] for a in d["attacks"]}
    for i, s in enumerate(subs):
        if s["text"] not in have:
            d["attacks"].append({"id": f"w{i:03d}", "family": "web submission", "text": s["text"]})
    rf.write_text(json.dumps(d, indent=1, ensure_ascii=False))
    print(f"{len(subs)} submissions -> {rf}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prompt", "score", "import-web"])
    ap.add_argument("--heldout", action="store_true")
    a = ap.parse_args()
    {"prompt": cmd_prompt, "score": lambda: cmd_score(a.heldout), "import-web": cmd_import_web}[a.cmd]()
