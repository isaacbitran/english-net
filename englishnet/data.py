"""Dataset download, normalization, cross-source dedupe and source-aware splits.

Every example is {id, text, label, source, split, group}. label 1 = attack (prompt injection or jailbreak), 0 = benign.

Sources
  Training sources (their train/dev splits are used for evolution and fitting; their test split only for final numbers):
    safeguard  xTRam1/safe-guard-prompt-injection    (official train -> train/dev, official test -> test)
    jackhhao   jackhhao/jailbreak-classification     (official train -> train/dev, official test -> test)
    itw        TrustAIRLab/in-the-wild-jailbreak-prompts, 2023_12_25 jailbreak vs regular prompts
    openpi     xxz224/prompt-injection-attack-dataset (Open-Prompt-Injection: clean task data vs data with
               an injected instruction; grouped by row id so a clean text and its attacked version share a split)
  Held-out sources (never used for training, selection or proposals; test only):
    deepset    deepset/prompt-injections (official test 116; the 546 official-train rows are a second test set)
    notinject  leolee99/NotInject (339 benign prompts full of trigger words; measures false alarms)
    gandalf    Lakera/gandalf_ignore_instructions (validation + test, 223 attacks; measures catch rate)

Test lock: `load(split="test")` raises unless the caller passes `allow_test=True`. Only `englishnet.eval --final`
does that. The training and proposal code never passes it (enforced by tests/test_protocol.py).

Usage: python -m englishnet.data   (writes data/examples.jsonl and data/manifest.json)
"""
import hashlib
import json
import random
import re
import unicodedata
from collections import Counter

from .config import DATA, MAX_CHARS

TRAIN_SOURCES = ["safeguard", "jackhhao", "itw", "openpi"]
HELDOUT_SOURCES = ["deepset", "notinject", "gandalf"]
ALL_SOURCES = TRAIN_SOURCES + HELDOUT_SOURCES + ["adversarial"]
SEED = 20261019
EXAMPLES = DATA / "examples.jsonl"
ADV_FILE = DATA / "adversarial.jsonl"  # attacks and hard negatives written during self-play rounds (committed)

_ZW = re.compile("[​‌‍⁠﻿­]")


def normalize(text: str) -> str:
    """The same normalization runs in training, eval and the web demo: NFC, strip zero-width and soft-hyphen
    characters and control characters except newline and tab, collapse runs of 3+ newlines, cap length."""
    t = unicodedata.normalize("NFC", text)
    t = _ZW.sub("", t)
    t = "".join(c for c in t if c in "\n\t" or unicodedata.category(c)[0] != "C")
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t[:MAX_CHARS]


def _dedupe_key(text: str) -> str:
    return hashlib.sha1(re.sub(r"\s+", " ", text.lower()).strip().encode()).hexdigest()


def _mk(source, split, idx, text, label, group=None):
    text = normalize(text)
    return {"id": f"{source}-{split}-{idx}", "text": text, "label": int(label), "source": source,
            "split": split, "group": group or f"{source}-{idx}"}


def _split_train_dev(rows, n_train, n_dev, rng, by_group=False):
    """Stratified (by label) split of rows into train and dev, optionally keeping groups together."""
    out = []
    if by_group:
        groups = sorted({r["group"] for r in rows})
        rng.shuffle(groups)
        cut = int(len(groups) * n_train / (n_train + n_dev))
        tr = set(groups[:cut])
        for r in rows:
            r["split"] = "train" if r["group"] in tr else "dev"
            out.append(r)
        return out
    for lab in (0, 1):
        rs = [r for r in rows if r["label"] == lab]
        rng.shuffle(rs)
        frac = len(rs) / max(1, len(rows))
        nt, nd = round(n_train * frac), round(n_dev * frac)
        for r in rs[:nt]:
            r["split"] = "train"; out.append(r)
        for r in rs[nt:nt + nd]:
            r["split"] = "dev"; out.append(r)
    return out


