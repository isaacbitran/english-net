import type { ReactNode } from "react";
import type { Neuron } from "@/lib/types";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

export const fmtW = (w: number) => (w > 0 ? "+" : w < 0 ? "−" : "±") + Math.abs(w).toFixed(2);
export const fmtP = (p: number) => p.toFixed(2);
export const word = (p: number) => (p >= 0.6 ? "yes" : p <= 0.4 ? "no" : "unclear");
export const sign = (w: number) => (w > 0.005 ? "pos" : w < -0.005 ? "neg" : "");

/** Where a neuron came from, in plain words. */
export function born(n: Neuron): string {
  if (n.origin === "patch") return "The added sentence, written from 30 missed password-extraction prompts";
  if (n.input === "logit") return "The single broad question, added as a neuron in the final version";
  if (n.origin === "adversarial") return `Written by the training loop in round ${n.born_round}, from attacks that got through`;
  if (n.origin === "evolved") return `Written by the training loop in round ${n.born_round}, from training mistakes`;
  return "Hand-written at the start";
}

export function Figure({ n, title, children, caption }: { n: number; title: string; children: ReactNode; caption?: ReactNode }) {
  return (
    <figure className="fig">
      <div className="fh">
        <span className="fn">Figure {n}</span>
        <span className="ft">{title}</span>
      </div>
      {children}
      {caption && <figcaption>{caption}</figcaption>}
    </figure>
  );
}

export function Keys({ items }: { items: { v: string; l: ReactNode; s?: ReactNode }[] }) {
  return (
    <div className="keys">
      {items.map((k) => (
        <div className="stat" key={k.v + String(k.l)}>
          <b>{k.v}</b>
          <span>{k.l}</span>
          {k.s && <small>{k.s}</small>}
        </div>
      ))}
    </div>
  );
}

export function Details({ summary, children }: { summary: string; children: ReactNode }) {
  return (
    <details className="more">
      <summary>{summary}</summary>
      <div className="body">{children}</div>
    </details>
  );
}

export async function postJSON<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { error?: string }).error ?? `HTTP ${res.status}`);
  return data as T;
}
