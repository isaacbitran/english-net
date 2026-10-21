"""Jev client: per-question disk cache, batching, concurrency, spend ledger and a hard budget cap.

Cache key = sha1(model | sha1(state) | sha1(question spec)). One Jev call answers every uncached question for one
state; answers are stored per question, so adding a neuron later costs one call per text for just that neuron.
Jev evaluates the questions of one request independently (docs: "Parallel questions", no change in answers), which
is what makes per-question caching valid.

The ledger (cache/ledger.jsonl) records one line per real API call: time, purpose, tokens, latency, USD.
`python -m englishnet.spend` turns it into docs/SPEND.md.
"""
import hashlib
import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .config import CACHE, JEV_BUDGET_USD, JEV_MODEL, JEV_USD_PER_MTOK

DB = CACHE / "jev.sqlite"
LEDGER = CACHE / "ledger.jsonl"
_lock = threading.Lock()
_local = threading.local()
MAX_Q_PER_CALL = 64


class BudgetExceeded(RuntimeError):
    pass


def _sha(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()


def qspec(neuron: dict) -> dict:
    """The part of a neuron that Jev sees. Only these fields enter the cache key."""
    spec = {"type": "noul", "instructions": neuron["question"]}
    if neuron.get("criteria"):
        spec["criteria"] = neuron["criteria"]
    return spec


def qhash(neuron: dict) -> str:
    return _sha(json.dumps(qspec(neuron), sort_keys=True))


def state_of(text_or_state) -> dict:
    return text_or_state if isinstance(text_or_state, dict) else {"text": text_or_state}


def _db():
    if not hasattr(_local, "db"):
        c = sqlite3.connect(DB, timeout=60, check_same_thread=False)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("CREATE TABLE IF NOT EXISTS answers (k TEXT PRIMARY KEY, p REAL, conf REAL)")
        _local.db = c
    return _local.db


def _client():
    if not hasattr(_local, "client"):
        from typesafe_sdk import TypeSafeClient
        _local.client = TypeSafeClient(model=JEV_MODEL)
    return _local.client


def spent_usd() -> float:
    if not LEDGER.exists():
        return 0.0
    return sum(json.loads(l)["usd"] for l in LEDGER.open() if l.strip())


_spent_cache = {"v": None}


def _charge(rec: dict):
    with _lock:
        if _spent_cache["v"] is None:
            _spent_cache["v"] = spent_usd()
        _spent_cache["v"] += rec["usd"]
        with LEDGER.open("a") as f:
            f.write(json.dumps(rec) + "\n")


def _guard(est_tokens: int, budget: float):
    with _lock:
        if _spent_cache["v"] is None:
            _spent_cache["v"] = spent_usd()
        if _spent_cache["v"] + est_tokens * JEV_USD_PER_MTOK / 1e6 > budget:
            raise BudgetExceeded(f"Jev spend {_spent_cache['v']:.3f} USD would pass the {budget} USD cap")


def lookup(state: dict, neurons: list[dict]) -> dict:
    """Return {neuron_id: p} for the cached answers only."""
    sk = _sha(json.dumps(state, sort_keys=True, ensure_ascii=False))
    keys = {n["id"]: _sha(f"{JEV_MODEL}|{sk}|{qhash(n)}") for n in neurons}
    out = {}
    cur = _db().cursor()
    for nid, k in keys.items():
        row = cur.execute("SELECT p FROM answers WHERE k=?", (k,)).fetchone()
        if row:
            out[nid] = row[0]
    return out


def ask(text_or_state, neurons: list[dict], purpose: str = "", budget: float = JEV_BUDGET_USD,
        offline: bool = False) -> dict:
    """Answer every neuron for one state, calling Jev only for uncached questions. Returns {id: p}.
    Duplicate question specs (same text) are asked once."""
    state = state_of(text_or_state)
    out = lookup(state, neurons)
    missing = [n for n in neurons if n["id"] not in out]
    if not missing:
        return out
    if offline:
        raise KeyError(f"{len(missing)} uncached answers and offline=True")
    from typesafe_sdk import Noul
    sk = _sha(json.dumps(state, sort_keys=True, ensure_ascii=False))
    by_hash = {}
    for n in missing:
        by_hash.setdefault(qhash(n), []).append(n)
    hashes = list(by_hash)
    state_chars = len(json.dumps(state, ensure_ascii=False))
    for i in range(0, len(hashes), MAX_Q_PER_CALL):
        chunk = hashes[i:i + MAX_Q_PER_CALL]
        est = state_chars // 3 + sum(len(by_hash[h][0]["question"]) // 3 + 8 for h in chunk)
        _guard(est, budget)
        qs = {}
        for j, h in enumerate(chunk):
            spec = qspec(by_hash[h][0])
            qs[f"q{j}"] = Noul(instructions=spec["instructions"], criteria=spec.get("criteria"))
        for attempt in range(6):
            try:
                t0 = time.perf_counter()
                r = _client().system_one(state=state, questions=qs)
                ms = (time.perf_counter() - t0) * 1000
                break
            except Exception as e:  # SDK already retries 429/5xx; this covers transient connection errors
                if attempt == 5 or "401" in str(e) or "400" in str(e):
                    raise
                time.sleep(2 * (attempt + 1))
        tokens = int(getattr(r.usage, "input_tokens", 0) or 0)
        _charge({"t": round(time.time(), 2), "purpose": purpose, "model": getattr(r, "model", JEV_MODEL),
                 "n_q": len(chunk), "tokens": tokens, "ms": round(ms, 1),
                 "usd": tokens * JEV_USD_PER_MTOK / 1e6})
        db = _db()
        with db:
            for j, h in enumerate(chunk):
                a = r.nouls[f"q{j}"]
                p, conf = float(a.noul), (float(a.confidence) if getattr(a, "confidence", None) is not None else None)
                db.execute("INSERT OR REPLACE INTO answers VALUES (?,?,?)", (_sha(f"{JEV_MODEL}|{sk}|{h}"), p, conf))
                for n in by_hash[h]:
                    out[n["id"]] = p
    return out


def ask_many(items, neurons, purpose="", workers=8, budget=JEV_BUDGET_USD, offline=False, progress=True):
    """items: list of texts or state dicts. Returns a list of {id: p} in order."""
    items = list(items)
    done = [0]
    t0 = time.time()

    def one(x):
        r = ask(x, neurons, purpose=purpose, budget=budget, offline=offline)
        done[0] += 1
        if progress and done[0] % 500 == 0:
            print(f"  [{purpose}] {done[0]}/{len(items)}  {time.time() - t0:.0f}s  spent {_spent_cache['v'] or 0:.3f} USD", flush=True)
        return r

    if offline or workers <= 1:
        return [one(x) for x in items]
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(one, items))
