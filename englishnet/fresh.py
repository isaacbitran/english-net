"""Fresh confirmation data: five public sources that no English Net model, design choice or proposal has seen.

Why it exists: the v5 test splits were read when v6 was designed (v6 adds the broad question as a neuron because
v5 lost to it there). Claims about v6 and about the one-sentence patch are therefore confirmed on this set, which was
built and frozen before any v6 answer on it was computed.

Sources (sampled with a fixed seed, deduplicated against data/examples.jsonl and against each other):
  multiling_attack  yanismiraoui/prompt_injections: 1,034 short injections in English, French, Spanish, Italian,
                    Portuguese and German (all attacks)
  aya_benign        CohereForAI/aya_dataset: ordinary user requests in the same six languages (all benign)
  spml              reshabhs/SPML_Chatbot_Prompt_Injection: chatbot user turns, injection or not (Gandalf rows dropped)
  mosscap           Lakera/mosscap_prompt_injection (test split): password-extraction attacks, levels 1-8
  jayavibhav        jayavibhav/prompt-injection (test split): synthetic injections hidden in code-like text, and benign

Splits: `fresh_dev` (30% by id hash) may be read to find an attack family the network misses and to pick a handful
of patch examples. `fresh_test` (70%) is locked like the test split and read only by englishnet.eval and
englishnet.patch for final numbers.

  python -m englishnet.fresh        # writes data/fresh.jsonl (ids, text, label, source, lang, split)
"""
import hashlib
import json
import random

from .config import DATA
from .data import EXAMPLES, TestSetLocked, _dedupe_key, normalize

FRESH = DATA / "fresh.jsonl"
SEED = 20261021
LANGS = {"English": "en", "French": "fr", "Spanish": "es", "Italian": "it", "Portuguese": "pt", "German": "de"}


def _split(rid: str) -> str:
    return "fresh_dev" if int(hashlib.sha1(rid.encode()).hexdigest(), 16) % 10 < 3 else "fresh_test"


def build():
    from datasets import load_dataset
    from langdetect import DetectorFactory, detect
    DetectorFactory.seed = 0
    rng = random.Random(SEED)
    out = []

    def add(source, i, text, label, lang=None):
        t = normalize(text or "")
        if t:
            out.append({"id": f"{source}-{i}", "text": t, "label": int(label), "source": source, "lang": lang})

    for i, t in enumerate(load_dataset("yanismiraoui/prompt_injections")["train"]["prompt_injections"]):
        try:
            lang = detect(t)
        except Exception:
            lang = "unk"
        add("multiling_attack", i, t, 1, lang)

    aya = load_dataset("CohereForAI/aya_dataset", split="train")
    for name, code in LANGS.items():
        idx = [i for i, l in enumerate(aya["language"]) if l == name]
        for i in rng.sample(idx, 150 if code != "en" else 100):
            add("aya_benign", i, aya[i]["inputs"], 0, code)

    sp = load_dataset("reshabhs/SPML_Chatbot_Prompt_Injection")["train"]
    idx = [i for i in range(len(sp)) if sp[i]["Source"] != "Gandalf"]
    for lab in (0, 1):
        pool = [i for i in idx if sp[i]["Prompt injection"] == lab]
        for i in rng.sample(pool, 300):
            add("spml", i, sp[i]["User Prompt"], lab, "en")

    mc = load_dataset("Lakera/mosscap_prompt_injection", split="test")
    for i in rng.sample(range(len(mc)), 300):
        add("mosscap", i, mc[i]["prompt"], 1, "en")

    jv = load_dataset("jayavibhav/prompt-injection", split="test")
    for lab in (0, 1):
        pool = [i for i in range(len(jv)) if jv[i]["label"] == lab]
        for i in rng.sample(pool, 200):
            add("jayavibhav", i, jv[i]["text"], lab, "en")

    seen = {_dedupe_key(json.loads(l)["text"]) for l in EXAMPLES.open()}
    kept = []
    for r in out:
        k = _dedupe_key(r["text"])
        if k in seen:
            continue
        seen.add(k)
        r["split"] = _split(r["id"])
        kept.append(r)
    with FRESH.open("w") as f:
        for r in sorted(kept, key=lambda r: r["id"]):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    c = Counter((r["source"], r["split"], r["label"]) for r in kept)
    for k in sorted(c):
        print(k, c[k])
    print("sha1 of ids:", hashlib.sha1("|".join(sorted(r["id"] for r in kept)).encode()).hexdigest())


def load_fresh(split="fresh_dev", allow_test=False):
    """fresh_test is locked like the main test split."""
    splits = {split} if isinstance(split, str) else set(split)
    if "fresh_test" in splits and not allow_test:
        raise TestSetLocked("fresh_test is locked; pass allow_test (report-only modules do)")
    return [r for r in (json.loads(l) for l in FRESH.open()) if r["split"] in splits]


if __name__ == "__main__":
    build()
