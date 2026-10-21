"use client";

import { useEffect, useState } from "react";
import { cx } from "./ui";

/* Sticky top bar; the link for the part on screen is underlined. */
export default function Nav({ parts }: { parts: { id: string; short: string }[] }) {
  const [on, setOn] = useState<string | null>(null);
  useEffect(() => {
    const els = parts.map((p) => document.getElementById(p.id)).filter((e): e is HTMLElement => !!e);
    const io = new IntersectionObserver(
      (es) => {
        const vis = es.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (vis[0]) setOn(vis[0].target.id);
      },
      { rootMargin: "-30% 0px -60% 0px" },
    );
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
  }, [parts]);
  return (
    <header className="top">
      <div className="in">
        <a className="brand" href="#">English Net</a>
        <nav className="tabs" aria-label="Parts">
          {parts.map((p, i) => (
            <a key={p.id} href={`#${p.id}`} className={cx(on === p.id && "on")}>
              <span className="n">{i + 1}</span>
              {p.short}
            </a>
          ))}
        </nav>
      </div>
    </header>
  );
}
