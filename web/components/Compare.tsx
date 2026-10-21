import { PAIRS } from "@/lib/results";
import { cx } from "./ui";

/* Figure 2: English Net minus the single question, ranking score (AUC), with 95% bootstrap intervals. */

const MIN = -0.018, MAX = 0.032;
const x = (v: number) => ((v - MIN) / (MAX - MIN)) * 100;
const f3 = (v: number) => v.toFixed(3);
const sgn = (v: number) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(Math.abs(v) < 0.001 ? 4 : 3);
const TICKS = [-0.01, 0, 0.01, 0.02, 0.03];

export default function Compare() {
  return (
    <div className="cmp" role="img" aria-label="English Net minus single question ranking score, with intervals, for four sets of texts">
      {PAIRS.map((p) => {
        const verdict = p.lo > 0 ? "win" : p.hi < 0 ? "loss" : "tie";
        const color = verdict === "win" ? "var(--accent)" : verdict === "loss" ? "var(--ink2)" : "var(--ink4)";
        return (
          <div className="crow" key={p.label}>
            <div className="cl">
              <b>{p.label}</b>
              <span>{p.sub}</span>
            </div>
            <svg viewBox="0 0 100 34" preserveAspectRatio="none" aria-hidden>
              <line x1={x(0)} x2={x(0)} y1="0" y2="34" stroke="var(--rule)" strokeWidth="1" vectorEffect="non-scaling-stroke" strokeDasharray="3 3" />
              <line x1={x(p.lo)} x2={x(p.hi)} y1="17" y2="17" stroke={color} strokeWidth="3" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
              <line x1={x(p.d)} x2={x(p.d)} y1="17" y2="17" stroke={color} strokeWidth="11" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
            </svg>
            <div className="cv">
              <b className={cx(verdict)}>{verdict === "win" ? "wins" : verdict === "loss" ? "small loss" : "tie"} {sgn(p.d)}</b>
              <span className="tnum">{f3(p.a)} vs {f3(p.b)}</span>
            </div>
          </div>
        );
      })}
      <div className="caxis" aria-hidden>
        <span />
        <div className="ticks">
          {TICKS.map((t) => (
            <span key={t} className="tick" style={{ left: `${x(t)}%` }}>{t === 0 ? "0" : (t > 0 ? "+" : "−") + Math.abs(t).toFixed(2)}</span>
          ))}
          <span className="dir l" style={{ right: `calc(${100 - x(0)}% + 8px)` }}>← one question better</span>
          <span className="dir r" style={{ left: `calc(${x(0)}% + 8px)` }}>English Net better →</span>
        </div>
        <span />
      </div>
    </div>
  );
}
