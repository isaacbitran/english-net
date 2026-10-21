"""Paths, pinned model, prices and secrets loading. Secrets are read from .env and never printed."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = ROOT / "cache"
MODEL_DIR = ROOT / "model"
RESULTS = ROOT / "results"
PROPOSALS = ROOT / "proposals"
ATTACKS = ROOT / "attacks"
DOCS = ROOT / "docs"

# Jev model is pinned to a versioned id (not the moving `jev-latest` alias) so cached answers stay valid.
JEV_MODEL = "jev-1.13.0"
JEV_USD_PER_MTOK = 0.042          # input tokens only; output tokens are free (docs.typesafe.ai/models)
JEV_BUDGET_USD = 2.80             # hard cap for the whole build (ledger total); jev.py refuses calls past it
MAX_CHARS = 6000                  # texts are truncated before they reach Jev

CLAUDE_MODEL = "claude-opus-5-5"


def load_env() -> None:
    """Load KEY=VALUE lines from ROOT/.env into os.environ without overriding existing values."""
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)


load_env()
for d in (DATA, CACHE, MODEL_DIR, RESULTS, PROPOSALS, ATTACKS):
    d.mkdir(exist_ok=True)
