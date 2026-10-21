"""Write docs/EVOLUTION.md: the network's history as English.  python -m englishnet.evolog"""
from . import neurons as N
from .config import DOCS


def main():
    net = N.load()
    by = N.by_id(net)
    L = ["# Evolution log", "", f"Generated from `model/network.json` (network v{net['version']}, Jev `{net['jev_model']}`) by "
         "`python -m englishnet.evolog`. Selection score J = mean of pooled dev AUC and leave-one-source-out dev AUC over the "
         "training sources (see `englishnet/fit.py`). Proposer \"claude-in-session\" means Claude wrote the proposals in the build "
         "session from the saved prompt because the Anthropic API key had no credit; the prompt and response are in `proposals/`.", ""]
    for h in net["history"]:
        m = h["metrics"]
        L.append(f"## Round {h['round']}: {h['kind']} ({h['at']}, proposer: {h['proposer']})")
        L.append("")
        L.append(h["summary"])
        L.append("")
        if h["kind"] in ("evolution",):
            L.append(f"Selection score {m['J_before']} -> {m['J']}; {m['n_active']} active neurons; "
                     f"{m['n_proposed']} proposed, {m['n_passed_gate']} passed the consistency gate.")
            L.append("")
        for a in h.get("added", []):
            n = by[a]
            par = n.get("parent") or {}
            src = f" Born from: {par.get('kind')} {', '.join(par.get('example_ids', [])[:3])}." if par.get("example_ids") else ""
            L.append(f"- Added `{a}` (final weight {n['weight']:+.2f}, status {n['status']}): \"{n['question']}\"{src}")
            if par.get("excerpt"):
                L.append(f"  - Parent text: \"{par['excerpt'][:160]}\"")
        for d in h.get("dropped", []):
            L.append(f"- Dropped `{d}`: \"{by[d]['question']}\"")
        for r in h.get("rejected", []):
            L.append(f"- Rejected `{r['id']}`: {r['reason']}")
        for e in h.get("examples_missed", []):
            L.append(f"- Missed ({e['family']}, p={e['p_attack']}): \"{e['excerpt'][:140]}\"")
        if m.get("by_family"):
            L.append("")
            L.append("Caught by family: " + "; ".join(f"{k} {v}" for k, v in m["by_family"].items()) + ".")
        L.append("")
    L += ["## Final network", "", "| Weight | Neuron | Question | Born |", "|---|---|---|---|"]
    for n in sorted(N.active(net), key=lambda n: -abs(n["weight"])):
        L.append(f"| {n['weight']:+.2f} | `{n['id']}` | {n['question']} | round {n['born_round']} ({n['origin']}) |")
    L.append(f"\nIntercept {net['readout']['intercept']}, threshold {net['readout']['threshold']}, C {net['readout']['C']}.")
    (DOCS / "EVOLUTION.md").write_text("\n".join(L) + "\n")
    print(f"wrote {DOCS / 'EVOLUTION.md'}")


if __name__ == "__main__":
    main()
