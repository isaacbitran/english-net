"""The same patch done the usual way: fine-tune a DeBERTa detector on the examples the English patch was written from.

  python -m englishnet.finetune      # writes results/finetune.json (local GPU/CPU, no API calls)

Model: protectai/deberta-v3-base-prompt-injection-v2 (the strongest fixed baseline on fresh_test catch rate).
Training data: the 30 fresh_dev Mosscap misses that the English patch was written from (label 1) plus 30 benign
fresh_dev rows (seeded sample of aya_benign and spml benign, label 0). Full fine-tune, AdamW lr 2e-5, batch 8,
5 epochs. Then the same before/after measurement as englishnet.patch: Mosscap fresh_test catch, and verdict flips
on every other fresh_test and test row at threshold 0.5.

Reads test rows (allow_test=True) only to report; nothing here feeds back into English Net.
"""
import json
import random
import time

import numpy as np

from .baselines import HF_MODELS, load_scores
from .config import RESULTS
from .data import load
from .eval import group_of
from .fresh import load_fresh
from .patch import flips

SEED = 0
EPOCHS = 5
LR = 2e-5
BATCH = 8


def main():
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    patch = json.loads((RESULTS / "patch.json").read_text())
    fam_ids = set(patch["patch"]["parent"]["example_ids"])
    fdev = load_fresh("fresh_dev")
    pos = [r for r in fdev if r["id"] in fam_ids]
    rng = random.Random(SEED)
    neg = rng.sample([r for r in fdev if r["label"] == 0 and r["source"] in ("aya_benign", "spml")], len(pos))
    train = pos + neg
    rng.shuffle(train)

    spec = HF_MODELS["protectai"]
    tok = AutoTokenizer.from_pretrained(spec["repo"], revision=spec["revision"])
    model = AutoModelForSequenceClassification.from_pretrained(spec["repo"], revision=spec["revision"])
    att = [k for k, v in model.config.id2label.items() if "inject" in v.lower()][0]
    import os
    dev = os.environ.get("DEVICE") or ("mps" if torch.backends.mps.is_available() else "cpu")
    torch.manual_seed(SEED)
    model.to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=LR)
    t0 = time.time()
    model.train()
    for ep in range(EPOCHS):
        for b in range(0, len(train), BATCH):
            chunk = train[b:b + BATCH]
            enc = tok([r["text"] for r in chunk], truncation=True, max_length=512, padding=True, return_tensors="pt").to(dev)
            y = torch.tensor([att if r["label"] == 1 else 1 - att for r in chunk], device=dev)
            loss = model(**{k: v for k, v in enc.items() if k in ("input_ids", "attention_mask")}, labels=y).loss
            loss.backward(); opt.step(); opt.zero_grad()
        print(f"epoch {ep + 1}/{EPOCHS} loss {loss.item():.4f} {time.time() - t0:.0f}s", flush=True)
    train_s = time.time() - t0
    model.eval()

    ft = load_fresh("fresh_test", allow_test=True)
    te = load("test", allow_test=True)
    rows = ft + te
    grp = np.array([r["source"] for r in ft] + [group_of(r) for r in te])
    p1 = np.zeros(len(rows))
    order = sorted(range(len(rows)), key=lambda i: len(rows[i]["text"]))
    with torch.no_grad():
        for b in range(0, len(order), 16):
            idx = order[b:b + 16]
            enc = tok([rows[i]["text"] for i in idx], truncation=True, max_length=512, padding=True, return_tensors="pt").to(dev)
            lg = model(**{k: v for k, v in enc.items() if k in ("input_ids", "attention_mask")}).logits.float()
            p1[idx] = torch.softmax(lg, -1)[:, att].cpu().numpy()
            if b % 1600 == 0:
                print(f"scored {b}/{len(order)}", flush=True)
    base = load_scores("protectai")
    p0 = np.array([base[r["id"]] for r in rows])
    fam = grp == "mosscap"
    out = {"model": spec["repo"], "device": dev, "train_examples": {"attack": len(pos), "benign": len(neg)},
           "epochs": EPOCHS, "lr": LR, "batch": BATCH, "train_seconds": round(train_s, 1), "threshold": 0.5,
           "family": flips([rows[i] for i in np.where(fam)[0]], p0[fam], p1[fam], 0.5),
           "everything_else": flips([rows[i] for i in np.where(~fam)[0]], p0[~fam], p1[~fam], 0.5),
           "by_group": {g: flips([rows[i] for i in np.where(grp == g)[0]], p0[grp == g], p1[grp == g], 0.5) for g in sorted(set(grp))}}
    (RESULTS / "finetune.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "by_group"}, indent=1))


if __name__ == "__main__":
    main()