def _stratified_sample(rows, n, rng):
    if len(rows) <= n:
        return rows
    out = []
    for lab in (0, 1):
        rs = [r for r in rows if r["label"] == lab]
        rng.shuffle(rs)
        out += rs[: round(n * len(rs) / len(rows))]
    return out


def build():
    from datasets import load_dataset
    ex = []
    R = lambda name: random.Random(f"{SEED}-{name}")  # one generator per source, so sources do not shift each other

    # --- safeguard
    rng = R("safeguard")
    sg = load_dataset("xTRam1/safe-guard-prompt-injection")
    rows = [_mk("safeguard", "pool", i, r["text"], int(r["label"])) for i, r in enumerate(sg["train"])]
    ex += _split_train_dev(_stratified_sample(rows, 1100, rng), 800, 300, rng)
    rows = [_mk("safeguard", "test", i, r["text"], int(r["label"])) for i, r in enumerate(sg["test"])]
    ex += _stratified_sample(rows, 600, rng)

    # --- jackhhao
    rng = R("jackhhao")
    jb = load_dataset("jackhhao/jailbreak-classification")
    rows = [_mk("jackhhao", "pool", i, r["prompt"], r["type"] == "jailbreak") for i, r in enumerate(jb["train"])]
    ex += _split_train_dev(rows, 744, 300, rng)
    ex += [_mk("jackhhao", "test", i, r["prompt"], r["type"] == "jailbreak") for i, r in enumerate(jb["test"])]

    # --- itw (in-the-wild jailbreak prompts vs regular prompts, Dec 2023 snapshot)
    jbw = load_dataset("TrustAIRLab/in-the-wild-jailbreak-prompts", "jailbreak_2023_12_25")["train"]
    reg = load_dataset("TrustAIRLab/in-the-wild-jailbreak-prompts", "regular_2023_12_25")["train"]
    rng = R("itw")
    att = [r["prompt"] for r in jbw if r["prompt"]]
    # Label-noise filter for the "regular" (benign) side, fixed before any evaluation and applied to every split:
    # drop regular prompts that also appear in the jailbreak set, and regular prompts that name a jailbreak
    # ("DAN", "jailbreak", "do anything now"), about 2% of the regular set.
    att_keys = {_dedupe_key(t) for t in att}
    named = re.compile(r"\bDAN\b|jailbr|do anything now", re.I)
    ben = [r["prompt"] for r in reg if r["prompt"] and _dedupe_key(r["prompt"]) not in att_keys and not named.search(r["prompt"])]
    rng.shuffle(att); rng.shuffle(ben)
    rows = [("a", t, 1) for t in att[:800]] + [("b", t, 0) for t in ben[:800]]
    rng.shuffle(rows)
    rows = [_mk("itw", "pool", f"{k}{i}", t, y) for i, (k, t, y) in enumerate(rows)]
    test_rows, pool = rows[:500], rows[500:]
    for r in test_rows:
        r["split"] = "test"; r["id"] = r["id"].replace("-pool-", "-test-")
    ex += test_rows + _split_train_dev(pool, 800, 300, rng)

    # --- openpi (indirect injection into task data). Each row id gives one clean text and one attacked text.
    rng = R("openpi")
    op = load_dataset("xxz224/prompt-injection-attack-dataset")["train"]
    variants = ["escape_attack", "ignore_attack", "fake_comp_attack", "combine_attack"]
    ids = list(range(len(op)))
    rng.shuffle(ids)
    rows = []
    for i in ids[:950]:
        r = op[i]
        g = f"openpi-{i}"
        rows.append(_mk("openpi", "pool", f"{i}c", r["target_text"], 0, g))
        rows.append(_mk("openpi", "pool", f"{i}a", r[rng.choice(variants)], 1, g))
    groups = sorted({r["group"] for r in rows}); rng.shuffle(groups)
    test_g = set(groups[:250])
    for r in rows:
        if r["group"] in test_g:
            r["split"] = "test"; r["id"] = r["id"].replace("-pool-", "-test-")
    ex += [r for r in rows if r["split"] == "test"]
    ex += _split_train_dev([r for r in rows if r["split"] == "pool"], 800, 300, rng, by_group=True)

    # --- held-out sources: test only
    dp = load_dataset("deepset/prompt-injections")
    ex += [_mk("deepset", "test", i, r["text"], int(r["label"])) for i, r in enumerate(dp["test"])]
    ex += [_mk("deepset", "test", f"t{i}", r["text"], int(r["label"])) | {"subset": "official_train"}
           for i, r in enumerate(dp["train"])]
    ni = load_dataset("leolee99/NotInject")
    for cfg in ni:
        ex += [_mk("notinject", "test", f"{cfg}-{i}", r["prompt"], 0) for i, r in enumerate(ni[cfg])]
    gd = load_dataset("Lakera/gandalf_ignore_instructions")
    for sp in ("validation", "test"):
        ex += [_mk("gandalf", "test", f"{sp}-{i}", r["text"], 1) for i, r in enumerate(gd[sp])]

    for r in ex:
        r["id"] = r["id"].replace("-pool-", f"-{r['split']}-")
    ex = [r for r in ex if r["text"]]

    # --- cross-source dedupe: a text may appear once. Test copies win; otherwise first source wins.
    order = {"test": 0, "dev": 1, "train": 2}
    ex.sort(key=lambda r: (order[r["split"]], ALL_SOURCES.index(r["source"])))
    seen, kept, dropped = {}, [], Counter()
    for r in ex:
        k = _dedupe_key(r["text"])
        if k in seen:
            dropped[(r["source"], r["split"])] += 1
            continue
        seen[k] = r["id"]; kept.append(r)
    ids = Counter(r["id"] for r in kept)
    assert max(ids.values()) == 1, ("duplicate ids", [k for k, v in ids.items() if v > 1][:5])

    with EXAMPLES.open("w") as f:
        for r in sorted(kept, key=lambda r: r["id"]):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    counts = Counter((r["source"], r["split"], r["label"]) for r in kept)
    manifest = {
        "seed": SEED, "max_chars": MAX_CHARS, "train_sources": TRAIN_SOURCES, "heldout_sources": HELDOUT_SOURCES,
        "counts": {f"{s}/{sp}/{'attack' if y else 'benign'}": n for (s, sp, y), n in sorted(counts.items())},
        "dropped_duplicates": {f"{s}/{sp}": n for (s, sp), n in sorted(dropped.items())},
        "sha1_of_ids_by_split": {sp: hashlib.sha1("|".join(sorted(r["id"] for r in kept if r["split"] == sp)).encode()).hexdigest()
                                 for sp in ("train", "dev", "test")},
    }
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps(manifest, indent=1))


class TestSetLocked(RuntimeError):
    pass


def load(split=None, sources=None, allow_test=False, include_adversarial=True):
    """Load examples. split: 'train' | 'dev' | 'test' | list of them | None (= train+dev).
    The test split is locked unless allow_test=True (only the final eval passes it)."""
    splits = {"train", "dev"} if split is None else ({split} if isinstance(split, str) else set(split))
    if "test" in splits and not allow_test:
        raise TestSetLocked("test split requested without allow_test=True; only `englishnet.eval --final` may do this")
    rows = [json.loads(l) for l in EXAMPLES.open()]
    if include_adversarial and ADV_FILE.exists():
        rows += [json.loads(l) for l in ADV_FILE.open() if l.strip()]
    rows = [r for r in rows if r["split"] in splits]
    if sources is not None:
        rows = [r for r in rows if r["source"] in set(sources)]
    for r in rows:
        if r["split"] == "test" and not allow_test:  # belt and braces
            raise TestSetLocked(r["id"])
    return rows


if __name__ == "__main__":
    build()
