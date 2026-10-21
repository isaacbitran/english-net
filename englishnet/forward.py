"""Forward pass: layer 1 (one Jev call over the text) -> optional layer 2 (one Jev call over layer-1 findings
rendered as words) -> logistic readout over each neuron's probability (or its log-odds, for neurons with
input="logit"). Returns a verdict object with every neuron's contribution."""
import math
import time

from . import jev
from .data import normalize
from .fit import feature
from .neurons import active


def word(p):
    return "yes" if p >= 0.6 else ("no" if p <= 0.4 else "unclear")


def layer2_state(n2, l1_answers, l1_by_id):
    """State for one layer-2 neuron: its input neurons' questions with yes/no/unclear answers (Jev reads words
    more reliably than numbers)."""
    return {"findings": {l1_by_id[i]["question"]: word(l1_answers[i]) for i in n2["inputs"]}}


def layer2_answers(net, l1_answers_list, purpose="layer2", offline=False, workers=8):
    """Answers for every active layer-2 neuron. Neurons that share inputs share a state and therefore a call."""
    l2 = active(net, layer=2)
    if not l2:
        return [dict() for _ in l1_answers_list]
    l1 = {n["id"]: n for n in net["neurons"]}
    groups = {}
    for n in l2:
        groups.setdefault(tuple(n["inputs"]), []).append(n)
    out = [dict() for _ in l1_answers_list]
    for inputs, ns in groups.items():
        states = [layer2_state(ns[0], a, l1) for a in l1_answers_list]
        res = jev.ask_many(states, ns, purpose=purpose, offline=offline, workers=workers, progress=False)
        for o, r in zip(out, res):
            o.update(r)
    return out


def score(text, net, purpose="score", offline=False):
    t0 = time.perf_counter()
    text = normalize(text)
    l1 = active(net, layer=1)
    a1 = jev.ask(text, l1, purpose=purpose, offline=offline)
    a2 = layer2_answers(net, [a1], purpose=purpose, offline=offline, workers=1)[0]
    ms = (time.perf_counter() - t0) * 1000
    ans = {**a1, **a2}
    contribs = []
    z = net["readout"]["intercept"]
    for n in active(net):
        x = feature(ans[n["id"]], n.get("input", "prob"))
        c = n["weight"] * x
        z += c
        contribs.append({"id": n["id"], "layer": n["layer"], "question": n["question"], "p": ans[n["id"]],
                         "input": n.get("input", "prob"), "x": round(x, 4), "weight": n["weight"],
                         "contribution": round(c, 4)})
    p = 1 / (1 + math.exp(-z))
    thr = net["readout"]["threshold"]
    contribs.sort(key=lambda c: -abs(c["contribution"]))
    return {"p_attack": round(p, 4), "label": "attack" if p >= thr else "benign", "threshold": thr,
            "logit": round(z, 4), "intercept": net["readout"]["intercept"], "ms": round(ms, 1),
            "model": net["jev_model"], "contributions": contribs}
