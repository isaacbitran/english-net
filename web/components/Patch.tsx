"use client";

import { useState } from "react";
import { cx, fmtP, postJSON } from "./ui";

/* Figures 3 and 4. Rows and every number come from web/data/replay.json, which `python -m englishnet.export_web`
   writes from results/patch.json, results/finetune.json and cached Jev answers. */

import { R, S } from "@/lib/patch";


type Row = { id: string; p_before: number; p_patch: number; p_after: number };
type Res = { weight: number; threshold: number; shipped: boolean; rows: Row[] };

export function PatchDemo() {
  const [q, setQ] = useState(S.patch.question);
  const [res, setRes] = useState<Res | null>(null);
  const [shown, setShown] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add() {
    setLoading(true);
    setError(null);
    setRes(null);
    setShown(0);
    try {
      const r = await postJSON<Res>("/api/patch", { question: q });
      setRes(r);
      r.rows.forEach((_, i) => setTimeout(() => setShown(i + 1), 160 * (i + 1)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Patch failed.");
    } finally {
      setLoading(false);
    }
  }

  const byId = new Map(res?.rows.map((r) => [r.id, r]) ?? []);
  const thr = S.rule.threshold;
  const weight = res?.weight ?? S.patch.weight;

  return (
    <div>
      <div className="patcher">
        <div>
          <textarea id="patch-q" className="ta" rows={3} aria-label="New neuron" value={q} maxLength={400} onChange={(e) => setQ(e.target.value)} />
          <div className="ctl">
            <button className="btn" onClick={add} disabled={loading || q.trim().length < 12} data-test="add-neuron">
              {loading ? "Asking Jev" : "Add this sentence as a neuron"}
            </button>
            {q !== S.patch.question && (
              <button className="btn ghost" onClick={() => setQ(S.patch.question)}>Reset to the shipped sentence</button>
            )}
            {error && <span className="err">{error}</span>}
          </div>
        </div>
        <div className="rule">
          <div className="k">Its weight, set by a rule</div>
          <div className="w tnum">+{weight.toFixed(2)}</div>
          A yes from Jev (p = {S.rule.p_confident}) must lift a typical benign text over the threshold. No example sets it, and no other
          weight moves.
        </div>
      </div>

      <div className="prows" data-test="patch-rows">
        <div className="phead" aria-hidden>
          <span>Text (not among the 30 the sentence was written from)</span>
          <span>Before</span>
          <span>Jev on the new question</span>
          <span>After</span>
        </div>
        {R.patch_demo.map((d, i) => {
          const r = byId.get(d.id);
          const live = !!r && i < shown;
          const before = d.p_before >= thr;
          const after = live ? r.p_after >= thr : null;
          const flipped = live && before !== after;
          return (
            <div key={d.id} className={cx("prow", flipped && (after ? "flip-a" : "flip-b"))}>
              <div className="pinfo" style={{ minWidth: 0 }}>
                <div className="pt" title={d.text}>{d.text}</div>
                <div className="ps">{sourceLabel(d.source)} · {d.label ? "attack" : "benign"}</div>
              </div>
              <V on={before} />
              <div className="ans">
                <span className="track"><i style={{ width: `${live ? r.p_patch * 100 : 0}%`, background: "var(--accent)" }} /></span>
                <b>{live ? fmtP(r.p_patch) : "–"}</b>
              </div>
              <V on={after} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Plain description of a demo row's source; the dataset name stays in parentheses. */
function sourceLabel(src: string) {
  if (src.startsWith("Mosscap")) return "Password-extraction game (Mosscap), locked test split";
  if (src.startsWith("NotInject")) return "Benign prompt with trigger words (NotInject)";
  return src;
}

function V({ on }: { on: boolean | null }) {
  if (on === null) return <span className="vd x">–</span>;
  return on ? <span className="vd a">Attack</span> : <span className="vd b">Benign</span>;
}

/* Figure 4: the shipped sentence vs fine-tuning ProtectAI DeBERTa v2 on the same examples. */
export function Versus() {
  const ft = S.finetune;
  const rows = [
    {
      who: "English Net + one sentence",
      how: "1 sentence, a rule for its weight, no training",
      fam: S.family,
      rest: S.everything_else,
    },
    {
      who: "ProtectAI DeBERTa, fine-tuned",
      how: `${ft.train_examples.attack} attacks + ${ft.train_examples.benign} benign texts, ${ft.epochs} epochs, ${ft.train_seconds} s on an Apple M-series GPU; 184M weights change`,
      fam: ft.family,
      rest: ft.everything_else,
    },
  ];
  const maxFa = Math.max(...rows.map((r) => r.rest.new_false_alarms));
  return (
    <div className="vs">
      <div className="vhead" aria-hidden>
        <span>Method</span>
        <span>Password attacks caught (206)</span>
        <span>New false alarms (2,731 benign)</span>
        <span>Attacks lost</span>
      </div>
      {rows.map((r) => {
        const a = r.fam.catch_before ?? 0, b = r.fam.catch_after ?? 0;
        const fa = r.rest.new_false_alarms;
        return (
          <div className="vrow" key={r.who}>
            <div className="who"><b>{r.who}</b><span>{r.how}</span></div>
            <div className="catch">
              <span className="lab">Password attacks caught (206)</span>
              <svg viewBox="0 0 100 30" preserveAspectRatio="none" aria-label={`${a}% to ${b}%`}>
                <line x1="0" x2="100" y1="15" y2="15" stroke="var(--fill)" strokeWidth="6" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
                <line x1={a} x2={b} y1="15" y2="15" stroke="var(--accent)" strokeWidth="6" vectorEffect="non-scaling-stroke" />
                <line x1={a} x2={a} y1="15" y2="15" stroke="var(--ink3)" strokeWidth="12" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
                <line x1={b} x2={b} y1="15" y2="15" stroke="var(--accent)" strokeWidth="14" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
              </svg>
              <div className="num">{a}% → {b}%</div>
            </div>
            <div>
              <span className="lab">New false alarms (2,731 benign)</span>
              <svg viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden>
                <line x1="0" x2={Math.max(1.5, (fa / maxFa) * 100)} y1="15" y2="15" stroke="var(--attack)" strokeWidth="12" vectorEffect="non-scaling-stroke" />
              </svg>
              <div className="num">{fa}{r.rest.false_alarms_removed ? <small style={{ fontSize: 12, color: "var(--ink3)", fontFamily: "var(--sans)" }}> ({r.rest.false_alarms_removed} old ones removed)</small> : null}</div>
            </div>
            <div className="lost">
              <span className="lab">Attacks lost</span>
              <b className="tnum">{r.rest.new_misses}</b>
            </div>
          </div>
        );
      })}
    </div>
  );
}
