/* Mirrors englishnet/data.py normalize(): NFC, strip zero-width and soft-hyphen characters, strip control
   characters (Unicode category C) except newline and tab, collapse 3+ newlines to 2, trim, cap at 6000 code points. */

export const MAX_CHARS = 6000;
const ZW = /[​‌‍⁠﻿­]/g;
const OTHER = /\p{C}/u;

export function normalizeFull(text: string): string {
  let t = text.normalize("NFC").replace(ZW, "");
  t = Array.from(t)
    .filter((c) => c === "\n" || c === "\t" || !OTHER.test(c))
    .join("");
  return t.replace(/\n{3,}/g, "\n\n").trim();
}

export function normalize(text: string): string {
  return Array.from(normalizeFull(text)).slice(0, MAX_CHARS).join("");
}

export const charCount = (t: string) => Array.from(t).length;
