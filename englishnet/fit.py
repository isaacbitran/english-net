"""Readout fitting, the selection objective, thresholds and metrics. No API calls happen here.

Readout: L1-regularized logistic regression over neuron probabilities. Samples are weighted so that every
(source, label) cell has the same total weight; otherwise the largest source decides the weights.

Selection objective J (higher is better), computed on train and dev only:
  pooled = mean over training sources s of AUC on dev(s), fitting on train(all sources)
  loso   = mean over training sources s of AUC on dev(s), fitting on train(all sources except s)
  J = (pooled + loso) / 2
The LOSO half rewards neurons that transfer to a source the readout did not see, which is the prototype's weak spot.
"""
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score, roc_curve
from sklearn.model_selection import StratifiedKFold

from .data import TRAIN_SOURCES

DEFAULT_C = 0.5


EPS = 1e-4


def logit(p):
    p = min(max(float(p), EPS), 1 - EPS)
    return float(np.log(p / (1 - p)))


def feature(p, kind="prob"):
    """What the readout sees from one neuron: its yes-probability, or (input="logit") the log-odds of it.
    Log-odds keep the fine ranking of a strong broad question (0.95 vs 0.999) that a probability squashes."""
    return logit(p) if kind == "logit" else float(p)


def matrix(answers, ids, kinds=None):
    kinds = kinds or {}
    return np.array([[feature(a[i], kinds.get(i, "prob")) for i in ids] for a in answers], dtype=float)


def sample_weights(rows):
    cells = {}
    for r in rows:
        cells[(r["source"], r["label"])] = cells.get((r["source"], r["label"]), 0) + 1
    w = np.array([1.0 / cells[(r["source"], r["label"])] for r in rows])
    return w * len(rows) / w.sum()


def fit(X, rows, C=DEFAULT_C):
    y = np.array([r["label"] for r in rows])
    m = LogisticRegression(l1_ratio=1.0, C=C, solver="liblinear", max_iter=5000)
    m.fit(X, y, sample_weight=sample_weights(rows))
    return m


def _auc(y, p):
    return roc_auc_score(y, p) if len(set(y)) == 2 else float("nan")


class Objective:
    """Caches the row partitions so that J(columns) is a handful of fast refits."""

    def __init__(self, train_rows, dev_rows, train_feats, dev_feats, C=DEFAULT_C, sources=TRAIN_SOURCES):
        self.tr, self.dv, self.Ftr, self.Fdv, self.C = train_rows, dev_rows, train_feats, dev_feats, C
        self.sources = [s for s in sources if any(r["source"] == s for r in dev_rows)]
        self.tr_src = np.array([r["source"] for r in train_rows])
        self.dv_src = np.array([r["source"] for r in dev_rows])
        self.ytr = np.array([r["label"] for r in train_rows])
        self.ydv = np.array([r["label"] for r in dev_rows])
        self.wtr = sample_weights(train_rows)

    def _fitpred(self, cols, train_mask, dev_mask):
        Xtr, Xdv = self.Ftr[np.ix_(train_mask, cols)], self.Fdv[np.ix_(dev_mask, cols)]
        w = self.wtr[train_mask]
        m = LogisticRegression(l1_ratio=1.0, C=self.C, solver="liblinear", max_iter=5000)
        m.fit(Xtr, self.ytr[train_mask], sample_weight=w * len(w) / w.sum())
        return m.predict_proba(Xdv)[:, 1]

    def parts(self, cols):
        cols = list(cols)
        all_tr = np.ones(len(self.tr), bool)
        pooled, loso = {}, {}
        all_dev = np.ones(len(self.dv), bool)
        p_all = self._fitpred(cols, all_tr, all_dev)
        for s in self.sources:
            dm = self.dv_src == s
            pooled[s] = _auc(self.ydv[dm], p_all[dm])
            loso[s] = _auc(self.ydv[dm], self._fitpred(cols, self.tr_src != s, dm))
        return pooled, loso

    def __call__(self, cols):
        pooled, loso = self.parts(cols)
        return 0.5 * (np.nanmean(list(pooled.values())) + np.nanmean(list(loso.values())))


def tune_threshold(rows, p):
    """Threshold that maximizes the mean over sources of balanced accuracy (sources with both labels)."""
    p = np.asarray(p)
    src = np.array([r["source"] for r in rows]); y = np.array([r["label"] for r in rows])
    best, best_t = -1, 0.5
    for t in np.linspace(0.05, 0.95, 91):
        accs = []
        for s in set(src):
            m = src == s
            if len(set(y[m])) < 2:
                continue
            yh = p[m] >= t
            accs.append(0.5 * ((yh[y[m] == 1]).mean() + (~yh[y[m] == 0]).mean()))
        if accs and np.mean(accs) > best:
            best, best_t = np.mean(accs), float(t)
    return round(best_t, 3)


def oof_predict(X, rows, C=DEFAULT_C, folds=5, seed=0):
    y = np.array([r["label"] for r in rows])
    strat = np.array([f"{r['source']}-{r['label']}" for r in rows])
    p = np.zeros(len(rows))
    for tr, te in StratifiedKFold(folds, shuffle=True, random_state=seed).split(X, strat):
        m = fit(X[tr], [rows[i] for i in tr], C)
        p[te] = m.predict_proba(X[te])[:, 1]
    return p


def catch_at_fpr(y, p, fpr_target):
    y, p = np.asarray(y), np.asarray(p)
    if len(set(y)) < 2:
        return float("nan")
    neg = np.sort(p[y == 0])[::-1]
    k = int(np.floor(fpr_target * len(neg)))
    thr = neg[k] if k < len(neg) else -np.inf
    return float((p[y == 1] > thr).mean())


def metrics(y, p, thr):
    y, p = np.asarray(y), np.asarray(p)
    yh = (p >= thr).astype(int)
    out = {"n": int(len(y)), "acc": round(100 * accuracy_score(y, yh), 1)}
    if len(set(y)) == 2:
        out.update({"f1": round(100 * f1_score(y, yh), 1), "auc": round(roc_auc_score(y, p), 3),
                    "catch@1%fpr": round(100 * catch_at_fpr(y, p, 0.01), 1),
                    "catch@5%fpr": round(100 * catch_at_fpr(y, p, 0.05), 1),
                    "fpr": round(100 * yh[y == 0].mean(), 1), "tpr": round(100 * yh[y == 1].mean(), 1)})
    elif y.size and y[0] == 0:
        out["fpr"] = round(100 * yh.mean(), 1)
    else:
        out["tpr"] = round(100 * yh.mean(), 1)
    return out
